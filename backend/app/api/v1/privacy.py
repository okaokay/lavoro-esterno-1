"""Audited Admin-only right-to-erasure workflow."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.advertisement import Advertisement
from app.models.export_jobs import ExportJobRecord
from app.models.media import Media
from app.models.privacy import ErasureRequest
from app.models.record import Record
from app.models.summary_versions import SummaryVersion
from app.models.users import User
from app.schemas.privacy import ErasureRequestCreate, ErasureRequestRead
from app.security.deps import require_admin_with_2fa, require_role
from app.services.audit import log_action
from app.services.phone_crypto import phone_lookup_hash

router = APIRouter()


def _read(row: ErasureRequest) -> ErasureRequestRead:
    return ErasureRequestRead(
        id=row.id,
        record_id=row.record_id,
        status=row.status,
        reason=row.reason,
        authorization_reference=row.authorization_reference,
        impact=row.impact_json,
        result=row.result_json,
        error_message=row.error_message,
        created_at=row.created_at,
        confirmed_at=row.confirmed_at,
        completed_at=row.completed_at,
    )


async def _impact(db: AsyncSession, record_id: uuid.UUID | None) -> dict:
    if record_id is None:
        return {
            "recordCount": 0,
            "advertisementCount": 0,
            "mediaCount": 0,
            "summaryCount": 0,
            "exportCount": 0,
        }
    ads = int(
        await db.scalar(
            select(func.count(Advertisement.id)).where(Advertisement.record_id == record_id)
        )
        or 0
    )
    media = int(
        await db.scalar(
            select(func.count(Media.id))
            .join(Advertisement, Advertisement.id == Media.advertisement_id)
            .where(Advertisement.record_id == record_id)
        )
        or 0
    )
    summaries = int(
        await db.scalar(
            select(func.count(SummaryVersion.id)).where(SummaryVersion.record_id == record_id)
        )
        or 0
    )
    exports = int(
        await db.scalar(
            select(func.count(ExportJobRecord.export_job_id)).where(
                ExportJobRecord.record_id == record_id
            )
        )
        or 0
    )
    return {
        "recordCount": 1,
        "advertisementCount": ads,
        "mediaCount": media,
        "summaryCount": summaries,
        "exportCount": exports,
    }


@router.post("/erasure-requests", response_model=ErasureRequestRead, status_code=201)
async def create_erasure_request(
    payload: ErasureRequestCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin_with_2fa),
) -> ErasureRequestRead:
    """Crea una bozza di cancellazione usando soltanto l'hash del telefono."""
    lookup = phone_lookup_hash(payload.phone)
    record_id = await db.scalar(select(Record.id).where(Record.phone_lookup_hash == lookup))
    request = ErasureRequest(
        phone_lookup_hash=lookup,
        record_id=record_id,
        status="draft",
        reason=payload.reason,
        authorization_reference=payload.authorization_reference,
        requested_by_user_id=admin.id,
        impact_json=await _impact(db, record_id),
    )
    db.add(request)
    await db.flush()
    await log_action(
        db,
        user_id=admin.id,
        action="create_erasure_request",
        entity_type="erasure_request",
        entity_id=str(request.id),
        details=request.impact_json,
    )
    await db.commit()
    await db.refresh(request)
    return _read(request)


@router.get("/erasure-requests", response_model=list[ErasureRequestRead])
async def list_erasure_requests(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
) -> list[ErasureRequestRead]:
    """Elenca le richieste di cancellazione più recenti per gli Admin."""
    rows = (
        await db.execute(
            select(ErasureRequest).order_by(ErasureRequest.created_at.desc()).limit(200)
        )
    ).scalars()
    return [_read(row) for row in rows]


@router.get("/erasure-requests/{request_id}", response_model=ErasureRequestRead)
async def get_erasure_request(
    request_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
) -> ErasureRequestRead:
    """Restituisce una richiesta di cancellazione senza dati telefonici in chiaro."""
    row = await db.get(ErasureRequest, request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Richiesta non trovata.")
    return _read(row)


@router.post(
    "/erasure-requests/{request_id}/confirm",
    response_model=ErasureRequestRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def confirm_erasure_request(
    request_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin_with_2fa),
) -> ErasureRequestRead:
    """Conferma una bozza valida e accoda la cancellazione asincrona."""
    row = await db.get(ErasureRequest, request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Richiesta non trovata.")
    if row.status not in {"draft", "failed"}:
        raise HTTPException(status_code=409, detail="La richiesta non può essere confermata.")
    row.status = "pending"
    row.confirmed_by_user_id = admin.id
    row.confirmed_at = datetime.now(UTC)
    row.error_message = None
    await log_action(
        db,
        user_id=admin.id,
        action="confirm_erasure_request",
        entity_type="erasure_request",
        entity_id=str(row.id),
        details=row.impact_json,
    )
    await db.commit()
    await db.refresh(row)
    from app.workers.tasks_privacy import execute_erasure

    try:
        execute_erasure.delay(str(row.id))
    except Exception:
        row.status = "failed"
        row.error_message = "Worker privacy temporaneamente non disponibile."
        await db.commit()
    return _read(row)
