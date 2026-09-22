"""Idempotent execution of confirmed GDPR erasure requests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select, update

from app.models.advertisement import Advertisement
from app.models.audit_log import AuditLog
from app.models.export_jobs import ExportJob, ExportJobRecord
from app.models.media import Media
from app.models.privacy import ErasureRequest, SuppressionEntry
from app.models.record import Record
from app.services.media_storage import remove_object
from app.workers.celery_app import celery_app
from app.workers.tasks_scraper import SyncSessionLocal


@celery_app.task(name="app.workers.tasks_privacy.execute_erasure")
def execute_erasure(request_id: str) -> dict:
    request_uuid = uuid.UUID(request_id)
    session = SyncSessionLocal()
    claimed = session.execute(
        update(ErasureRequest)
        .where(ErasureRequest.id == request_uuid, ErasureRequest.status == "pending")
        .values(status="processing", error_message=None)
        .returning(ErasureRequest.id)
    ).scalar_one_or_none()
    session.commit()
    if claimed is None:
        row = session.get(ErasureRequest, request_uuid)
        session.close()
        return {"status": row.status if row else "missing", "idempotent": True}
    try:
        row = session.get(ErasureRequest, request_uuid)
        suppression = session.execute(
            select(SuppressionEntry).where(
                SuppressionEntry.phone_lookup_hash == row.phone_lookup_hash
            )
        ).scalar_one_or_none()
        if suppression is None:
            session.add(
                SuppressionEntry(phone_lookup_hash=row.phone_lookup_hash, erasure_request_id=row.id)
            )
            session.commit()

        record_id = row.record_id
        export_ids: list[uuid.UUID] = []
        media_count = 0
        if record_id:
            export_ids = list(
                session.execute(
                    select(ExportJobRecord.export_job_id).where(
                        ExportJobRecord.record_id == record_id
                    )
                ).scalars()
            )
            export_jobs = (
                list(
                    session.execute(select(ExportJob).where(ExportJob.id.in_(export_ids))).scalars()
                )
                if export_ids
                else []
            )
            media_rows = list(
                session.execute(
                    select(Media)
                    .join(Advertisement, Advertisement.id == Media.advertisement_id)
                    .where(Advertisement.record_id == record_id)
                ).scalars()
            )
            for export in export_jobs:
                if export.object_key:
                    remove_object(export.object_key)
            for media in media_rows:
                for key in {
                    media.original_object_key,
                    media.display_object_key,
                    media.thumbnail_object_key,
                    media.derived_object_key,
                }:
                    if key:
                        remove_object(key)
                media_count += 1
            if export_ids:
                session.execute(delete(ExportJob).where(ExportJob.id.in_(export_ids)))
            record = session.get(Record, record_id)
            if record:
                record.canonical_ad_id = None
                session.flush()
                session.delete(record)

        row.result_json = {
            "recordDeleted": bool(record_id),
            "mediaDeleted": media_count,
            "exportsInvalidated": len(export_ids),
        }
        row.record_id = None
        row.status = "completed"
        row.completed_at = datetime.now(UTC)
        session.add(
            AuditLog(
                user_id=row.confirmed_by_user_id,
                action="complete_erasure_request",
                entity_type="erasure_request",
                entity_id=str(row.id),
                details_json=row.result_json,
            )
        )
        session.commit()
        return row.result_json
    except Exception:
        session.rollback()
        row = session.get(ErasureRequest, request_uuid)
        if row:
            row.status = "failed"
            row.error_message = (
                "Cancellazione non completata; ripetere dopo aver verificato lo storage."
            )
            session.commit()
        raise
    finally:
        session.close()
