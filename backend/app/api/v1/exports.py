"""Asynchronous, explicitly scoped export API."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import false, func, insert, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.config import settings
from app.db import get_db
from app.models.advertisement import Advertisement
from app.models.export_jobs import ExportJob, ExportJobRecord
from app.models.media import Media
from app.models.record import Record
from app.models.sources import Source
from app.models.users import User
from app.schemas.exports import DownloadUrlResponse, ExportFilters, ExportJobCreate, ExportJobOut
from app.security.deps import require_role
from app.services.audit import log_action
from app.services.media_storage import presigned_download_url
from app.services.phone_crypto import PhoneCryptoError, phone_lookup_hash
from app.services.record_search import VERIFIED_CONFIDENCE_THRESHOLD

router = APIRouter()
_RECENT_EXPORTS_LIMIT = 100


def _can_view_clear_phone(user: User) -> bool:
    return user.role == "admin" or user.can_view_clear_phone


def _expiry_from(now: datetime) -> datetime | None:
    if settings.EXPORT_RETENTION_DAYS <= 0:
        return None
    return now + timedelta(days=settings.EXPORT_RETENTION_DAYS)


def _to_out(job: ExportJob, email: str) -> ExportJobOut:
    return ExportJobOut(
        id=job.id,
        type=job.type,
        status=job.status,
        progress_pct=job.progress_percent,
        requested_by=email,
        requested_at=job.requested_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        expires_at=job.expires_at,
        record_count=job.record_count,
        estimated_uncompressed_bytes=job.estimated_uncompressed_bytes,
        archive_size_bytes=job.archive_size_bytes,
        phone_visibility="clear" if job.include_clear_phone else "masked",
        error_message=job.error_message,
        # Signed download URLs are issued only by the dedicated audited
        # endpoint, never as a side effect of listing jobs.
        download_url=None,
    )


def _scope_select(scope: str, filters: ExportFilters | None):
    """Build the frozen scope query without materializing every UUID in Python."""
    if scope == "all":
        return select(Record.id).order_by(Record.id)
    assert filters is not None
    canonical = aliased(Advertisement)
    stmt = select(Record.id).outerjoin(canonical, canonical.id == Record.canonical_ad_id)
    if filters.phone:
        try:
            lookup = phone_lookup_hash(filters.phone)
        except PhoneCryptoError as exc:
            raise HTTPException(status_code=422, detail="Filtro telefono non valido.") from exc
        stmt = stmt.where(Record.phone_lookup_hash == lookup)
    if filters.source:
        source_match = (
            select(Advertisement.id)
            .join(Source, Source.id == Advertisement.source_id)
            .where(
                Advertisement.record_id == Record.id,
                or_(Source.slug == filters.source, Source.name == filters.source),
            )
        )
        stmt = stmt.where(source_match.exists())
    if filters.date_from:
        stmt = stmt.where(
            select(Advertisement.id)
            .where(
                Advertisement.record_id == Record.id,
                Advertisement.last_seen_at >= filters.date_from,
            )
            .exists()
        )
    if filters.date_to:
        stmt = stmt.where(
            select(Advertisement.id)
            .where(
                Advertisement.record_id == Record.id,
                Advertisement.first_seen_at <= filters.date_to,
            )
            .exists()
        )
    if filters.status == "verified":
        stmt = stmt.where(canonical.confidence >= VERIFIED_CONFIDENCE_THRESHOLD)
    elif filters.status == "unverified":
        stmt = stmt.where(
            or_(canonical.confidence < VERIFIED_CONFIDENCE_THRESHOLD, canonical.id.is_(None))
        )
    elif filters.status == "flagged":
        stmt = stmt.where(false())
    return stmt.order_by(Record.id)


async def _resolve_selected_scope(
    db: AsyncSession, record_ids: list[uuid.UUID]
) -> list[uuid.UUID]:
    rows = (
        (await db.execute(select(Record.id).where(Record.id.in_(record_ids)))).scalars().all()
    )
    if len(rows) != len(record_ids):
        raise HTTPException(status_code=404, detail="Uno o più record non esistono.")
    return list(rows)


async def _estimate_media_bytes(db: AsyncSession, record_ids: list[uuid.UUID]) -> int:
    value = await db.scalar(
        select(func.coalesce(func.sum(Media.file_size_bytes), 0))
        .join(Advertisement, Advertisement.id == Media.advertisement_id)
        .where(Advertisement.record_id.in_(record_ids), Media.is_current.is_(True))
    )
    return int(value or 0)


async def _get_visible_job(db: AsyncSession, job_id: uuid.UUID, user: User) -> ExportJob:
    job = await db.get(ExportJob, job_id)
    if job is None or (user.role != "admin" and job.requested_by_user_id != user.id):
        raise HTTPException(status_code=404, detail="Export non trovato.")
    return job


@router.post("", response_model=ExportJobOut, status_code=status.HTTP_202_ACCEPTED)
async def create_export(
    payload: ExportJobCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
) -> ExportJobOut:
    """Congela lo scope autorizzato e accoda la creazione del pacchetto."""
    scope = payload.scope or "selected"
    scope_statement = None
    if payload.record_ids:
        ids = await _resolve_selected_scope(db, payload.record_ids)
        record_count = len(ids)
    else:
        ids = []
        scope_statement = _scope_select(scope, payload.filters)
        record_count = int(
            await db.scalar(select(func.count()).select_from(scope_statement.subquery())) or 0
        )
    if not record_count:
        raise HTTPException(status_code=422, detail="Lo scope non contiene record.")
    if scope == "selected" and record_count > settings.EXPORT_MAX_RECORDS:
        raise HTTPException(status_code=413, detail="Limite massimo di record superato.")
    estimated = (
        0
        if payload.type == "text_only" or scope in {"filters", "all"}
        else await _estimate_media_bytes(db, ids)
    )
    if estimated > settings.EXPORT_MAX_UNCOMPRESSED_BYTES:
        raise HTTPException(status_code=413, detail="Dimensione massima dell'export superata.")

    clear = _can_view_clear_phone(user)
    now = datetime.now(UTC)
    job = ExportJob(
        record_id=ids[0] if len(ids) == 1 else None,
        type=payload.type,
        status="pending",
        progress_percent=0,
        requested_by_user_id=user.id,
        requested_at=now,
        expires_at=_expiry_from(now),
        manifest_json={
            "scope": scope,
            "filters": payload.filters.model_dump(mode="json") if payload.filters else None,
        },
        record_count=record_count,
        estimated_uncompressed_bytes=estimated,
        include_clear_phone=clear,
    )
    db.add(job)
    await db.flush()
    if scope_statement is not None:
        frozen_scope = scope_statement.subquery()
        await db.execute(
            insert(ExportJobRecord).from_select(
                ["export_job_id", "record_id"],
                select(literal(job.id), frozen_scope.c.id),
            )
        )
    else:
        db.add_all(
            ExportJobRecord(export_job_id=job.id, record_id=record_id) for record_id in ids
        )
    await log_action(
        db,
        user_id=user.id,
        action="create_export",
        entity_type="export_job",
        entity_id=str(job.id),
        details={
            "type": job.type,
            "record_count": record_count,
            "phone_visibility": "clear" if clear else "masked",
            "scope": scope,
        },
    )
    await db.commit()
    await db.refresh(job)

    from app.workers.tasks_exports import generate_export

    try:
        generate_export.delay(str(job.id))
    except Exception:  # broker unavailable: persist a retryable safe state
        job.status = "failed"
        job.error_message = "Worker export temporaneamente non disponibile."
        await db.commit()
    return _to_out(job, user.email)


@router.get("", response_model=list[ExportJobOut])
async def list_exports(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
) -> list[ExportJobOut]:
    """Elenca gli export visibili, limitando gli operatori ai propri job."""
    stmt = select(ExportJob, User.email).join(User, User.id == ExportJob.requested_by_user_id)
    if user.role != "admin":
        stmt = stmt.where(ExportJob.requested_by_user_id == user.id)
    rows = (
        await db.execute(stmt.order_by(ExportJob.requested_at.desc()).limit(_RECENT_EXPORTS_LIMIT))
    ).all()
    return [_to_out(job, email) for job, email in rows]


@router.post("/{job_id}/retry", response_model=ExportJobOut, status_code=status.HTTP_202_ACCEPTED)
async def retry_export(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
) -> ExportJobOut:
    """Riaccoda un export fallito preservandone scope e proprietà."""
    job = await _get_visible_job(db, job_id, user)
    if job.status != "failed":
        raise HTTPException(status_code=400, detail="Solo un export fallito può essere ripetuto.")
    job.status = "pending"
    job.progress_percent = 0
    job.error_message = None
    job.started_at = None
    job.completed_at = None
    job.expires_at = _expiry_from(datetime.now(UTC))
    await log_action(
        db, user_id=user.id, action="retry_export", entity_type="export_job", entity_id=str(job.id)
    )
    await db.commit()
    from app.workers.tasks_exports import generate_export

    try:
        generate_export.delay(str(job.id))
    except Exception:
        job.status = "failed"
        job.error_message = "Worker export temporaneamente non disponibile."
        await db.commit()
    requester = await db.get(User, job.requested_by_user_id)
    return _to_out(job, requester.email if requester else "N/D")


@router.get("/{job_id}/download", response_model=DownloadUrlResponse)
async def get_export_download_url(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
) -> DownloadUrlResponse:
    """Genera un URL temporaneo solo per pacchetti pronti e non scaduti."""
    job = await _get_visible_job(db, job_id, user)
    if job.status != "ready" or not job.object_key:
        raise HTTPException(status_code=409, detail="Il pacchetto non è pronto.")
    if job.expires_at and job.expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=410, detail="Il pacchetto è scaduto.")
    await log_action(
        db,
        user_id=user.id,
        action="download_export",
        entity_type="export_job",
        entity_id=str(job.id),
    )
    await db.commit()
    return DownloadUrlResponse(
        url=presigned_download_url(job.object_key, f"export-{job.id}.zip"),
        expires_at=job.expires_at,
    )
