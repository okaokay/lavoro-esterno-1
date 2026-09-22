"""Celery tasks for persistent manual and fixed-delay source scraping."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _sync_database_url() -> str:
    if settings.DATABASE_URL_SYNC:
        return settings.DATABASE_URL_SYNC
    return settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://")


_sync_engine = create_engine(_sync_database_url(), pool_pre_ping=True)
SyncSessionLocal = sessionmaker(bind=_sync_engine, class_=Session, expire_on_commit=False)


def _set_next_after_completion(source, finished_at: datetime) -> None:
    source.last_completed_scrape_at = finished_at
    if (
        source.automatic_scraping_enabled
        and source.enabled
        and source.scrape_config
        and source.scrape_interval_minutes
    ):
        source.next_scrape_at = finished_at + timedelta(minutes=source.scrape_interval_minutes)
        source.last_schedule_skip_reason = None
    else:
        source.next_scrape_at = None


def _new_pending_run(source_id: uuid.UUID, trigger_type: str, scheduled_for=None):
    from app.models.scrape_runs import ScrapeRun

    return ScrapeRun(
        source_id=source_id,
        status="pending",
        queued_at=datetime.now(UTC),
        trigger_type=trigger_type,
        scheduled_for=scheduled_for,
        celery_task_id=str(uuid.uuid4()),
    )


def _publish(run) -> None:
    run_scrape_source.apply_async(
        args=[str(run.source_id), str(run.id)], task_id=run.celery_task_id
    )


@celery_app.task(name="app.workers.tasks_scraper.dispatch_due_source_scrapes")
def dispatch_due_source_scrapes() -> dict:
    """Recover stuck dispatches, close stale runs and queue due sources."""
    from app.models.scrape_runs import ScrapeRun
    from app.models.sources import Source
    from app.services.notifications import create_notification

    now = datetime.now(UTC)
    pending_cutoff = now - timedelta(minutes=settings.SCRAPE_PENDING_RETRY_MINUTES)
    # Celery hard-kills this task one minute after the configured limit.
    # The extra grace prevents a replacement from overlapping that process.
    stale_cutoff = now - timedelta(hours=settings.SCRAPE_STALE_HOURS, minutes=5)
    session = SyncSessionLocal()
    publishable = []
    stale_count = 0
    try:
        stale_runs = (
            session.execute(
                select(ScrapeRun)
                .where(ScrapeRun.status == "running", ScrapeRun.started_at < stale_cutoff)
                .with_for_update(skip_locked=True)
            )
            .scalars()
            .all()
        )
        for run in stale_runs:
            source = session.get(Source, run.source_id)
            run.status = "failed"
            run.finished_at = now
            run.errors_count += 1
            if source is not None:
                source.status = "degraded"
                _set_next_after_completion(source, now)
                source.last_schedule_skip_reason = "stale_run_closed"
                create_notification(
                    session,
                    kind="scrape_stale",
                    severity="error",
                    title="Scraping interrotto",
                    message=f"Lo scan della fonte {source.name} ha superato il tempo massimo.",
                    link=f"/sources?source={source.id}",
                    audience="operator",
                    dedup_key=f"scrape_stale:{run.id}",
                )
            stale_count += 1

        retry_runs = (
            session.execute(
                select(ScrapeRun)
                .where(ScrapeRun.status == "pending", ScrapeRun.queued_at <= pending_cutoff)
                .with_for_update(skip_locked=True)
                .limit(settings.SCRAPE_SCHEDULER_BATCH_SIZE)
            )
            .scalars()
            .all()
        )
        for run in retry_runs:
            run.queued_at = now
            publishable.append(run)

        remaining = max(0, settings.SCRAPE_SCHEDULER_BATCH_SIZE - len(publishable))
        due_sources = (
            session.execute(
                select(Source)
                .where(
                    Source.automatic_scraping_enabled.is_(True),
                    Source.enabled.is_(True),
                    Source.scrape_config.is_not(None),
                    Source.next_scrape_at.is_not(None),
                    Source.next_scrape_at <= now,
                )
                .order_by(Source.next_scrape_at, Source.id)
                .with_for_update(skip_locked=True)
                .limit(remaining)
            )
            .scalars()
            .all()
        )
        for source in due_sources:
            active = session.scalar(
                select(ScrapeRun.id).where(
                    ScrapeRun.source_id == source.id,
                    ScrapeRun.status.in_(("pending", "running")),
                )
            )
            if active is not None:
                source.next_scrape_at = None
                source.last_schedule_skip_reason = "active_run"
                continue
            scheduled_for = source.next_scrape_at
            run = _new_pending_run(source.id, "scheduled", scheduled_for)
            session.add(run)
            session.flush()
            source.next_scrape_at = None
            source.last_scheduled_at = now
            source.last_schedule_skip_reason = None
            publishable.append(run)
        session.commit()

        published = 0
        for run in publishable:
            try:
                _publish(run)
                published += 1
            except Exception:  # broker outage: pending row will be retried
                logger.exception("Impossibile pubblicare il run di scraping %s.", run.id)
        return {"published": published, "stale_closed": stale_count}
    finally:
        session.close()


@celery_app.task(
    name="app.workers.tasks_scraper.run_scrape_source",
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=settings.SCRAPE_STALE_HOURS * 3600,
    time_limit=settings.SCRAPE_STALE_HOURS * 3600 + 60,
)
def run_scrape_source(self, source_id: str, run_id: str | None = None) -> dict:
    """Atomically claim and execute one previously persisted scrape run."""
    from app.models.proxies import ScrapeRunProxyAttempt
    from app.models.scrape_errors import ScrapeError
    from app.models.scrape_runs import ScrapeRun
    from app.models.sources import Source
    from app.services.notifications import create_notification
    from app.services.proxy_rotation import (
        ProxyPoolUnavailableError,
        apply_proxy_event,
        reserve_proxy_candidates,
    )
    from app.services.scrape_ingest import (
        CollectionResult,
        ScrapeErrorDetail,
        collect_ads,
        persist_collected_ads,
    )

    source_uuid = uuid.UUID(source_id)
    session = SyncSessionLocal()
    try:
        source = session.get(Source, source_uuid)
        if source is None:
            return {"status": "failed", "reason": "source_not_found"}

        if run_id is None:  # compatibility for tasks queued before this migration
            active = session.scalar(
                select(ScrapeRun.id).where(
                    ScrapeRun.source_id == source.id,
                    ScrapeRun.status.in_(("pending", "running")),
                )
            )
            if active is not None:
                return {"status": "ignored", "reason": "active_run"}
            run = _new_pending_run(source.id, "manual")
            session.add(run)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                return {"status": "ignored", "reason": "active_run"}
            run_id = str(run.id)

        run = session.execute(
            select(ScrapeRun).where(ScrapeRun.id == uuid.UUID(run_id)).with_for_update()
        ).scalar_one_or_none()
        if run is None or run.source_id != source.id:
            return {"status": "failed", "reason": "run_not_found"}
        if run.status != "pending":
            return {"status": "ignored", "reason": "already_claimed"}
        run.status = "running"
        run.started_at = datetime.now(UTC)
        source.next_scrape_at = None
        session.commit()

        outcome: dict = {}
        collection = None
        webhook_delivery_ids: list[str] = []
        try:
            if not source.enabled:
                raise RuntimeError("source_disabled")
            if not source.scrape_config:
                raise RuntimeError("configuration_missing")
            try:
                proxy_candidates = (
                    reserve_proxy_candidates(session, source.proxy_pool_id)
                    if source.proxy_pool_id
                    else []
                )
                from app.models.integrations import IngestionSettings
                from app.services.content_sanitizer import (
                    ContentSanitizationError,
                    sanitize_normalized,
                )

                ingestion = session.get(IngestionSettings, 1)
                batch_size = ingestion.publish_batch_size if ingestion else 50
                pending_batch = []
                published_ads = []
                sanitization_errors = []
                persistence_errors = []
                aggregate = {
                    "items_new": 0,
                    "items_updated": 0,
                    "items_unchanged": 0,
                    "media_ids": [],
                }

                def publish_pending_batch() -> None:
                    if not pending_batch:
                        return
                    partial = persist_collected_ads(
                        session,
                        source,
                        CollectionResult(ads=list(pending_batch)),
                        run.id,
                        batch_size=batch_size,
                    )
                    for key in ("items_new", "items_updated", "items_unchanged"):
                        aggregate[key] += partial[key]
                    aggregate["media_ids"].extend(partial["media_ids"])
                    persistence_errors.extend(partial["errors"])
                    pending_batch.clear()

                def sanitize_and_stage(collected) -> bool:
                    try:
                        sanitized = sanitize_normalized(
                            session, collected.normalized, source.scrape_config or {}
                        )
                    except ContentSanitizationError as exc:
                        sanitization_errors.append(
                            ScrapeErrorDetail(
                                url=collected.normalized.get("source_url") or source.base_url,
                                message=str(exc),
                                code=exc.error_code,
                            )
                        )
                        return False
                    collected.normalized = sanitized.normalized
                    collected.original_content_encrypted = sanitized.original_encrypted
                    collected.sanitization_metadata = sanitized.metadata
                    pending_batch.append(collected)
                    published_ads.append(collected)
                    if len(pending_batch) >= batch_size:
                        publish_pending_batch()
                    return True

                try:
                    collection = asyncio.run(
                        collect_ads(source, proxy_candidates, on_ad=sanitize_and_stage)
                    )
                    # A run with fewer ads than the configured threshold still
                    # publishes its final partial batch.
                    publish_pending_batch()
                except Exception:
                    # Full batches may already be committed. Keep their safe,
                    # sanitized items available to the final failed-run webhook.
                    collection = CollectionResult(
                        ads=published_ads,
                        errors=list(sanitization_errors) + list(persistence_errors),
                    )
                    outcome = {
                        **aggregate,
                        "items_found": len(collection.ads) + len(collection.errors),
                        "errors": collection.errors,
                        "errors_count": len(collection.errors),
                        "pages_visited": 0,
                        "pagination_mode": None,
                        "pagination_stop_reason": "unexpected_error",
                        "proxy_events": [],
                    }
                    raise

                all_errors = (
                    list(collection.errors)
                    + sanitization_errors
                    + persistence_errors
                )
                outcome = {
                    **aggregate,
                    "items_found": len(collection.ads) + len(all_errors),
                    "errors": all_errors,
                    "errors_count": len(all_errors),
                    "pages_visited": collection.discovery_diagnostics.pages_visited,
                    "pagination_mode": collection.discovery_diagnostics.pagination_mode,
                    "pagination_stop_reason": collection.discovery_diagnostics.stop_reason,
                    "proxy_events": collection.proxy_events,
                }
            except ProxyPoolUnavailableError:
                run.status = "failed"
                run.errors_count += 1
                run.proxy_stop_reason = "pool_unavailable"
                session.add(
                    ScrapeError(
                        scrape_run_id=run.id,
                        url=source.base_url,
                        error_message="Nessun proxy sano disponibile; accesso diretto bloccato.",
                    )
                )
                create_notification(
                    session,
                    kind="proxy_pool_exhausted",
                    severity="error",
                    title="Pool proxy non disponibile",
                    message=f"La fonte {source.name} non dispone di un proxy utilizzabile.",
                    link=f"/settings/proxies?source={source.id}",
                    audience="operator",
                    dedup_key=f"proxy_pool_exhausted:{run.id}",
                )
            else:
                run.items_found = outcome["items_found"]
                run.items_new = outcome["items_new"]
                run.items_updated = outcome["items_updated"]
                run.items_unchanged = outcome["items_unchanged"]
                run.errors_count = outcome["errors_count"]
                run.pages_visited = outcome["pages_visited"]
                run.pagination_mode = outcome["pagination_mode"]
                run.pagination_stop_reason = outcome["pagination_stop_reason"]
                events = outcome.get("proxy_events", [])
                run.proxy_attempts_count = len(events)
                endpoint_order = list(dict.fromkeys(event.endpoint_id for event in events))
                run.proxy_rotations_count = max(0, len(endpoint_order) - 1)
                if events and events[-1].outcome == "failed":
                    run.proxy_stop_reason = "pool_exhausted"
                for attempt_number, event in enumerate(events, start=1):
                    apply_proxy_event(session, event)
                    session.add(
                        ScrapeRunProxyAttempt(
                            scrape_run_id=run.id,
                            proxy_endpoint_id=event.endpoint_id,
                            attempted_at=datetime.now(UTC),
                            attempt_number=attempt_number,
                            operation=event.operation,
                            outcome=event.outcome,
                            latency_ms=event.latency_ms,
                            failure_category=event.failure_category,
                        )
                    )
                if run.proxy_stop_reason == "pool_exhausted":
                    create_notification(
                        session,
                        kind="proxy_pool_exhausted",
                        severity="error",
                        title="Pool proxy esaurito",
                        message=f"I proxy disponibili per {source.name} hanno fallito.",
                        link=f"/settings/proxies?source={source.id}",
                        audience="operator",
                        dedup_key=f"proxy_pool_exhausted:{run.id}",
                    )
                run.status = (
                    "failed"
                    if (
                        outcome["items_new"] == 0
                        and outcome["items_updated"] == 0
                        and outcome["items_unchanged"] == 0
                        and outcome["errors"]
                    )
                    else "completed"
                )
                from app.services.scrape_ingest import encode_scrape_error_message

                for error in outcome["errors"]:
                    session.add(
                        ScrapeError(
                            scrape_run_id=run.id,
                            url=error.url,
                            error_message=encode_scrape_error_message(error.code, error.message),
                        )
                    )
        except Exception as exc:  # keep every claimed run terminal and schedulable
            logger.exception("Errore durante lo scraping della fonte '%s'.", source.slug)
            run.status = "failed"
            run.errors_count += 1
            safe_reason = (
                str(exc)
                if str(exc) in {"source_disabled", "configuration_missing"}
                else "unexpected_error"
            )
            session.add(
                ScrapeError(
                    scrape_run_id=run.id,
                    url=source.base_url,
                    error_message=f"Scraping interrotto: {safe_reason}.",
                )
            )

        # The Admin may have changed or disabled the schedule while this
        # potentially long scan was running. Reload only schedule eligibility
        # fields so the fixed-delay deadline always uses the current revision.
        session.refresh(
            source,
            attribute_names=[
                "automatic_scraping_enabled",
                "enabled",
                "scrape_config",
                "scrape_interval_minutes",
            ],
        )
        finished_at = datetime.now(UTC)
        run.finished_at = finished_at
        _set_next_after_completion(source, finished_at)
        if run.status == "failed":
            if source.enabled:
                source.status = "degraded"
            create_notification(
                session,
                kind="scrape_failed",
                severity="error",
                title="Scraping non riuscito",
                message=f"La fonte {source.name} non ha completato l'ultimo scan.",
                link=f"/sources?source={source.id}",
                audience="operator",
                dedup_key=f"scrape_failed:{run.id}",
            )
        elif run.errors_count:
            if source.enabled:
                source.status = "degraded"
            create_notification(
                session,
                kind="source_degraded",
                severity="warning",
                title="Fonte degradata",
                message=f"La fonte {source.name} ha completato lo scan con errori.",
                link=f"/sources?source={source.id}",
                audience="operator",
                dedup_key=f"source_degraded:{run.id}",
            )
        elif source.enabled:
            source.status = "healthy"
        try:
            from app.services.webhook_outbox import enqueue_run_webhooks

            webhook_delivery_ids = enqueue_run_webhooks(session, source, run, collection, outcome)
        except Exception:
            logger.exception("Impossibile creare l'outbox webhook per il run %s.", run.id)
        session.commit()

        if source.scrape_config:
            from app.workers.tasks_media import process_media

            for media_id in outcome.get("media_ids", []):
                process_media.delay(media_id)
        if webhook_delivery_ids:
            from app.workers.tasks_webhooks import deliver_webhook

            for delivery_id in webhook_delivery_ids:
                deliver_webhook.delay(delivery_id)
        return {"status": run.status, "run_id": str(run.id)}
    finally:
        session.close()
