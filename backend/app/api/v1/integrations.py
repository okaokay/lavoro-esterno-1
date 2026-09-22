"""Admin settings for ingestion and reliable webhook destinations."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.ai_settings import AIProviderConfig
from app.models.integrations import IngestionSettings, WebhookEndpoint, WebhookEndpointSource
from app.models.sources import Source
from app.models.users import User
from app.schemas.integrations import (
    IngestionSettingsRead,
    IngestionSettingsUpdate,
    SanitizationBackfillRead,
    WebhookEndpointInput,
    WebhookEndpointRead,
    WebhookEndpointUpdate,
)
from app.security.deps import require_admin_with_2fa, require_role
from app.services.audit import log_action
from app.services.integration_crypto import encrypt_json

router = APIRouter()


async def _ingestion_read(db: AsyncSession) -> IngestionSettingsRead:
    row = await db.get(IngestionSettings, 1)
    provider = (
        await db.execute(select(AIProviderConfig).where(AIProviderConfig.provider == "ollama"))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(503, "Impostazioni acquisizione non inizializzate.")
    return IngestionSettingsRead(
        publish_batch_size=row.publish_batch_size,
        revision=row.revision,
        sanitization_model=provider.model_name if provider else "non configurato",
    )


@router.get("/ingestion-settings", response_model=IngestionSettingsRead)
async def get_ingestion_settings(
    db: AsyncSession = Depends(get_db), _admin: User = Depends(require_role("admin"))
):
    return await _ingestion_read(db)


@router.patch("/ingestion-settings", response_model=IngestionSettingsRead)
async def update_ingestion_settings(
    payload: IngestionSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin_with_2fa),
):
    row = (
        await db.execute(
            select(IngestionSettings).where(IngestionSettings.id == 1).with_for_update()
        )
    ).scalar_one()
    if row.revision != payload.expected_revision:
        raise HTTPException(409, "Impostazioni modificate da un altro Admin.")
    row.publish_batch_size = payload.publish_batch_size
    row.revision += 1
    await log_action(
        db,
        user_id=admin.id,
        action="update_ingestion_settings",
        entity_type="ingestion_settings",
        entity_id="1",
        details={"publish_batch_size": row.publish_batch_size},
    )
    await db.commit()
    return await _ingestion_read(db)


async def _endpoint_read(db: AsyncSession, row: WebhookEndpoint) -> WebhookEndpointRead:
    ids = list(
        (
            await db.execute(
                select(WebhookEndpointSource.source_id).where(
                    WebhookEndpointSource.endpoint_id == row.id
                )
            )
        )
        .scalars()
        .all()
    )
    return WebhookEndpointRead(
        id=row.id,
        name=row.name,
        url=row.url,
        enabled=row.enabled,
        all_sources=row.all_sources,
        source_ids=ids,
        phone_policy=row.phone_policy,
        secret_configured=row.secret_encrypted is not None,
        revision=row.revision,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _replace_sources(db: AsyncSession, endpoint_id: uuid.UUID, ids: list[uuid.UUID]) -> None:
    unique = list(dict.fromkeys(ids))
    if unique:
        found = set(
            (await db.execute(select(Source.id).where(Source.id.in_(unique)))).scalars().all()
        )
        if found != set(unique):
            raise HTTPException(422, "Una o più fonti non esistono.")
    await db.execute(
        delete(WebhookEndpointSource).where(WebhookEndpointSource.endpoint_id == endpoint_id)
    )
    db.add_all([WebhookEndpointSource(endpoint_id=endpoint_id, source_id=item) for item in unique])


@router.get("/webhook-endpoints", response_model=list[WebhookEndpointRead])
async def list_webhooks(
    db: AsyncSession = Depends(get_db), _admin: User = Depends(require_role("admin"))
):
    rows = (
        (await db.execute(select(WebhookEndpoint).order_by(WebhookEndpoint.name))).scalars().all()
    )
    return [await _endpoint_read(db, row) for row in rows]


@router.post(
    "/webhook-endpoints", response_model=WebhookEndpointRead, status_code=status.HTTP_201_CREATED
)
async def create_webhook(
    payload: WebhookEndpointInput,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin_with_2fa),
):
    row = WebhookEndpoint(
        name=payload.name.strip(),
        url=payload.url,
        enabled=payload.enabled,
        all_sources=payload.all_sources,
        phone_policy=payload.phone_policy,
        secret_encrypted=encrypt_json({"secret": payload.secret}) if payload.secret else None,
    )
    db.add(row)
    await db.flush()
    await _replace_sources(db, row.id, payload.source_ids)
    await log_action(
        db,
        user_id=admin.id,
        action="create_webhook_endpoint",
        entity_type="webhook_endpoint",
        entity_id=str(row.id),
        details={"all_sources": row.all_sources, "phone_policy": row.phone_policy},
    )
    await db.commit()
    await db.refresh(row)
    return await _endpoint_read(db, row)


@router.put("/webhook-endpoints/{endpoint_id}", response_model=WebhookEndpointRead)
async def update_webhook(
    endpoint_id: uuid.UUID,
    payload: WebhookEndpointUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin_with_2fa),
):
    row = await db.get(WebhookEndpoint, endpoint_id)
    if row is None:
        raise HTTPException(404, "Webhook non trovato.")
    row.name, row.url, row.enabled = payload.name.strip(), payload.url, payload.enabled
    row.all_sources, row.phone_policy, row.revision = (
        payload.all_sources,
        payload.phone_policy,
        row.revision + 1,
    )
    if payload.secret:
        row.secret_encrypted = encrypt_json({"secret": payload.secret})
    elif payload.clear_secret:
        row.secret_encrypted = None
    await _replace_sources(db, row.id, payload.source_ids)
    await log_action(
        db,
        user_id=admin.id,
        action="update_webhook_endpoint",
        entity_type="webhook_endpoint",
        entity_id=str(row.id),
    )
    await db.commit()
    await db.refresh(row)
    return await _endpoint_read(db, row)


@router.delete("/webhook-endpoints/{endpoint_id}", status_code=204)
async def delete_webhook(
    endpoint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin_with_2fa),
):
    row = await db.get(WebhookEndpoint, endpoint_id)
    if row is None:
        raise HTTPException(404, "Webhook non trovato.")
    await log_action(
        db,
        user_id=admin.id,
        action="delete_webhook_endpoint",
        entity_type="webhook_endpoint",
        entity_id=str(row.id),
    )
    await db.delete(row)
    await db.commit()


@router.post(
    "/ingestion-settings/sanitize-existing",
    response_model=SanitizationBackfillRead,
    status_code=202,
)
async def sanitize_existing(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin_with_2fa),
):
    from app.workers.tasks_ai import sanitize_existing_advertisements

    await log_action(
        db,
        user_id=admin.id,
        action="start_content_sanitization_backfill",
        entity_type="ingestion_settings",
        entity_id="1",
    )
    await db.commit()
    task = sanitize_existing_advertisements.delay()
    return SanitizationBackfillRead(task_id=task.id)
