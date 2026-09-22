"""Orchestrazione dello scraping reale: dalla configurazione di una fonte
(`Source.scrape_config`) alla persistenza di `Record`/`Advertisement`/
`Media`, passando per dedup e selezione canonica.

Prima pipeline di ingestione end-to-end del progetto: finora
`app/workers/tasks_scraper.py` si limitava a loggare un TODO. Divisa in
due fasi deliberatamente separate:

1. `collect_ads` — SOLO rete (async, via `GenericScraper`), nessuna
   scrittura su DB: testabile con fixture HTML locali, senza toccare
   Postgres (vedi `backend/tests/scrapers/`).
2. `persist_collected_ads` — SOLO scrittura su DB (sync, stessa sessione
   sincrona già usata da `tasks_scraper.py`), nessuna rete: riusa
   `app/services/dedup.py`, `phone_crypto.py`, `canonical.py`, già
   testati in isolamento.

Il worker Celery (`run_scrape_source`) chiama prima la fase 1 (dentro
`asyncio.run`), poi la fase 2.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.advertisement import Advertisement
from app.models.advertisement_versions import AdvertisementVersion
from app.models.canonical_history import CanonicalHistory
from app.models.media import Media
from app.models.record import Record
from app.models.sources import Source
from app.scrapers.generic import (
    AntiBotBlockedError,
    DiscoveryDiagnostics,
    GenericScraper,
    PageFetchError,
    ProxyPoolExhaustedError,
    RobotsDisallowedError,
)
from app.services.canonical import (
    CandidateAdvertisement,
    CandidateSource,
    SourcePriority,
    build_history_entry,
    resolve_canonical,
)
from app.services.dedup import content_sha256
from app.services.media_processing import probe_video, validate_image
from app.services.media_storage import sniff_mime_type, upload_media_object
from app.services.phone_crypto import (
    PhoneCryptoError,
    encrypt_phone,
    normalize_phone,
    phone_lookup_hash,
)
from app.services.proxy_rotation import ProxyRuntimeConfig, ProxyRuntimeEvent

logger = logging.getLogger(__name__)

_SCRAPE_ERROR_CODES = {
    "anti_bot_blocked",
    "proxy_pool_exhausted",
    "robots_disallowed",
    "fetch_failed",
    "field_pagination_incomplete",
    "content_sanitization_failed",
    "content_sanitization_configuration",
    "content_sanitization_timeout",
    "content_sanitization_unavailable",
    "content_sanitization_http_error",
    "content_sanitization_invalid_response",
    "content_sanitization_incomplete_response",
    "content_sanitization_empty_output",
    "content_sanitization_invalid_changed",
    "content_sanitization_unchanged_mismatch",
    "content_sanitization_numbers_changed",
}


def encode_scrape_error_message(code: str | None, message: str) -> str:
    return f"[{code}] {message}" if code in _SCRAPE_ERROR_CODES else message


def decode_scrape_error_message(message: str) -> tuple[str | None, str]:
    for code in _SCRAPE_ERROR_CODES:
        prefix = f"[{code}] "
        if message.startswith(prefix):
            return code, message[len(prefix) :]
    return None, message


def scrape_error_code(exc: Exception) -> str:
    if isinstance(exc, RobotsDisallowedError):
        return "robots_disallowed"
    if isinstance(exc, AntiBotBlockedError):
        return "anti_bot_blocked"
    if isinstance(exc, ProxyPoolExhaustedError):
        return "proxy_pool_exhausted"
    return "fetch_failed"


def advertisement_content_hash(normalized: dict) -> str:
    """Hash core and custom content with stable JSON ordering."""
    return content_sha256(
        json.dumps(
            {
                "title": normalized.get("title") or "",
                "description": normalized.get("description") or "",
                "custom_fields": normalized.get("custom_fields") or {},
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def non_empty_custom_field_count(custom_fields: dict | None) -> int:
    """Count informative custom values for canonical completeness scoring."""
    return sum(
        1
        for value in (custom_fields or {}).values()
        if value is not None
        and (not isinstance(value, str) or bool(value.strip()))
        and (not isinstance(value, list) or bool(value))
    )


@dataclass
class CollectedAd:
    normalized: dict
    media_bytes: list[bytes] = field(default_factory=list)
    media_download_complete: bool = True
    listing_page_number: int | None = None
    original_content_encrypted: bytes | None = None
    sanitization_metadata: dict = field(default_factory=dict)
    persistence_outcome: str = "pending"


@dataclass
class ScrapeErrorDetail:
    url: str
    message: str
    code: str | None = None


@dataclass
class CollectionResult:
    ads: list[CollectedAd]
    errors: list[ScrapeErrorDetail] = field(default_factory=list)
    discovery_diagnostics: DiscoveryDiagnostics = field(default_factory=DiscoveryDiagnostics)
    proxy_events: list[ProxyRuntimeEvent] = field(default_factory=list)

    @property
    def errors_count(self) -> int:
        return len(self.errors)


async def collect_ads(
    source: Source,
    proxy_candidates: list[ProxyRuntimeConfig] | None = None,
    on_ad: Callable[[CollectedAd], bool] | None = None,
) -> CollectionResult:
    """Fase 1: esegue davvero `discover -> scrape_ad -> normalize ->
    download_media` per la fonte, senza toccare il database.

    Un URL vietato da robots.txt, o irraggiungibile, viene saltato e
    contato come errore — non interrompe l'intero run (a meno che sia
    `discover()` stesso a fallire, nel qual caso non c'è nulla da fare per
    questa fonte in questo run).
    """
    scraper = GenericScraper(
        slug=source.slug,
        base_url=source.base_url,
        config=source.scrape_config,
        proxy_candidates=proxy_candidates,
    )

    try:
        try:
            ad_urls = await scraper.discover()
        except RobotsDisallowedError as exc:
            logger.warning(
                "robots.txt vieta l'accesso alla pagina di elenco per '%s': %s", source.slug, exc
            )
            return CollectionResult(
                ads=[],
                errors=[ScrapeErrorDetail(url=exc.url, message=str(exc), code="robots_disallowed")],
                discovery_diagnostics=scraper.discovery_diagnostics,
                proxy_events=scraper.proxy_events,
            )
        except (httpx.HTTPError, PageFetchError) as exc:
            logger.warning("Errore durante discover() per '%s': %s", source.slug, exc)
            return CollectionResult(
                ads=[],
                errors=[
                    ScrapeErrorDetail(
                        url=source.base_url,
                        message=str(exc),
                        code=scrape_error_code(exc),
                    )
                ],
                discovery_diagnostics=scraper.discovery_diagnostics,
                proxy_events=scraper.proxy_events,
            )

        collected: list[CollectedAd] = []
        errors = [
            ScrapeErrorDetail(url=source.base_url, message=message)
            for message in scraper.discovery_diagnostics.errors
        ]

        for url in ad_urls:
            pagination_warning_offset = len(scraper.field_pagination_warnings)
            try:
                raw = await scraper.scrape_ad(url)
            except (RobotsDisallowedError, httpx.HTTPError, PageFetchError) as exc:
                logger.info("Annuncio saltato (%s): %s", url, exc)
                errors.append(
                    ScrapeErrorDetail(url=url, message=str(exc), code=scrape_error_code(exc))
                )
                continue

            errors.extend(
                ScrapeErrorDetail(
                    url=url,
                    message=message,
                    code="field_pagination_incomplete",
                )
                for message in scraper.field_pagination_warnings[pagination_warning_offset:]
            )

            normalized = scraper.normalize(raw)
            if not normalized.get("phone_raw"):
                # Senza un telefono non c'è modo di deduplicare/collegare
                # l'annuncio a un Record: lo scartiamo esplicitamente invece di
                # crearne uno "orfano".
                errors.append(
                    ScrapeErrorDetail(url=url, message="Nessun numero di telefono estratto.")
                )
                continue

            media_bytes: list[bytes] = []
            media_download_complete = True
            media_issues = scraper.media_extraction_warnings(raw)
            try:
                media_result = await scraper.download_media(normalized)
                media_bytes = media_result.media_bytes
                if media_result.failures:
                    media_download_complete = False
                    media_issues.append(
                        "Download media: "
                        f"{media_result.failed_count} di {media_result.attempted_count} file "
                        f"non scaricati. Primo errore: {media_result.failures[0].message}"
                    )
            except Exception as exc:  # noqa: BLE001 - protezione best-effort del run
                media_download_complete = False
                # Non serializzare l'eccezione: potrebbe contenere l'URL media.
                logger.error(
                    "Download media fallito per un annuncio della fonte '%s' (%s).",
                    source.slug,
                    type(exc).__name__,
                )
                media_issues.append("Errore inatteso durante il download dei media.")

            if media_issues:
                errors.append(ScrapeErrorDetail(url=url, message=" ".join(media_issues)))

            item = CollectedAd(
                normalized=normalized,
                media_bytes=media_bytes,
                media_download_complete=media_download_complete,
                listing_page_number=scraper.discovered_page_numbers.get(url),
            )
            # The Celery orchestration uses this hook to sanitize and commit a
            # full publication batch while the remaining detail pages are
            # still being scraped. Tests and other callers keep the original
            # collect-then-persist behavior when the hook is omitted.
            if on_ad is None or on_ad(item):
                collected.append(item)

        return CollectionResult(
            ads=collected,
            errors=errors,
            discovery_diagnostics=scraper.discovery_diagnostics,
            proxy_events=scraper.proxy_events,
        )
    finally:
        await scraper.aclose()


def _get_or_create_record(session: Session, phone_lookup: str, phone_normalized: str) -> Record:
    # Serialize creation for the same HMAC across concurrent source workers.
    # The database unique key remains the final guard; the advisory lock avoids
    # turning a normal race into a failed scrape transaction.
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        lock_key = int(phone_lookup[:16], 16)
        if lock_key >= 2**63:
            lock_key -= 2**64
        session.execute(select(func.pg_advisory_xact_lock(lock_key)))
    record = session.execute(
        select(Record).where(Record.phone_lookup_hash == phone_lookup)
    ).scalar_one_or_none()
    if record is not None:
        return record

    record = Record(phone_encrypted=encrypt_phone(phone_normalized), phone_lookup_hash=phone_lookup)
    session.add(record)
    session.flush()  # popola record.id per l'uso immediato sotto
    return record


def media_set_hash(hashes: list[str] | set[str]) -> str:
    """Return an order-independent hash for the deduplicated current set."""
    payload = json.dumps(sorted(set(hashes)), separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def occurrence_fingerprint(content_hash: str, current_media_hash: str) -> str:
    return hashlib.sha256(f"{content_hash}:{current_media_hash}".encode()).hexdigest()


@dataclass
class MediaPersistResult:
    new_media_ids: list[uuid.UUID]
    current_hashes: list[str]
    complete: bool


def _reconcile_media(
    session: Session,
    record_id: uuid.UUID,
    advertisement: Advertisement,
    media_bytes_list: list[bytes],
    *,
    download_complete: bool,
) -> MediaPersistResult:
    """Reconcile current media while preserving immutable original objects."""
    now = datetime.now(UTC)
    existing_media = (
        session.execute(
            select(Media).where(Media.advertisement_id == advertisement.id).with_for_update()
        )
        .scalars()
        .all()
    )
    by_hash = {media.sha256: media for media in existing_media}
    incoming = {hashlib.sha256(data).hexdigest(): data for data in media_bytes_list}
    accepted_hashes: set[str] = set()
    new_ids: list[uuid.UUID] = []
    effective_complete = download_complete

    for sha256, data in incoming.items():
        existing = by_hash.get(sha256)
        if existing is not None:
            existing.last_seen_at = now
            existing.is_current = True
            accepted_hashes.add(sha256)
            continue
        mime_type = sniff_mime_type(data)
        try:
            metadata = (
                validate_image(data, mime_type)
                if mime_type.startswith("image/")
                else probe_video(data, mime_type)
            )
            object_key = upload_media_object(record_id, data, mime_type)
        except Exception as exc:  # noqa: BLE001
            effective_complete = False
            logger.warning(
                "Media non persistito per annuncio %s (%s).",
                advertisement.id,
                type(exc).__name__,
            )
            continue
        media = Media(
            advertisement_id=advertisement.id,
            original_object_key=object_key,
            sha256=sha256,
            mime_type=mime_type,
            classification="unclassified",
            processing_status="pending",
            review_status="required",
            safety_signals={},
            file_size_bytes=metadata.file_size_bytes,
            width=metadata.width,
            height=metadata.height,
            duration_seconds=metadata.duration_seconds,
            is_current=True,
            last_seen_at=now,
        )
        session.add(media)
        session.flush()
        accepted_hashes.add(sha256)
        new_ids.append(media.id)

    if effective_complete:
        for media in existing_media:
            if media.is_current and media.sha256 not in accepted_hashes:
                media.is_current = False
    else:
        accepted_hashes.update(media.sha256 for media in existing_media if media.is_current)
    return MediaPersistResult(new_ids, sorted(accepted_hashes), effective_complete)


def _changed_fields(
    advertisement: Advertisement, normalized: dict, media_changed: bool
) -> list[str]:
    changed: list[str] = []
    if (advertisement.title or "") != (normalized.get("title") or ""):
        changed.append("title")
    if (advertisement.description or "") != (normalized.get("description") or ""):
        changed.append("description")
    if (advertisement.custom_fields or {}) != (normalized.get("custom_fields") or {}):
        changed.append("customFields")
    if media_changed:
        changed.append("media")
    return changed


def _save_version(
    session: Session,
    advertisement: Advertisement,
    run_id: uuid.UUID | None,
    changed_fields: list[str],
    current_media_hashes: list[str],
) -> None:
    content_hash = advertisement.content_hash or advertisement_content_hash(
        {
            "title": advertisement.title,
            "description": advertisement.description,
            "custom_fields": advertisement.custom_fields,
        }
    )
    current_media_set_hash = advertisement.media_set_hash or media_set_hash(current_media_hashes)
    session.add(
        AdvertisementVersion(
            advertisement_id=advertisement.id,
            revision=advertisement.revision,
            scrape_run_id=run_id,
            content_hash=content_hash,
            media_set_hash=current_media_set_hash,
            fingerprint=occurrence_fingerprint(content_hash, current_media_set_hash),
            changed_fields=changed_fields,
            snapshot_json={
                "title": advertisement.title,
                "description": advertisement.description,
                "customFields": advertisement.custom_fields or {},
                "listingPageNumber": advertisement.listing_page_number,
                "mediaHashes": current_media_hashes,
            },
        )
    )


def recompute_canonical(session: Session, record: Record) -> bool:
    rows = session.execute(
        select(Advertisement, Source)
        .join(Source, Source.id == Advertisement.source_id)
        .where(Advertisement.record_id == record.id)
    ).all()

    candidates = [
        CandidateAdvertisement(
            id=ad.id,
            source=CandidateSource(id=src.id, slug=src.slug, priority=SourcePriority[src.priority]),
            scraped_at=ad.scraped_at,
            status=ad.status,
            title=ad.title,
            description=ad.description,
            source_url=ad.source_url,
            extra_non_empty_fields=non_empty_custom_field_count(ad.custom_fields),
            listing_page_number=ad.listing_page_number,
        )
        for ad, src in rows
    ]

    try:
        resolution = resolve_canonical(candidates)
    except ValueError:
        return False  # nessun annuncio "active": nulla da fare (caso limite)

    if record.canonical_ad_id == resolution.chosen.id:
        return False

    entry = build_history_entry(record.id, record.canonical_ad_id, resolution)
    session.add(CanonicalHistory(**entry))
    record.canonical_ad_id = resolution.chosen.id
    session.add(record)
    return True


def persist_collected_ads(
    session: Session,
    source: Source,
    result: CollectionResult,
    run_id: uuid.UUID | None = None,
    batch_size: int = 50,
) -> dict:
    """Fase 2: scrive su DB gli annunci raccolti dalla fase 1 (dedup per
    telefono, upsert per URL, upload media, ricalcolo canonico). Nessuna
    richiesta di rete qui: solo operazioni DB (+ upload MinIO, anch'esso
    locale/interno alla rete Docker, non verso la fonte scrapata)."""
    items_new = 0
    items_updated = 0
    items_unchanged = 0
    persist_errors: list[ScrapeErrorDetail] = []
    media_ids: list[uuid.UUID] = []
    pending_since_commit = 0

    for item in result.ads:
        phone_raw = item.normalized["phone_raw"]
        source_url = item.normalized.get("source_url") or source.base_url
        try:
            # International numbers keep their own prefix; national numbers
            # inherit the calling code selected on the source.
            phone_normalized = normalize_phone(phone_raw, source.country_code)
        except PhoneCryptoError as exc:
            item.persistence_outcome = "rejected_invalid_phone"
            persist_errors.append(
                ScrapeErrorDetail(url=source_url, message=f"Telefono non valido: {exc}")
            )
            continue

        lookup_hash = phone_lookup_hash(phone_normalized)
        # A completed/confirmed right-to-erasure request must not be undone by
        # the next scraper run.  Store only the keyed HMAC and aggregate
        # counters: the clear phone is never copied into the suppression log.
        from app.models.privacy import SuppressionEntry

        suppression = session.execute(
            select(SuppressionEntry).where(SuppressionEntry.phone_lookup_hash == lookup_hash)
        ).scalar_one_or_none()
        if suppression is not None:
            item.persistence_outcome = "suppressed"
            suppression.blocked_ingestions += 1
            suppression.last_blocked_at = datetime.now(UTC)
            session.add(suppression)
            pending_since_commit += 1
            if pending_since_commit >= batch_size:
                session.commit()
                pending_since_commit = 0
            continue
        record = _get_or_create_record(session, lookup_hash, phone_normalized)

        now = datetime.now(UTC)
        advertisement = session.execute(
            select(Advertisement)
            .where(
                Advertisement.record_id == record.id,
                Advertisement.source_id == source.id,
                Advertisement.source_url == item.normalized["source_url"],
            )
            .with_for_update()
        ).scalar_one_or_none()
        is_new = advertisement is None
        new_content_hash = advertisement_content_hash(item.normalized)
        if advertisement is None:
            advertisement = Advertisement(
                record_id=record.id,
                source_id=source.id,
                source_url=item.normalized["source_url"],
                title=item.normalized.get("title"),
                description=item.normalized.get("description"),
                listing_page_number=item.listing_page_number,
                original_content_encrypted=item.original_content_encrypted,
                sanitization_metadata=item.sanitization_metadata,
                custom_fields=item.normalized.get("custom_fields") or {},
                content_hash=new_content_hash,
                confidence=1.0,
                status="active",
                revision=1,
                first_seen_at=now,
                last_seen_at=now,
                scraped_at=now,
                last_changed_at=now,
            )
            session.add(advertisement)
            session.flush()
            items_new += 1
            item.persistence_outcome = "created"

        previous_hashes = (
            session.execute(
                select(Media.sha256).where(
                    Media.advertisement_id == advertisement.id, Media.is_current.is_(True)
                )
            )
            .scalars()
            .all()
        )
        previous_media_hash = advertisement.media_set_hash or media_set_hash(previous_hashes)
        media_result = _reconcile_media(
            session,
            record.id,
            advertisement,
            item.media_bytes,
            download_complete=item.media_download_complete,
        )
        media_ids.extend(media_result.new_media_ids)
        new_media_hash = media_set_hash(media_result.current_hashes)

        if is_new:
            advertisement.media_set_hash = new_media_hash
            record.content_revision += 1
            _save_version(session, advertisement, run_id, ["initial"], media_result.current_hashes)
            recompute_canonical(session, record)
        else:
            resolved_page_number = advertisement.listing_page_number
            if item.listing_page_number is not None:
                resolved_page_number = (
                    item.listing_page_number
                    if resolved_page_number is None
                    else min(resolved_page_number, item.listing_page_number)
                )
            changed = _changed_fields(
                advertisement, item.normalized, new_media_hash != previous_media_hash
            )
            if advertisement.listing_page_number != resolved_page_number:
                changed.append("listingPageNumber")
            advertisement.last_seen_at = now
            if not changed:
                items_unchanged += 1
                item.persistence_outcome = "unchanged"
            else:
                advertisement.title = item.normalized.get("title")
                advertisement.description = item.normalized.get("description")
                advertisement.listing_page_number = resolved_page_number
                advertisement.original_content_encrypted = item.original_content_encrypted
                advertisement.sanitization_metadata = item.sanitization_metadata
                advertisement.custom_fields = item.normalized.get("custom_fields") or {}
                advertisement.content_hash = new_content_hash
                advertisement.media_set_hash = new_media_hash
                advertisement.scraped_at = now
                advertisement.last_changed_at = now
                advertisement.revision += 1
                record.content_revision += 1
                items_updated += 1
                item.persistence_outcome = "updated"
                _save_version(session, advertisement, run_id, changed, media_result.current_hashes)
                recompute_canonical(session, record)
        pending_since_commit += 1
        if pending_since_commit >= batch_size:
            session.commit()
            pending_since_commit = 0

    if pending_since_commit:
        session.commit()

    all_errors = result.errors + persist_errors
    return {
        "items_found": len(result.ads) + result.errors_count,
        "items_new": items_new,
        "items_updated": items_updated,
        "items_unchanged": items_unchanged,
        "errors": all_errors,
        "errors_count": len(all_errors),
        "media_ids": [str(media_id) for media_id in media_ids],
        "pages_visited": result.discovery_diagnostics.pages_visited,
        "pagination_mode": result.discovery_diagnostics.pagination_mode,
        "pagination_stop_reason": result.discovery_diagnostics.stop_reason,
        "proxy_events": result.proxy_events,
    }
