"""Asynchronous, budget-gated OpenAI summary generation."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime

import redis
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.models.advertisement import Advertisement
from app.models.ai_settings import AIProviderConfig, AISettings
from app.models.audit_log import AuditLog
from app.models.record import Record
from app.models.sources import Source
from app.models.summary_generation_jobs import SummaryGenerationJob
from app.models.summary_versions import SummaryVersion
from app.services.ai_config import REMOTE_PROVIDERS, runtime_config
from app.services.summary_generator import ProviderError, create_summary_provider
from app.workers.celery_app import celery_app
from app.workers.tasks_scraper import SyncSessionLocal

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\s().-]*){8,15}(?!\w)")


@celery_app.task(name="app.workers.tasks_ai.sanitize_existing_advertisements")
def sanitize_existing_advertisements() -> dict:
    """Riprendibile: elabora solo annunci senza envelope originale."""
    from app.models.media import Media
    from app.services.content_sanitizer import ContentSanitizationError, sanitize_normalized
    from app.services.scrape_ingest import (
        _save_version,
        advertisement_content_hash,
        recompute_canonical,
    )

    session = SyncSessionLocal()
    processed = failed = 0
    failures_by_reason: Counter[str] = Counter()
    try:
        rows = session.execute(
            select(Advertisement, Source)
            .join(Source, Source.id == Advertisement.source_id)
            .where(Advertisement.original_content_encrypted.is_(None))
            .order_by(Advertisement.id)
        ).all()
        for advertisement, source in rows:
            normalized = {
                "title": advertisement.title,
                "description": advertisement.description,
                "custom_fields": advertisement.custom_fields or {},
            }
            try:
                result = sanitize_normalized(session, normalized, source.scrape_config or {})
            except ContentSanitizationError as exc:
                failed += 1
                failures_by_reason[exc.error_code] += 1
                continue
            changed_fields = [
                name
                for name in ("title", "description", "custom_fields")
                if normalized[name] != result.normalized.get(name)
            ]
            advertisement.title = result.normalized.get("title")
            advertisement.description = result.normalized.get("description")
            advertisement.custom_fields = result.normalized.get("custom_fields") or {}
            advertisement.original_content_encrypted = result.original_encrypted
            advertisement.sanitization_metadata = result.metadata
            if changed_fields:
                advertisement.content_hash = advertisement_content_hash(result.normalized)
                advertisement.last_changed_at = datetime.now(UTC)
                advertisement.revision += 1
                record = session.get(Record, advertisement.record_id)
                record.content_revision += 1
                media_hashes = list(
                    session.execute(
                        select(Media.sha256).where(
                            Media.advertisement_id == advertisement.id,
                            Media.is_current.is_(True),
                        )
                    )
                    .scalars()
                    .all()
                )
                _save_version(session, advertisement, None, changed_fields, media_hashes)
                recompute_canonical(session, record)
            processed += 1
            if processed % 50 == 0:
                session.commit()
        session.commit()
        session.add(
            AuditLog(
                user_id=None,
                action="content_sanitization_backfill_completed",
                entity_type="ingestion_settings",
                entity_id="1",
                details_json={
                    "processed": processed,
                    "failed": failed,
                    "failures_by_reason": dict(failures_by_reason),
                },
            )
        )
        session.commit()
        return {
            "status": "completed",
            "processed": processed,
            "failed": failed,
            "failures_by_reason": dict(failures_by_reason),
        }
    finally:
        session.close()


class AIDisabledError(RuntimeError):
    pass


def _redis() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def _reserve_budget(
    user_id: uuid.UUID, estimated_tokens: int, ai: AISettings, provider: str
) -> tuple[str, int] | None:
    if ai.user_daily_request_limit <= 0 or ai.provider_requests_per_minute <= 0:
        raise AIDisabledError("AI disabilitata: configurare limiti operativi positivi.")
    if provider in REMOTE_PROVIDERS and ai.global_daily_token_budget <= 0:
        raise AIDisabledError("Provider cloud disabilitato: configurare il budget token.")
    client = _redis()
    day = datetime.now(UTC).strftime("%Y%m%d")
    minute = datetime.now(UTC).strftime("%Y%m%d%H%M")
    user_key = f"ai:user:{user_id}:{day}"
    rpm_key = f"ai:rpm:{provider}:{minute}"
    token_key = f"ai:tokens:cloud:{day}"
    user_count = client.incr(user_key)
    client.expire(user_key, 172800)
    rpm_count = client.incr(rpm_key)
    client.expire(rpm_key, 120)
    if user_count > ai.user_daily_request_limit:
        raise AIDisabledError("Limite giornaliero per utente esaurito.")
    if rpm_count > ai.provider_requests_per_minute:
        raise AIDisabledError("Rate limit AI applicativo raggiunto.")
    if provider not in REMOTE_PROVIDERS:
        return None
    reserved = client.incrby(token_key, estimated_tokens)
    client.expire(token_key, 172800)
    if reserved > ai.global_daily_token_budget:
        client.decrby(token_key, estimated_tokens)
        raise AIDisabledError("Budget token AI giornaliero esaurito.")
    return token_key, estimated_tokens


def _release_reservation(reservation: tuple[str, int] | None) -> None:
    if reservation:
        _redis().decrby(reservation[0], reservation[1])


def _is_retryable_provider_error(exc: Exception) -> bool:
    """Retry transient network, timeout, throttling and provider 5xx failures."""
    if isinstance(exc, ProviderError):
        return exc.retryable
    try:
        from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
    except ImportError:  # pragma: no cover - dependency is mandatory in production
        return False
    if isinstance(exc, (APIConnectionError, APITimeoutError, RateLimitError)):
        return True
    return isinstance(exc, APIStatusError) and exc.status_code >= 500


def _sanitized_input(rows: list[tuple[Advertisement, Source]]) -> tuple[dict, dict[str, str]]:
    source_refs: dict[uuid.UUID, str] = {}
    source_urls: dict[str, str] = {}
    advertisements = []
    for advertisement, source in rows:
        ref = source_refs.setdefault(source.id, f"source-{len(source_refs) + 1}")
        source_urls[ref] = advertisement.source_url
        advertisements.append(
            {
                "source_ref": ref,
                "title": _redact_external_identifiers(advertisement.title or "")[:500],
                "description": _redact_external_identifiers(advertisement.description or "")[:4000],
                "scraped_at": advertisement.scraped_at.isoformat(),
            }
        )
    payload = {"advertisements": advertisements, "forum_snippets": []}
    encoded = json.dumps(payload, ensure_ascii=False)
    if len(encoded) > settings.AI_MAX_INPUT_CHARS:
        raise ValueError("Input riepilogo oltre AI_MAX_INPUT_CHARS.")
    return payload, source_urls


def _redact_external_identifiers(value: str) -> str:
    value = _URL_RE.sub("[URL REDACTED]", value)
    return _PHONE_RE.sub("[PHONE REDACTED]", value)


def summary_input_hash(
    payload: dict,
    provider: str | None = None,
    model: str | None = None,
    prompt_version: str | None = None,
    record_content_revision: int = 0,
) -> str:
    envelope = {
        "provider": provider or "openai",
        "model": model or settings.OPENAI_MODEL,
        "prompt_version": prompt_version or settings.OPENAI_PROMPT_VERSION,
        "payload": payload,
        "record_content_revision": record_content_revision,
    }
    return hashlib.sha256(
        json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


@celery_app.task(name="app.workers.tasks_ai.generate_summary", bind=True, max_retries=3)
def generate_summary(self, job_id: str) -> dict:
    session = SyncSessionLocal()
    job_uuid = uuid.UUID(job_id)
    token_reservation: tuple[str, int] | None = None
    try:
        job = session.get(SummaryGenerationJob, job_uuid)
        if job is None:
            return {"status": "failed", "reason": "job_not_found"}
        if job.status == "completed":
            return {"status": "completed", "job_id": job_id, "idempotent": True}
        job.status = "processing"
        job.started_at = datetime.now(UTC)
        job.error_message = None
        session.commit()

        record = session.get(Record, job.record_id)
        if record is None:
            raise AIDisabledError("Record non disponibile.")
        if record.content_revision != job.record_content_revision:
            raise AIDisabledError(
                "Il record e cambiato dopo la richiesta: rilanciare il riepilogo."
            )

        rows = session.execute(
            select(Advertisement, Source)
            .join(Source, Source.id == Advertisement.source_id)
            .where(Advertisement.record_id == job.record_id)
            .order_by(Advertisement.scraped_at, Advertisement.id)
        ).all()
        ai = session.get(AISettings, 1)
        provider_row = session.execute(
            select(AIProviderConfig).where(AIProviderConfig.provider == job.model_provider)
        ).scalar_one_or_none()
        if ai is None or provider_row is None or not provider_row.enabled:
            raise AIDisabledError("Il provider AI del job non e piu abilitato.")
        if job.provider_config_revision != provider_row.revision:
            raise AIDisabledError("La configurazione AI e cambiata: rilanciare il riepilogo.")
        provider_config = replace(
            runtime_config(provider_row),
            model=job.model_name,
            options={**(provider_row.config_json or {}), "prompt_version": job.prompt_version},
        )
        if job.model_provider in REMOTE_PROVIDERS and not provider_config.api_key:
            raise AIDisabledError("Credenziale del provider AI non configurata.")
        payload, source_urls = _sanitized_input(rows)
        input_hash = summary_input_hash(
            payload,
            job.model_provider,
            job.model_name,
            job.prompt_version,
            job.record_content_revision,
        )
        job.input_hash = input_hash

        cached = session.execute(
            select(SummaryVersion).where(
                SummaryVersion.record_id == job.record_id,
                SummaryVersion.input_hash == input_hash,
                SummaryVersion.model_provider == job.model_provider,
                SummaryVersion.model_name == job.model_name,
                SummaryVersion.prompt_version == job.prompt_version,
            )
        ).scalar_one_or_none()
        if cached is not None:
            job.status = "completed"
            job.result_version = cached.version
            job.cache_hit = True
            job.completed_at = datetime.now(UTC)
            session.commit()
            return {"status": "completed", "job_id": job_id, "cache_hit": True}

        estimated_tokens = max(1, len(json.dumps(payload, ensure_ascii=False)) // 4) + 2000
        token_reservation = _reserve_budget(
            job.requested_by_user_id, estimated_tokens, ai, job.model_provider
        )
        generator = create_summary_provider(provider_config)
        for attempt in range(2):
            try:
                generated = generator.generate_structured(payload)
                if not set(generated.payload.sources) <= set(source_urls):
                    raise ProviderError(
                        "Il provider ha restituito riferimenti a fonti non validi.",
                        validation=True,
                    )
                break
            except ProviderError as exc:
                if not exc.validation or attempt == 1:
                    raise
        result_payload = generated.payload.as_dict()
        result_payload["sources"] = [
            source_urls[ref] for ref in generated.payload.sources if ref in source_urls
        ]

        version_number = (
            session.execute(
                select(func.max(SummaryVersion.version)).where(
                    SummaryVersion.record_id == job.record_id
                )
            ).scalar_one()
            or 0
        ) + 1
        version = SummaryVersion(
            record_id=job.record_id,
            version=version_number,
            summary_json=result_payload,
            model_provider=job.model_provider,
            model_name=job.model_name,
            prompt_version=job.prompt_version,
            input_hash=input_hash,
            input_tokens=generated.input_tokens,
            output_tokens=generated.output_tokens,
            cached_input_tokens=generated.cached_input_tokens,
            generation_job_id=job.id,
            record_content_revision=job.record_content_revision,
        )
        session.add(version)
        job.status = "completed"
        job.result_version = version_number
        job.completed_at = datetime.now(UTC)
        session.add(
            AuditLog(
                user_id=job.requested_by_user_id,
                action="regenerate_ai_summary",
                entity_type="record",
                entity_id=str(job.record_id),
                details_json={
                    "version": version_number,
                    "provider": job.model_provider,
                    "model": job.model_name,
                    "prompt_version": job.prompt_version,
                    "input_tokens": generated.input_tokens,
                    "output_tokens": generated.output_tokens,
                },
            )
        )
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            cached = session.execute(
                select(SummaryVersion).where(
                    SummaryVersion.record_id == job.record_id,
                    SummaryVersion.input_hash == input_hash,
                    SummaryVersion.model_provider == job.model_provider,
                    SummaryVersion.model_name == job.model_name,
                    SummaryVersion.prompt_version == job.prompt_version,
                )
            ).scalar_one()
            job = session.get(SummaryGenerationJob, job_uuid)
            job.status, job.cache_hit = "completed", True
            job.result_version, job.completed_at = cached.version, datetime.now(UTC)
            session.commit()
        if token_reservation:
            actual = generated.input_tokens + generated.output_tokens
            _redis().incrby(token_reservation[0], actual - token_reservation[1])
        return {"status": "completed", "job_id": job_id, "version": job.result_version}
    except AIDisabledError as exc:
        _release_reservation(token_reservation)
        session.rollback()
        job = session.get(SummaryGenerationJob, job_uuid)
        if job:
            job.status, job.error_message = "failed", str(exc)
            job.completed_at = datetime.now(UTC)
            from app.services.notifications import create_notification

            create_notification(
                session,
                kind="ai_failed",
                severity="warning",
                title="Riepilogo AI non generato",
                message="Il job di riepilogo non è stato completato.",
                link=f"/records/{job.record_id}/ai-summary",
                owner_user_id=job.requested_by_user_id,
                dedup_key=f"ai_failed:{job.id}",
            )
            session.commit()
        return {"status": "failed", "job_id": job_id, "reason": str(exc)}
    except Exception as exc:
        _release_reservation(token_reservation)
        session.rollback()
        if _is_retryable_provider_error(exc) and self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=2 ** (self.request.retries + 1)) from exc
        job = session.get(SummaryGenerationJob, job_uuid)
        if job:
            job.status = "failed"
            job.error_message = "Generazione AI non riuscita; consultare i log del worker."
            job.completed_at = datetime.now(UTC)
            from app.services.notifications import create_notification

            create_notification(
                session,
                kind="ai_failed",
                severity="error",
                title="Riepilogo AI non riuscito",
                message="Il worker AI non ha completato il riepilogo.",
                link=f"/records/{job.record_id}/ai-summary",
                owner_user_id=job.requested_by_user_id,
                dedup_key=f"ai_failed:{job.id}",
            )
            session.commit()
        logger.exception("Generazione riepilogo fallita per job %s", job_id)
        return {"status": "failed", "job_id": job_id}
    finally:
        session.close()
