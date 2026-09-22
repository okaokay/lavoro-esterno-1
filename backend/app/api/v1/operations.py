"""Admin operational consoles, notifications and sanitized service health."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models.advertisement import Advertisement
from app.models.media import Media
from app.models.operations import (
    MediaClassifierSettings,
    NotificationEvent,
    NotificationRead,
    SourcePriorityRecalculationJob,
)
from app.models.sources import Source
from app.models.users import User
from app.schemas.operations import (
    ClassifierReprocessInput,
    ClassifierReprocessResult,
    ClassifierSettingsRead,
    ClassifierSettingsUpdate,
    ClassifierStats,
    NotificationList,
    NotificationReadOut,
    SourcePriorityJobRead,
    SourcePriorityRead,
    SourcePriorityUpdate,
    SystemComponentRead,
    SystemStatusRead,
)
from app.security.deps import get_current_user, require_admin_with_2fa, require_role
from app.security.redis_client import get_redis
from app.services.audit import log_action

router = APIRouter()
_status_cache: tuple[float, SystemStatusRead] | None = None


async def _classifier_stats(db: AsyncSession) -> ClassifierStats:
    async def grouped(column) -> dict[str, int]:
        rows = (await db.execute(select(column, func.count()).group_by(column))).all()
        return {str(key): count for key, count in rows}

    return ClassifierStats(
        classifications=await grouped(Media.classification),
        processing=await grouped(Media.processing_status),
        reviews=await grouped(Media.review_status),
    )


@router.get("/admin/classifier-settings", response_model=ClassifierSettingsRead)
async def get_classifier_settings(
    db: AsyncSession = Depends(get_db), _user: User = Depends(require_role("admin"))
) -> ClassifierSettingsRead:
    """Restituisce configurazione e statistiche del classificatore media."""
    config = await db.get(MediaClassifierSettings, 1)
    if config is None:
        raise HTTPException(503, "Configurazione classificatore non inizializzata.")
    return ClassifierSettingsRead(
        model_name=config.model_name,
        model_version=config.model_version,
        safe_threshold=config.safe_threshold,
        explicit_threshold=config.explicit_threshold,
        revision=config.revision,
        stats=await _classifier_stats(db),
    )


@router.patch("/admin/classifier-settings", response_model=ClassifierSettingsRead)
async def update_classifier_settings(
    payload: ClassifierSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin_with_2fa),
) -> ClassifierSettingsRead:
    """Aggiorna soglie e modello con lock e revisione ottimistica."""
    config = (
        await db.execute(
            select(MediaClassifierSettings).where(MediaClassifierSettings.id == 1).with_for_update()
        )
    ).scalar_one_or_none()
    if config is None:
        raise HTTPException(503, "Configurazione classificatore non inizializzata.")
    if config.revision != payload.expected_revision:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Configurazione modificata da un altro Admin."
        )
    previous = {"safe": config.safe_threshold, "explicit": config.explicit_threshold}
    config.safe_threshold = payload.safe_threshold
    config.explicit_threshold = payload.explicit_threshold
    config.revision += 1
    await log_action(
        db,
        user_id=admin.id,
        action="update_classifier_settings",
        entity_type="media_classifier_settings",
        entity_id="1",
        details={
            "previous": previous,
            "revision": config.revision,
            "safe": config.safe_threshold,
            "explicit": config.explicit_threshold,
        },
    )
    await db.commit()
    return await get_classifier_settings(db, admin)


@router.post(
    "/admin/classifier-settings/reprocess",
    response_model=ClassifierReprocessResult,
    status_code=202,
)
async def reprocess_classifier_media(
    payload: ClassifierReprocessInput,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin_with_2fa),
) -> ClassifierReprocessResult:
    """Riaccoda in modo limitato i media falliti o da revisionare."""
    condition = (
        Media.processing_status == "failed"
        if payload.scope == "failed"
        else and_(Media.review_status == "required", Media.processing_status != "processing")
    )
    media = (
        (
            await db.execute(
                select(Media).where(condition, Media.review_status != "reviewed").limit(1000)
            )
        )
        .scalars()
        .all()
    )
    ids: list[str] = []
    for item in media:
        item.processing_status = "pending"
        item.processing_error = None
        ids.append(str(item.id))
    await log_action(
        db,
        user_id=admin.id,
        action="bulk_reprocess_media",
        entity_type="media",
        details={"scope": payload.scope, "count": len(ids)},
    )
    await db.commit()
    from app.workers.tasks_media import process_media

    for media_id in ids:
        process_media.delay(media_id, True)
    return ClassifierReprocessResult(scope=payload.scope, queued=len(ids))


@router.get("/admin/source-priorities", response_model=list[SourcePriorityRead])
async def list_source_priorities(
    db: AsyncSession = Depends(get_db), _user: User = Depends(require_role("admin"))
) -> list[SourcePriorityRead]:
    """Elenca priorità delle fonti e impatto sui record canonici."""
    sources = (await db.execute(select(Source).order_by(Source.name))).scalars().all()
    output = []
    for source in sources:
        affected = (
            await db.execute(
                select(func.count(func.distinct(Advertisement.record_id))).where(
                    Advertisement.source_id == source.id
                )
            )
        ).scalar_one()
        latest = (
            await db.execute(
                select(SourcePriorityRecalculationJob)
                .where(SourcePriorityRecalculationJob.source_id == source.id)
                .order_by(SourcePriorityRecalculationJob.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        output.append(
            SourcePriorityRead(
                source_id=source.id,
                name=source.name,
                code=source.slug,
                status=source.status,
                priority=source.priority,
                affected_records=affected,
                latest_job=SourcePriorityJobRead.model_validate(latest) if latest else None,
            )
        )
    return output


@router.patch(
    "/admin/source-priorities/{source_id}", response_model=SourcePriorityJobRead, status_code=202
)
async def update_source_priority(
    source_id: uuid.UUID,
    payload: SourcePriorityUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin_with_2fa),
) -> SourcePriorityJobRead:
    """Modifica la priorità e crea il job persistente di ricalcolo."""
    source = (
        await db.execute(select(Source).where(Source.id == source_id).with_for_update())
    ).scalar_one_or_none()
    if source is None:
        raise HTTPException(404, "Fonte non trovata.")
    previous = source.priority
    source.priority = payload.priority
    job = SourcePriorityRecalculationJob(
        source_id=source.id,
        requested_by_user_id=admin.id,
        previous_priority=previous,
        requested_priority=payload.priority,
    )
    db.add(job)
    await log_action(
        db,
        user_id=admin.id,
        action="update_source_priority",
        entity_type="source",
        entity_id=str(source.id),
        details={"previous": previous, "new": payload.priority},
    )
    await db.commit()
    await db.refresh(job)
    from app.workers.tasks_operations import recalculate_source_priority

    recalculate_source_priority.delay(str(job.id))
    return SourcePriorityJobRead.model_validate(job)


@router.get("/admin/source-priorities/jobs/{job_id}", response_model=SourcePriorityJobRead)
async def get_source_priority_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
) -> SourcePriorityJobRead:
    """Restituisce stato e avanzamento di un ricalcolo priorità."""
    job = await db.get(SourcePriorityRecalculationJob, job_id)
    if job is None:
        raise HTTPException(404, "Job non trovato.")
    return SourcePriorityJobRead.model_validate(job)


def _notification_visibility(user: User):
    if user.role == "admin":
        return True
    if user.role == "operator":
        return or_(
            NotificationEvent.audience.in_(["operator", "all"]),
            NotificationEvent.owner_user_id == user.id,
        )
    return NotificationEvent.audience == "all"


@router.get("/notifications", response_model=NotificationList)
async def list_notifications(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> NotificationList:
    """Elenca le notifiche consentite dal ruolo con lo stato di lettura."""
    visibility = _notification_visibility(user)
    read_join = and_(
        NotificationRead.notification_id == NotificationEvent.id,
        NotificationRead.user_id == user.id,
    )
    stmt = select(NotificationEvent, NotificationRead.read_at).outerjoin(
        NotificationRead, read_join
    )
    if visibility is not True:
        stmt = stmt.where(visibility)
    rows = (await db.execute(stmt.order_by(NotificationEvent.created_at.desc()).limit(30))).all()
    unread_stmt = (
        select(func.count())
        .select_from(NotificationEvent)
        .outerjoin(NotificationRead, read_join)
        .where(NotificationRead.notification_id.is_(None))
    )
    if visibility is not True:
        unread_stmt = unread_stmt.where(visibility)
    unread = (await db.execute(unread_stmt)).scalar_one()
    return NotificationList(
        items=[
            NotificationReadOut(
                id=item.id,
                kind=item.kind,
                severity=item.severity,
                title=item.title,
                message=item.message,
                link=item.link,
                is_read=read_at is not None,
                created_at=item.created_at,
            )
            for item, read_at in rows
        ],
        unread_count=unread,
    )


async def _visible_notification(
    db: AsyncSession, notification_id: uuid.UUID, user: User
) -> NotificationEvent:
    visibility = _notification_visibility(user)
    stmt = select(NotificationEvent).where(NotificationEvent.id == notification_id)
    if visibility is not True:
        stmt = stmt.where(visibility)
    item = (await db.execute(stmt)).scalar_one_or_none()
    if item is None:
        raise HTTPException(404, "Notifica non trovata.")
    return item


@router.post("/notifications/read-all", status_code=204)
async def mark_all_notifications_read(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> None:
    """Segna come lette tutte le notifiche attualmente visibili all'utente."""
    visibility = _notification_visibility(user)
    ids_stmt = select(NotificationEvent.id)
    if visibility is not True:
        ids_stmt = ids_stmt.where(visibility)
    visible_ids = (await db.execute(ids_stmt)).scalars().all()
    existing = set(
        (
            await db.execute(
                select(NotificationRead.notification_id).where(NotificationRead.user_id == user.id)
            )
        ).scalars()
    )
    for notification_id in visible_ids:
        if notification_id not in existing:
            db.add(NotificationRead(notification_id=notification_id, user_id=user.id))
    await db.commit()


