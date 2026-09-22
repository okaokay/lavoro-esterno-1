"""Background operational maintenance triggered from Admin consoles."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import distinct, select

from app.models.advertisement import Advertisement
from app.models.operations import SourcePriorityRecalculationJob
from app.models.record import Record
from app.models.sources import Source
from app.services.scrape_ingest import recompute_canonical
from app.workers.celery_app import celery_app
from app.workers.tasks_scraper import SyncSessionLocal


@celery_app.task(
    name="app.workers.tasks_operations.recalculate_source_priority",
    bind=True,
    max_retries=2,
)
def recalculate_source_priority(self, job_id: str) -> dict:
    session = SyncSessionLocal()
    job_uuid = uuid.UUID(job_id)
    try:
        job = session.execute(
            select(SourcePriorityRecalculationJob)
            .where(SourcePriorityRecalculationJob.id == job_uuid)
            .with_for_update()
        ).scalar_one_or_none()
        if job is None:
            return {"status": "missing"}
        if job.status in {"completed", "superseded"}:
            return {"status": job.status, "idempotent": True}
        if job.status == "processing":
            return {"status": "processing", "idempotent": True}
        source = session.get(Source, job.source_id)
        if source is None or source.priority != job.requested_priority:
            job.status = "superseded"
            job.completed_at = datetime.now(UTC)
            session.commit()
            return {"status": "superseded"}

        job.status = "processing"
        job.started_at = job.started_at or datetime.now(UTC)
        # A retry starts the deterministic batch from the beginning. Canonical
        # changes are themselves idempotent, while progress must not be counted
        # twice after a partial failure.
        job.records_processed = 0
        job.canonicals_changed = 0
        record_ids = (
            session.execute(
                select(distinct(Advertisement.record_id)).where(
                    Advertisement.source_id == job.source_id
                )
            )
            .scalars()
            .all()
        )
        job.records_total = len(record_ids)
        session.commit()

        changed = 0
        for record_id in record_ids:
            session.expire_all()
            source = session.get(Source, job.source_id)
            if source is None or source.priority != job.requested_priority:
                job = session.get(SourcePriorityRecalculationJob, job_uuid)
                job.status = "superseded"
                job.completed_at = datetime.now(UTC)
                session.commit()
                return {"status": "superseded"}
            record = session.get(Record, record_id)
            if record and recompute_canonical(session, record):
                changed += 1
            job = session.get(SourcePriorityRecalculationJob, job_uuid)
            job.records_processed += 1
            job.canonicals_changed = changed
            session.commit()

        job = session.get(SourcePriorityRecalculationJob, job_uuid)
        job.status = "completed"
        job.completed_at = datetime.now(UTC)
        session.commit()
        return {"status": "completed", "changed": changed}
    except Exception as exc:
        session.rollback()
        job = session.get(SourcePriorityRecalculationJob, job_uuid)
        if job:
            job.status = "failed"
            job.error_message = "Ricalcolo non completato. Riprovare."
            session.commit()
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=2 ** (self.request.retries + 1)) from exc
        return {"status": "failed"}
    finally:
        session.close()
