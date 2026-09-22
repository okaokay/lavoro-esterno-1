"""Nightly DB-aware retention and object-storage lifecycle tasks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.config import settings
from app.workers.celery_app import celery_app
from app.workers.tasks_scraper import SyncSessionLocal


def _client():
    from minio import Minio

    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )


def _remove_keys(keys) -> int:
    client = _client()
    removed = 0
    for key in {key for key in keys if key}:
        client.remove_object(settings.MINIO_BUCKET, key)
        removed += 1
    return removed


def _invalidate_exports(session, record_ids: set) -> int:
    from app.models.export_jobs import ExportJob, ExportJobRecord

    if not record_ids:
        return 0
    job_ids = list(
        session.execute(
            select(ExportJobRecord.export_job_id).where(ExportJobRecord.record_id.in_(record_ids))
        ).scalars()
    )
    if not job_ids:
        return 0
    jobs = list(session.execute(select(ExportJob).where(ExportJob.id.in_(job_ids))).scalars())
    _remove_keys(job.object_key for job in jobs)
    session.execute(delete(ExportJob).where(ExportJob.id.in_(job_ids)))
    return len(jobs)


@celery_app.task(name="app.workers.tasks_maintenance.cleanup_expired_data")
def cleanup_expired_data() -> dict:
    from app.models.advertisement import Advertisement
    from app.models.audit_log import AuditLog
    from app.models.export_jobs import ExportJob
    from app.models.integrations import ScrapeRunPayload, WebhookDelivery
    from app.models.media import Media
    from app.models.operations import NotificationEvent
    from app.models.record import Record
    from app.models.scrape_runs import ScrapeRun
    from app.services.scrape_ingest import recompute_canonical

    now = datetime.now(UTC)
    session = SyncSessionLocal()
    result = {
        "deleted_audit_log": 0,
        "deleted_technical_logs": 0,
        "deleted_media": 0,
        "deleted_advertisements": 0,
        "deleted_records": 0,
        "deleted_exports": 0,
        "deleted_notifications": 0,
        "deleted_webhook_payloads": 0,
    }
    try:
        if settings.MEDIA_RETENTION_DAYS > 0:
            cutoff = now - timedelta(days=settings.MEDIA_RETENTION_DAYS)
            media_rows = list(
                session.execute(
                    select(Media, Advertisement.record_id)
                    .join(Advertisement, Advertisement.id == Media.advertisement_id)
                    .where(Media.created_at < cutoff)
                    .limit(500)
                ).all()
            )
            if media_rows:
                record_ids = {record_id for _, record_id in media_rows}
                result["deleted_exports"] += _invalidate_exports(session, record_ids)
                _remove_keys(
                    key
                    for media, _ in media_rows
                    for key in (
                        media.original_object_key,
                        media.display_object_key,
                        media.thumbnail_object_key,
                        media.derived_object_key,
                    )
                )
                for media, _ in media_rows:
                    session.delete(media)
                result["deleted_media"] = len(media_rows)

        if settings.ADVERTISEMENT_RETENTION_DAYS > 0:
            cutoff = now - timedelta(days=settings.ADVERTISEMENT_RETENTION_DAYS)
            ads = list(
                session.execute(
                    select(Advertisement).where(Advertisement.last_seen_at < cutoff).limit(500)
                ).scalars()
            )
            affected = {ad.record_id for ad in ads}
            result["deleted_exports"] += _invalidate_exports(session, affected)
            for ad in ads:
                media = list(
                    session.execute(select(Media).where(Media.advertisement_id == ad.id)).scalars()
                )
                _remove_keys(
                    key
                    for item in media
                    for key in (
                        item.original_object_key,
                        item.display_object_key,
                        item.thumbnail_object_key,
                        item.derived_object_key,
                    )
                )
                record = session.get(Record, ad.record_id)
                if record and record.canonical_ad_id == ad.id:
                    record.canonical_ad_id = None
                    session.flush()
                session.delete(ad)
                session.flush()
                if record:
                    remaining = session.scalar(
                        select(Advertisement.id)
                        .where(Advertisement.record_id == record.id)
                        .limit(1)
                    )
                    if remaining is None:
                        session.delete(record)
                        result["deleted_records"] += 1
                    else:
                        recompute_canonical(session, record)
            result["deleted_advertisements"] = len(ads)

        if settings.TECHNICAL_LOG_RETENTION_DAYS > 0:
            cutoff = now - timedelta(days=settings.TECHNICAL_LOG_RETENTION_DAYS)
            result["deleted_technical_logs"] = session.execute(
                delete(ScrapeRun).where(
                    ScrapeRun.finished_at.is_not(None), ScrapeRun.finished_at < cutoff
                )
            ).rowcount

        if settings.AUDIT_LOG_RETENTION_DAYS > 0:
            cutoff = now - timedelta(days=settings.AUDIT_LOG_RETENTION_DAYS)
            result["deleted_audit_log"] = session.execute(
                delete(AuditLog).where(AuditLog.created_at < cutoff)
            ).rowcount

        if settings.NOTIFICATION_RETENTION_DAYS > 0:
            cutoff = now - timedelta(days=settings.NOTIFICATION_RETENTION_DAYS)
            result["deleted_notifications"] = session.execute(
                delete(NotificationEvent).where(NotificationEvent.created_at < cutoff)
            ).rowcount

        # Webhook payloads contain the complete sanitized result of a run and
        # therefore follow the same 90-day technical retention as scrape runs.
        webhook_cutoff = now - timedelta(days=90)
        session.execute(
            delete(WebhookDelivery).where(WebhookDelivery.created_at < webhook_cutoff)
        )
        result["deleted_webhook_payloads"] = session.execute(
            delete(ScrapeRunPayload).where(ScrapeRunPayload.created_at < webhook_cutoff)
        ).rowcount

        expired = list(
            session.execute(
                select(ExportJob)
                .where(ExportJob.expires_at.is_not(None), ExportJob.expires_at < now)
                .limit(500)
            ).scalars()
        )
        _remove_keys(job.object_key for job in expired)
        for job in expired:
            session.delete(job)
        result["deleted_exports"] += len(expired)
        session.add(
            AuditLog(
                user_id=None,
                action="retention_cleanup",
                entity_type="system",
                details_json={key: value for key, value in result.items() if value},
            )
        )
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@celery_app.task(name="app.workers.tasks_maintenance.cleanup_orphan_media_objects")
def cleanup_orphan_media_objects() -> dict:
    from app.models.export_jobs import ExportJob
    from app.models.media import Media

    session = SyncSessionLocal()
    deleted_media = 0
    deleted_exports = 0
    try:
        media_rows = session.execute(
            select(
                Media.original_object_key,
                Media.display_object_key,
                Media.thumbnail_object_key,
                Media.derived_object_key,
            )
        ).all()
        referenced_media = {key for row in media_rows for key in row if key}
        referenced_exports = set(
            session.execute(
                select(ExportJob.object_key).where(ExportJob.object_key.is_not(None))
            ).scalars()
        )
        now = datetime.now(UTC)
        client = _client()
        if not client.bucket_exists(settings.MINIO_BUCKET):
            return {"deleted_orphan_media_objects": 0, "deleted_orphan_export_objects": 0}
        for item in client.list_objects(settings.MINIO_BUCKET, prefix="media/", recursive=True):
            cutoff = now - timedelta(hours=settings.MEDIA_ORPHAN_GRACE_HOURS)
            if (
                item.object_name not in referenced_media
                and item.last_modified
                and item.last_modified < cutoff
            ):
                client.remove_object(settings.MINIO_BUCKET, item.object_name)
                deleted_media += 1
        for item in client.list_objects(settings.MINIO_BUCKET, prefix="exports/", recursive=True):
            cutoff = now - timedelta(hours=settings.EXPORT_ORPHAN_GRACE_HOURS)
            if (
                item.object_name not in referenced_exports
                and item.last_modified
                and item.last_modified < cutoff
            ):
                client.remove_object(settings.MINIO_BUCKET, item.object_name)
                deleted_exports += 1
        return {
            "deleted_orphan_media_objects": deleted_media,
            "deleted_orphan_export_objects": deleted_exports,
        }
    finally:
        session.close()


@celery_app.task(name="app.workers.tasks_maintenance.configure_media_lifecycle")
def configure_media_lifecycle() -> dict:
    from minio.commonconfig import ENABLED, Filter
    from minio.lifecycleconfig import (
        AbortIncompleteMultipartUpload,
        Expiration,
        LifecycleConfig,
        Rule,
    )

    client = _client()
    if not client.bucket_exists(settings.MINIO_BUCKET):
        client.make_bucket(settings.MINIO_BUCKET)
    rule = Rule(
        ENABLED,
        rule_filter=Filter(prefix="tmp/"),
        rule_id="temporary-media-one-day",
        expiration=Expiration(days=1),
        abort_incomplete_multipart_upload=AbortIncompleteMultipartUpload(days_after_initiation=1),
    )
    client.set_bucket_lifecycle(settings.MINIO_BUCKET, LifecycleConfig([rule]))
    return {"configured": True, "temporary_expiry_days": 1}