@router.post("/notifications/{notification_id}/read", status_code=204)
async def mark_notification_read(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Segna una singola notifica visibile come letta in modo idempotente."""
    await _visible_notification(db, notification_id, user)
    if await db.get(NotificationRead, (notification_id, user.id)) is None:
        db.add(NotificationRead(notification_id=notification_id, user_id=user.id))
        await db.commit()


async def _timed(name: str, check) -> SystemComponentRead:
    started = time.perf_counter()
    try:
        await asyncio.wait_for(check(), timeout=2.0)
        latency = round((time.perf_counter() - started) * 1000)
        return SystemComponentRead(name=name, status="healthy", latency_ms=latency)
    except Exception:
        return SystemComponentRead(
            name=name, status="unavailable", message="Servizio non raggiungibile"
        )


@router.get("/system/status", response_model=SystemStatusRead)
async def system_status(
    db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)
) -> SystemStatusRead:
    """Verifica le dipendenze operative e restituisce risultati sanitizzati e brevemente cached."""
    global _status_cache
    if _status_cache and time.monotonic() - _status_cache[0] < 10:
        return _status_cache[1]

    async def database():
        await db.execute(select(1))

    async def redis():
        await get_redis().ping()

    async def minio():
        from app.services.media_storage import _client

        exists = await asyncio.to_thread(_client().bucket_exists, settings.MINIO_BUCKET)
        if not exists:
            raise RuntimeError("bucket missing")

    async def ollama():
        async with httpx.AsyncClient(timeout=1.8) as client:
            response = await client.get(f"{settings.OLLAMA_ENDPOINT.rstrip('/')}/api/tags")
            response.raise_for_status()

    components = list(
        await asyncio.gather(
            _timed("API", lambda: asyncio.sleep(0)),
            _timed("PostgreSQL", database),
            _timed("Redis", redis),
            _timed("MinIO", minio),
            _timed("Ollama", ollama),
        )
    )

    def inspect_workers():
        from app.workers.celery_app import celery_app

        return celery_app.control.inspect(timeout=1.5).active_queues() or {}

    try:
        workers = await asyncio.wait_for(asyncio.to_thread(inspect_workers), timeout=2.0)
    except Exception:
        workers = {}
    queues = {q.get("name") for entries in workers.values() for q in entries}
    for queue in ("scraping", "media", "ai", "exports"):
        components.append(
            SystemComponentRead(
                name=f"Worker {queue}",
                status="healthy" if queue in queues else "unavailable",
                message=None if queue in queues else "Nessun worker attivo",
            )
        )
    unavailable = sum(c.status == "unavailable" for c in components)
    overall = (
        "healthy"
        if unavailable == 0
        else ("unavailable" if unavailable == len(components) else "degraded")
    )
    now = datetime.now(UTC)
    failed_components = [
        component
        for component in components
        if component.status == "unavailable" and component.name != "PostgreSQL"
    ]
    for component in failed_components:
        await db.execute(
            insert(NotificationEvent)
            .values(
                id=uuid.uuid4(),
                kind="service_unavailable",
                severity="error",
                title="Servizio non disponibile",
                message=f"{component.name} non risponde ai controlli di stato.",
                link="/dashboard",
                audience="all",
                owner_user_id=None,
                dedup_key=f"service:{component.name}:{now.strftime('%Y%m%d%H')}",
                details_json={},
            )
            .on_conflict_do_nothing(index_elements=[NotificationEvent.dedup_key])
        )
    if failed_components:
        await db.commit()
    result = SystemStatusRead(status=overall, checked_at=now, components=components)
    _status_cache = (time.monotonic(), result)
    return result
