"""Endpoint per la gestione delle fonti e l'avvio di scan on-demand."""

from __future__ import annotations

import asyncio
import uuid
from copy import deepcopy
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models.advertisement import Advertisement
from app.models.proxies import ProxyEndpoint, ProxyPool, ProxyPoolMember
from app.models.scrape_errors import ScrapeError
from app.models.scrape_runs import ScrapeRun
from app.models.sources import Source
from app.models.users import User
from app.schemas.sources import (
    RobotsCheckRead,
    ScanTriggerResponse,
    ScrapeErrorRead,
    ScrapeRunRead,
    SourceCreate,
    SourceDetailRead,
    SourceDuplicate,
    SourceExportRequest,
    SourceImportApplyRequest,
    SourceImportPreviewRequest,
    SourceImportPreviewResult,
    SourceImportResult,
    SourceRead,
    SourceScheduleUpdate,
    SourcesSummaryRead,
    SourceTransferDocument,
    SourceTransferItem,
    SourceUpdate,
    TestConfigInput,
    TestConfigResult,
)
from app.security.deps import get_current_user, require_admin_with_2fa, require_role
from app.services.audit import log_action
from app.services.proxy_credentials import decrypt_proxy_credentials
from app.services.proxy_rotation import ProxyRuntimeConfig, proxy_host_is_allowed
from app.services.scrape_ingest import decode_scrape_error_message
from app.services.source_health import summarize_sources_by_status
from app.services.source_transfer import preview_source_document

# Numero massimo di run restituiti da GET /sources/{id}/runs: un drill-down
# "storico recente", non un archivio completo paginato (coerente con lo
# stesso limite pragmatico già usato per GET /exports, vedi
# app/api/v1/exports.py:_RECENT_EXPORTS_LIMIT).
_RECENT_RUNS_LIMIT = 50

# Quanti run recenti considerare per calcolare "consecutive_failures":
# sufficientemente ampio da rilevare un connettore rotto da un po', senza
# scandire l'intero storico di scrape_runs a ogni GET /sources.
_CONSECUTIVE_FAILURES_LOOKBACK = 10

# Soglia oltre la quale la UI mostra il badge "Connector broken?" (vedi
# frontend/src/routes/SourcesPage.tsx) — dashboard/alert per fonti che
# smettono di funzionare, PROGETTO.md § 4.
CONSECUTIVE_FAILURES_ALERT_THRESHOLD = 3

router = APIRouter()


async def _proxy_pool_or_422(db: AsyncSession, pool_id: uuid.UUID | None) -> ProxyPool | None:
    if pool_id is None:
        return None
    pool = await db.get(ProxyPool, pool_id)
    if pool is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pool proxy non trovato.")
    return pool


async def _proxy_pool_status(db: AsyncSession, source: Source) -> str:
    if source.proxy_pool_id is None:
        return "direct"
    pool = await db.get(ProxyPool, source.proxy_pool_id)
    if pool is None or not pool.enabled:
        return "disabled"
    now = datetime.now(UTC)
    healthy = (
        await db.execute(
            select(ProxyEndpoint.id)
            .join(ProxyPoolMember, ProxyPoolMember.proxy_id == ProxyEndpoint.id)
            .where(
                ProxyPoolMember.pool_id == pool.id,
                ProxyEndpoint.enabled.is_(True),
                or_(ProxyEndpoint.cooldown_until.is_(None), ProxyEndpoint.cooldown_until <= now),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return "healthy" if healthy else "unavailable"


async def _proxy_candidates_for_test(
    db: AsyncSession, pool_id: uuid.UUID | None
) -> list[ProxyRuntimeConfig]:
    if pool_id is None:
        return []
    pool = await _proxy_pool_or_422(db, pool_id)
    if pool is None or not pool.enabled:
        raise HTTPException(422, "Il pool proxy e disabilitato.")
    now = datetime.now(UTC)
    rows = (
        (
            await db.execute(
                select(ProxyEndpoint)
                .join(ProxyPoolMember, ProxyPoolMember.proxy_id == ProxyEndpoint.id)
                .where(
                    ProxyPoolMember.pool_id == pool_id,
                    ProxyEndpoint.enabled.is_(True),
                    or_(
                        ProxyEndpoint.cooldown_until.is_(None), ProxyEndpoint.cooldown_until <= now
                    ),
                )
                .order_by(ProxyEndpoint.last_used_at.asc().nullsfirst(), ProxyEndpoint.id.asc())
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        raise HTTPException(503, "Nessun proxy sano disponibile; accesso diretto bloccato.")
    result = []
    for row in rows:
        if not await asyncio.to_thread(proxy_host_is_allowed, row.host):
            continue
        try:
            credentials = decrypt_proxy_credentials(row.credentials_encrypted)
        except RuntimeError as exc:
            raise HTTPException(503, "Credenziali proxy non disponibili.") from exc
        result.append(
            ProxyRuntimeConfig(
                row.id,
                row.scheme,
                row.host,
                row.port,
                credentials[0] if credentials else None,
                credentials[1] if credentials else None,
            )
        )
        if len(result) >= settings.PROXY_MAX_ATTEMPTS:
            break
    if not result:
        raise HTTPException(503, "Nessun proxy con destinazione consentita nel pool.")
    return result


def _source_user_agent(source: Source) -> str:
    scrape_config = source.scrape_config or {}
    configured_user_agent = scrape_config.get("user_agent") or scrape_config.get("userAgent")
    if configured_user_agent:
        return str(configured_user_agent).strip()

    from app.scrapers.base import Scraper

    return Scraper.user_agent


async def _compute_source_read(db: AsyncSession, source: Source, since: datetime) -> SourceRead:
    """Calcola le metriche derivate (`lastRunAt`, `itemsLast24h`,
    `errorRate`, `consecutiveFailures`) di UNA fonte da `scrape_runs`, non
    presenti come colonne dirette su `Source`. Condivisa da `GET /sources`
    (una fonte alla volta, N+1 accettato deliberatamente: il numero di
    fonti è tipicamente piccolo, decine non migliaia — vedi PROGETTO.md)
    e da `GET /sources/{id}` (una singola fonte, nessun N+1)."""
    last_run = (
        await db.execute(
            select(func.coalesce(ScrapeRun.started_at, ScrapeRun.queued_at))
            .where(ScrapeRun.source_id == source.id)
            .order_by(func.coalesce(ScrapeRun.started_at, ScrapeRun.queued_at).desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    recent_runs = (
        await db.execute(
            select(ScrapeRun.items_found, ScrapeRun.errors_count).where(
                ScrapeRun.source_id == source.id,
                func.coalesce(ScrapeRun.started_at, ScrapeRun.queued_at) >= since,
            )
        )
    ).all()
    items_last_24h = sum(r.items_found for r in recent_runs)
    errors_last_24h = sum(r.errors_count for r in recent_runs)
    # Error rate = errori / (item processati + errori) nelle ultime 24h;
    # 0.0 se non c'è stata alcuna attività recente (evita divisione per 0 e
    # non è comunque un dato "in errore", solo assente).
    denominator = items_last_24h + errors_last_24h
    error_rate = (errors_last_24h / denominator) if denominator > 0 else 0.0

    last_statuses = (
        (
            await db.execute(
                select(ScrapeRun.status)
                .where(ScrapeRun.source_id == source.id)
                .order_by(func.coalesce(ScrapeRun.started_at, ScrapeRun.queued_at).desc())
                .limit(_CONSECUTIVE_FAILURES_LOOKBACK)
            )
        )
        .scalars()
        .all()
    )
    consecutive_failures = 0
    for run_status in last_statuses:
        if run_status != "failed":
            break
        consecutive_failures += 1

    active_status = (
        await db.execute(
            select(ScrapeRun.status)
            .where(ScrapeRun.source_id == source.id, ScrapeRun.status.in_(("pending", "running")))
            .limit(1)
        )
    ).scalar_one_or_none()
    schedule_state = (
        "disabled"
        if not source.enabled
        else active_status
        if active_status in {"pending", "running"}
        else "waiting"
        if source.automatic_scraping_enabled and source.next_scrape_at is not None
        else "paused"
    )

    return SourceRead(
        id=source.id,
        code=source.slug,
        name=source.name,
        country_code=source.country_code,
        country=source.country_code or "N/D",
        status=source.status,
        enabled=source.enabled,
        priority=source.priority,
        last_run_at=last_run,
        items_last_24h=items_last_24h,
        error_rate=round(error_rate, 4),
        consecutive_failures=consecutive_failures,
        has_scrape_config=source.scrape_config is not None,
        proxy_pool_id=source.proxy_pool_id,
        proxy_pool_status=await _proxy_pool_status(db, source),
        automatic_scraping_enabled=bool(source.automatic_scraping_enabled),
        scrape_interval_minutes=source.scrape_interval_minutes,
        next_scrape_at=source.next_scrape_at,
        last_scheduled_at=source.last_scheduled_at,
        last_completed_scrape_at=source.last_completed_scrape_at,
        last_schedule_skip_reason=source.last_schedule_skip_reason,
        schedule_revision=source.schedule_revision or 1,
        automatic_scraping_state=schedule_state,
    )


@router.get("", response_model=list[SourceRead])
async def list_sources(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[SourceRead]:
    """Elenco fonti nella forma attesa dal frontend (`Source` type)."""
    sources = (await db.execute(select(Source).order_by(Source.name))).scalars().all()
    since = datetime.now(UTC) - timedelta(hours=24)
    return [await _compute_source_read(db, source, since) for source in sources]


# NOTA D'ORDINE ROUTE: "/summary" deve restare dichiarata prima di
# "/{source_id}" (route a singolo segmento, come "/summary"): FastAPI
# risolve le route nell'ordine di dichiarazione, quindi "/summary"
# andrebbe altrimenti intercettata da "/{source_id}" con
# source_id="summary" (422, UUID non valido) invece di raggiungere questo
# handler.
@router.get("/summary", response_model=SourcesSummaryRead)
async def get_sources_summary(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> SourcesSummaryRead:
    """Conteggio delle fonti per stato, per la card riepilogativa della
    pagina Sources (`GET /sources/summary`, mancante nel backend
    originario: la pagina Sources del frontend la chiama al primo
    caricamento insieme a `GET /sources`)."""
    statuses = (await db.execute(select(Source.status))).scalars().all()
    return SourcesSummaryRead(**summarize_sources_by_status(statuses))


@router.post("/export", response_model=SourceTransferDocument)
async def export_sources(
    payload: SourceExportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> SourceTransferDocument:
    """Export portable source configuration without runtime state or proxy secrets."""
    stmt = select(Source).order_by(Source.name)
    if payload.scope == "selected":
        stmt = stmt.where(Source.id.in_(payload.source_ids))
    sources = (await db.execute(stmt)).scalars().all()
    if payload.scope == "selected" and len(sources) != len(payload.source_ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Una o più fonti non esistono.")
    if not sources:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Nessuna fonte da esportare.")

    pool_ids = {source.proxy_pool_id for source in sources if source.proxy_pool_id}
    pools = (
        (await db.execute(select(ProxyPool).where(ProxyPool.id.in_(pool_ids)))).scalars().all()
        if pool_ids
        else []
    )
    pool_names = {pool.id: pool.name for pool in pools}
    document = SourceTransferDocument(
        format="lavoro-esterno-sources",
        version=1,
        exported_at=datetime.now(UTC),
        sources=[
            SourceTransferItem(
                name=source.name,
                slug=source.slug,
                base_url=source.base_url,
                priority=source.priority,
                country_code=source.country_code,
                scrape_config=source.scrape_config,
                proxy_pool_name=pool_names.get(source.proxy_pool_id),
                watermark_removal={
                    "enabled": source.watermark_removal_enabled,
                    "authorization_reference": source.watermark_authorization_reference,
                    "regions": source.watermark_regions or [],
                },
            )
            for source in sources
        ],
    )
    await log_action(
        db,
        user_id=user.id,
        action="export_sources",
        entity_type="source",
        details={"count": len(sources), "slugs": [source.slug for source in sources]},
    )
    await db.commit()
    return document


@router.post("/import/preview", response_model=SourceImportPreviewResult)
async def preview_sources_import(
    payload: SourceImportPreviewRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
) -> SourceImportPreviewResult:
    """Validate an untrusted source document and report item-level problems."""
    return await preview_source_document(db, payload.document)


@router.post("/import", response_model=SourceImportResult)
async def import_sources(
    payload: SourceImportApplyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> SourceImportResult:
    """Atomically create or update the validated sources in a transfer document."""
    items = payload.document.sources
    slugs = [item.slug for item in items]
    existing_sources = (
        (await db.execute(select(Source).where(Source.slug.in_(slugs)).with_for_update()))
        .scalars()
        .all()
    )
    existing_by_slug = {source.slug: source for source in existing_sources}
    existing_slugs = set(existing_by_slug)
    missing_actions = existing_slugs - payload.conflict_actions.keys()
    extra_actions = payload.conflict_actions.keys() - existing_slugs
    if missing_actions:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Manca un'azione per gli slug esistenti: {', '.join(sorted(missing_actions))}.",
        )
    if extra_actions:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Azioni specificate per slug non in conflitto: {', '.join(sorted(extra_actions))}.",
        )

    pool_names = {item.proxy_pool_name for item in items if item.proxy_pool_name}
    pools = (
        (await db.execute(select(ProxyPool).where(ProxyPool.name.in_(pool_names)))).scalars().all()
        if pool_names
        else []
    )
    pools_by_name = {pool.name: pool for pool in pools}
    created = updated = skipped = 0
    warnings: list[str] = []
    priority_jobs = []

    for item in items:
        source = existing_by_slug.get(item.slug)
        if source is not None and payload.conflict_actions[item.slug] == "skip":
            skipped += 1
            continue

        pool = pools_by_name.get(item.proxy_pool_name) if item.proxy_pool_name else None
        if item.proxy_pool_name and pool is None:
            warnings.append(
                f"{item.slug}: pool proxy '{item.proxy_pool_name}' non trovato; "
                "associazione rimossa."
            )
        scrape_config = item.scrape_config.model_dump() if item.scrape_config else None
        watermark = item.watermark_removal
        watermark_regions = [region.model_dump() for region in watermark.regions]

        if source is None:
            source = Source(
                name=item.name,
                slug=item.slug,
                base_url=item.base_url,
                priority=item.priority,
                country_code=item.country_code,
                status="offline",
                enabled=False,
                automatic_scraping_enabled=False,
                scrape_config=scrape_config,
                proxy_pool_id=pool.id if pool else None,
                watermark_removal_enabled=watermark.enabled,
                watermark_authorization_reference=watermark.authorization_reference,
                watermark_regions=watermark_regions,
            )
            db.add(source)
            created += 1
        else:
            if source.priority != item.priority:
                from app.models.operations import SourcePriorityRecalculationJob

                priority_job = SourcePriorityRecalculationJob(
                    source_id=source.id,
                    requested_by_user_id=user.id,
                    previous_priority=source.priority,
                    requested_priority=item.priority,
                )
                db.add(priority_job)
                priority_jobs.append(priority_job)
            source.name = item.name
            source.base_url = item.base_url
            source.priority = item.priority
            source.country_code = item.country_code
            source.scrape_config = scrape_config
            source.proxy_pool_id = pool.id if pool else None
            source.watermark_removal_enabled = watermark.enabled
            source.watermark_authorization_reference = watermark.authorization_reference
            source.watermark_regions = watermark_regions
            updated += 1

    try:
        await db.flush()
        await log_action(
            db,
            user_id=user.id,
            action="import_sources",
            entity_type="source",
            details={
                "created": created,
                "updated": updated,
                "skipped": skipped,
                "slugs": slugs,
            },
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "L'import è entrato in conflitto con una modifica concorrente; "
            "nessuna fonte è stata importata.",
        ) from exc

    if priority_jobs:
        from app.workers.tasks_operations import recalculate_source_priority

        for priority_job in priority_jobs:
            if priority_job.id is not None:
                recalculate_source_priority.delay(str(priority_job.id))

    return SourceImportResult(
        created=created,
        updated=updated,
        skipped=skipped,
        warnings=warnings,
    )


@router.post("", response_model=SourceRead, status_code=status.HTTP_201_CREATED)
async def create_source(
    payload: SourceCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> SourceRead:
    """Crea una nuova fonte (solo Admin). Se `scrape_config` è valorizzato
    (già validato da `ScrapeConfigInput`), la fonte è immediatamente
    scrapabile dal motore generico tramite `POST /sources/{id}/scan`.
    """
    existing = (
        await db.execute(select(Source.id).where(Source.slug == payload.slug))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Una fonte con slug '{payload.slug}' esiste già.",
        )

    await _proxy_pool_or_422(db, payload.proxy_pool_id)
    source = Source(
        name=payload.name,
        slug=payload.slug,
        base_url=payload.base_url,
        priority=payload.priority,
        country_code=payload.country_code,
        status="healthy",
        enabled=True,
        scrape_config=payload.scrape_config.model_dump() if payload.scrape_config else None,
        proxy_pool_id=payload.proxy_pool_id,
        watermark_removal_enabled=payload.watermark_removal.enabled,
        watermark_authorization_reference=payload.watermark_removal.authorization_reference,
        watermark_regions=[region.model_dump() for region in payload.watermark_removal.regions],
    )
    db.add(source)
    await log_action(
        db,
        user_id=user.id,
        action="create_source",
        entity_type="source",
        details={"slug": payload.slug},
    )
    await db.commit()
    await db.refresh(source)

    return _to_minimal_source_read(source)


async def _get_source_or_404(db: AsyncSession, source_id: uuid.UUID) -> Source:
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fonte non trovata.")
    return source


@router.post(
    "/{source_id}/duplicate",
    response_model=SourceRead,
    status_code=status.HTTP_201_CREATED,
)
async def duplicate_source(
    source_id: uuid.UUID,
    payload: SourceDuplicate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> SourceRead:
    """Duplica la configurazione di una fonte, senza copiarne lo storico operativo."""
    original = await _get_source_or_404(db, source_id)
    if payload.name.strip() == original.name.strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Il nome della copia deve essere diverso da quello della fonte originale.",
        )
    existing = (
        await db.execute(select(Source.id).where(Source.slug == payload.slug))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Una fonte con slug '{payload.slug}' esiste gia.",
        )

    duplicate = Source(
        name=payload.name,
        slug=payload.slug,
        base_url=original.base_url,
        priority=original.priority,
        country_code=original.country_code,
        status="offline",
        enabled=False,
        # Copie esplicite evitano che modifiche in-memory ai JSON mutabili
        # possano propagarsi tra originale e duplicato prima del flush.
        scrape_config=deepcopy(original.scrape_config),
        proxy_pool_id=original.proxy_pool_id,
        watermark_removal_enabled=original.watermark_removal_enabled,
        watermark_authorization_reference=original.watermark_authorization_reference,
        watermark_regions=deepcopy(original.watermark_regions or []),
    )
    db.add(duplicate)
    try:
        await db.flush()
        await log_action(
            db,
            user_id=user.id,
            action="duplicate_source",
            entity_type="source",
            entity_id=str(duplicate.id),
            details={"original_source_id": str(source_id), "duplicate_slug": payload.slug},
        )
        await db.commit()
    except IntegrityError as exc:
        # La constraint UNIQUE resta l'autorita anche in caso di richieste
        # concorrenti che superano entrambe il controllo preventivo.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Una fonte con slug '{payload.slug}' esiste gia.",
        ) from exc
    await db.refresh(duplicate)
    return _to_minimal_source_read(duplicate)


def _to_minimal_source_read(source: Source) -> SourceRead:
    """`SourceRead` con le metriche derivate azzerate: usata subito dopo
    creazione/modifica di una fonte, quando non ha ancora `scrape_runs`
    (o non è comunque il caso di ricalcolarle per una singola risposta di
    scrittura — quella vista completa/aggregata resta `GET /sources`)."""
    return SourceRead(
        id=source.id,
        code=source.slug,
        name=source.name,
        country_code=source.country_code,
        country=source.country_code or "N/D",
        status=source.status,
        enabled=source.enabled,
        priority=source.priority,
        last_run_at=None,
        items_last_24h=0,
        error_rate=0.0,
        consecutive_failures=0,
        has_scrape_config=source.scrape_config is not None,
        proxy_pool_id=source.proxy_pool_id,
        proxy_pool_status="configured" if source.proxy_pool_id else "direct",
        automatic_scraping_enabled=bool(source.automatic_scraping_enabled),
        scrape_interval_minutes=source.scrape_interval_minutes,
        next_scrape_at=source.next_scrape_at,
        last_scheduled_at=source.last_scheduled_at,
        last_completed_scrape_at=source.last_completed_scrape_at,
        last_schedule_skip_reason=source.last_schedule_skip_reason,
        schedule_revision=source.schedule_revision or 1,
        automatic_scraping_state=(
            "disabled"
            if not source.enabled
            else "waiting"
            if source.automatic_scraping_enabled and source.next_scrape_at
            else "paused"
        ),
    )


@router.get("/{source_id}", response_model=SourceDetailRead)
async def get_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> SourceDetailRead:
    """Dettaglio di una fonte, incluso `scrapeConfig` completo — usato per
    precompilare il form "Edit configuration" in UI (`GET /sources`, la
    lista, espone solo `hasScrapeConfig`, un booleano)."""
    source = await _get_source_or_404(db, source_id)
    since = datetime.now(UTC) - timedelta(hours=24)
    base = await _compute_source_read(db, source, since)
    return SourceDetailRead(
        **base.model_dump(by_alias=False),
        scrape_config=source.scrape_config,
        watermark_removal={
            "enabled": source.watermark_removal_enabled,
            "authorization_reference": source.watermark_authorization_reference,
            "regions": source.watermark_regions or [],
        },
    )


@router.patch("/{source_id}", response_model=SourceRead)
async def update_source(
    source_id: uuid.UUID,
    payload: SourceUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> SourceRead:
    """Modifica `name`/`base_url`/`priority`/`scrape_config` di una fonte
    esistente (solo Admin). Non permette di cambiare `slug`: è la chiave
    stabile usata per collegare la fonte al connettore
    (`app/scrapers/registry.py`) o, se configurata, al motore generico."""
    source = (
        await db.execute(select(Source).where(Source.id == source_id).with_for_update())
    ).scalar_one_or_none()
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fonte non trovata.")
    previous_priority = source.priority

    updates = payload.model_dump(
        exclude_unset=True, exclude={"scrape_config", "watermark_removal", "proxy_pool_id"}
    )
    for field_name, value in updates.items():
        setattr(source, field_name, value)
    if "scrape_config" in payload.model_fields_set:
        source.scrape_config = payload.scrape_config.model_dump() if payload.scrape_config else None
        if source.automatic_scraping_enabled:
            active_run = (
                await db.execute(
                    select(ScrapeRun.id).where(
                        ScrapeRun.source_id == source.id,
                        ScrapeRun.status.in_(("pending", "running")),
                    )
                )
            ).scalar_one_or_none()
            if active_run is not None:
                source.next_scrape_at = None
                source.last_schedule_skip_reason = "active_run"
            elif source.scrape_config and source.enabled and source.scrape_interval_minutes:
                source.next_scrape_at = datetime.now(UTC) + timedelta(
                    minutes=source.scrape_interval_minutes
                )
                source.last_schedule_skip_reason = None
            else:
                source.next_scrape_at = None
                source.last_schedule_skip_reason = "configuration_missing"
    if "proxy_pool_id" in payload.model_fields_set:
        await _proxy_pool_or_422(db, payload.proxy_pool_id)
        source.proxy_pool_id = payload.proxy_pool_id
    if "watermark_removal" in payload.model_fields_set and payload.watermark_removal is not None:
        wm = payload.watermark_removal
        source.watermark_removal_enabled = wm.enabled
        source.watermark_authorization_reference = wm.authorization_reference
        source.watermark_regions = [region.model_dump() for region in wm.regions]

    db.add(source)
    priority_job = None
    if source.priority != previous_priority:
        from app.models.operations import SourcePriorityRecalculationJob

        priority_job = SourcePriorityRecalculationJob(
            source_id=source.id,
            requested_by_user_id=user.id,
            previous_priority=previous_priority,
            requested_priority=source.priority,
        )
        db.add(priority_job)
    await log_action(
        db,
        user_id=user.id,
        action="update_source",
        entity_type="source",
        entity_id=str(source_id),
        details={
            "watermark_removal_enabled": source.watermark_removal_enabled,
            "watermark_authorization_reference": source.watermark_authorization_reference,
            "proxy_pool_changed": "proxy_pool_id" in payload.model_fields_set,
        },
    )
    await db.commit()
    await db.refresh(source)
    if priority_job is not None:
        await db.refresh(priority_job)
        from app.workers.tasks_operations import recalculate_source_priority

        recalculate_source_priority.delay(str(priority_job.id))

    return _to_minimal_source_read(source)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
) -> None:
    """Rimuove una fonte (solo Admin). Bloccato con 409 se esistono
    `advertisement` collegati: preserva lo storico invece di lasciare
    annunci orfani o cancellarli silenziosamente."""
    source = await _get_source_or_404(db, source_id)

    has_ads = (
        await db.execute(
            select(Advertisement.id).where(Advertisement.source_id == source_id).limit(1)
        )
    ).scalar_one_or_none()
    if has_ads is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Impossibile eliminare: esistono annunci collegati a questa fonte.",
        )

    await log_action(
        db, user_id=user.id, action="delete_source", entity_type="source", entity_id=str(source_id)
    )
    await db.delete(source)
    await db.commit()


@router.get("/{source_id}/runs", response_model=list[ScrapeRunRead])
async def get_source_runs(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[ScrapeRunRead]:
    """Storico dei run di scraping per una fonte, con gli errori di
    ciascun run annidati — drill-down "visualizzazione errori scraping"
    della pagina Sources (`frontend/src/routes/SourcesPage.tsx`), che oggi
    mostra solo `errorRate` aggregato senza poter vedere i singoli errori.

    Sola lettura, aperto a qualunque ruolo autenticato (come `GET
    /sources`): non è un'azione operativa, solo consultazione.
    """
    await _get_source_or_404(db, source_id)

    runs = (
        (
            await db.execute(
                select(ScrapeRun)
                .where(ScrapeRun.source_id == source_id)
                .order_by(func.coalesce(ScrapeRun.started_at, ScrapeRun.queued_at).desc())
                .limit(_RECENT_RUNS_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    if not runs:
        return []

    run_ids = [r.id for r in runs]
    errors = (
        (
            await db.execute(
                select(ScrapeError)
                .where(ScrapeError.scrape_run_id.in_(run_ids))
                .order_by(ScrapeError.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    errors_by_run: dict[uuid.UUID, list[ScrapeErrorRead]] = {}
    for err in errors:
        error_code, error_message = decode_scrape_error_message(err.error_message)
        errors_by_run.setdefault(err.scrape_run_id, []).append(
            ScrapeErrorRead(
                id=err.id,
                url=err.url,
                error_message=error_message,
                error_code=error_code,
                created_at=err.created_at,
            )
        )

    return [
        ScrapeRunRead(
            id=run.id,
            started_at=run.started_at,
            finished_at=run.finished_at,
            status=run.status,
            items_found=run.items_found,
            items_new=run.items_new,
            items_updated=run.items_updated,
            items_unchanged=run.items_unchanged,
            errors_count=run.errors_count,
            pages_visited=run.pages_visited,
            pagination_mode=run.pagination_mode,
            pagination_stop_reason=run.pagination_stop_reason,
            proxy_attempts_count=run.proxy_attempts_count,
            proxy_rotations_count=run.proxy_rotations_count,
            proxy_stop_reason=run.proxy_stop_reason,
            queued_at=run.queued_at,
            trigger_type=run.trigger_type,
            scheduled_for=run.scheduled_for,
            errors=errors_by_run.get(run.id, []),
        )
        for run in runs
    ]


@router.post("/{source_id}/pause", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def pause_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
) -> None:
    """Mette in pausa una fonte: `enabled=False` senza cambiarne lo `status`
    di salute (una fonte in pausa non è "offline", è semplicemente ferma su
    decisione di un operatore — lo status di salute torna rilevante quando
    verrà riattivata).

    Riservato ad admin/operator, come `POST /sources/{id}/scan`: mettere in
    pausa una fonte è un'azione operativa che impatta la raccolta dati.
    """
    source = (
        await db.execute(select(Source).where(Source.id == source_id).with_for_update())
    ).scalar_one_or_none()
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fonte non trovata.")
    source.enabled = False
    source.next_scrape_at = None
    source.last_schedule_skip_reason = "source_disabled"
    db.add(source)
    await log_action(
        db, user_id=user.id, action="pause_source", entity_type="source", entity_id=str(source_id)
    )
    await db.commit()


@router.post("/{source_id}/disable", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def disable_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
) -> None:
    """Disabilita definitivamente una fonte: `enabled=False` e
    `status="offline"`, a differenza della pausa che lascia lo status di
    salute invariato (vedi `pause_source`)."""
    source = (
        await db.execute(select(Source).where(Source.id == source_id).with_for_update())
    ).scalar_one_or_none()
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fonte non trovata.")
    source.enabled = False
    source.status = "offline"
    source.next_scrape_at = None
    source.last_schedule_skip_reason = "source_disabled"
    db.add(source)
    await log_action(
        db, user_id=user.id, action="disable_source", entity_type="source", entity_id=str(source_id)
    )
    await db.commit()


@router.post("/{source_id}/enable", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def enable_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
) -> None:
    """Riabilita una fonte disabilitata/in pausa e ne ripristina lo stato iniziale."""
    source = (
        await db.execute(select(Source).where(Source.id == source_id).with_for_update())
    ).scalar_one_or_none()
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fonte non trovata.")
    if source.enabled:
        return

    source.enabled = True
    source.status = "healthy"
    active_run = (
        await db.execute(
            select(ScrapeRun.id).where(
                ScrapeRun.source_id == source.id,
                ScrapeRun.status.in_(("pending", "running")),
            )
        )
    ).scalar_one_or_none()
    if (
        source.automatic_scraping_enabled
        and source.scrape_config
        and source.scrape_interval_minutes
        and active_run is None
    ):
        source.next_scrape_at = datetime.now(UTC) + timedelta(
            minutes=source.scrape_interval_minutes
        )
        source.last_schedule_skip_reason = None
    elif active_run is not None:
        source.next_scrape_at = None
        source.last_schedule_skip_reason = "active_run"
    else:
        source.next_scrape_at = None
        source.last_schedule_skip_reason = (
            "schedule_disabled"
            if not source.automatic_scraping_enabled
            else "configuration_missing"
        )
    db.add(source)
    await log_action(
        db, user_id=user.id, action="enable_source", entity_type="source", entity_id=str(source_id)
    )
    await db.commit()


@router.patch("/{source_id}/schedule", response_model=SourceRead)
async def update_source_schedule(
    source_id: uuid.UUID,
    payload: SourceScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin_with_2fa),
) -> SourceRead:
    """Aggiorna lo schedule fixed-delay invalidando pianificazioni obsolete."""
    source = (
        await db.execute(select(Source).where(Source.id == source_id).with_for_update())
    ).scalar_one_or_none()
    if source is None:
        raise HTTPException(404, "Fonte non trovata.")
    if source.schedule_revision != payload.revision:
        raise HTTPException(409, "La schedulazione e stata modificata; ricaricare i dati.")
    if payload.enabled and (not source.enabled or source.scrape_config is None):
        raise HTTPException(422, "La fonte deve essere abilitata e configurata per lo scraping.")
    interval = payload.normalized_minutes()
    if payload.enabled and interval is None:
        raise HTTPException(422, "Intervallo non valido.")
    if interval is not None:
        source.scrape_interval_minutes = interval
    source.automatic_scraping_enabled = payload.enabled
    source.schedule_revision += 1
    source.last_schedule_skip_reason = None if payload.enabled else "schedule_disabled"
    active = (
        await db.execute(
            select(ScrapeRun.id).where(
                ScrapeRun.source_id == source.id,
                ScrapeRun.status.in_(("pending", "running")),
            )
        )
    ).scalar_one_or_none()
    source.next_scrape_at = (
        None
        if active or not payload.enabled
        else datetime.now(UTC) + timedelta(minutes=source.scrape_interval_minutes or 0)
    )
    await log_action(
        db,
        user_id=admin.id,
        action="update_source_schedule",
        entity_type="source",
        entity_id=str(source.id),
        details={
            "enabled": payload.enabled,
            "interval_minutes": source.scrape_interval_minutes,
            "revision": source.schedule_revision,
        },
    )
    await db.commit()
    await db.refresh(source)
    return await _compute_source_read(db, source, datetime.now(UTC) - timedelta(hours=24))


@router.post(
    "/{source_id}/scan", response_model=ScanTriggerResponse, status_code=status.HTTP_202_ACCEPTED
)
async def scan_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin", "operator")),
) -> ScanTriggerResponse:
    """Accoda un task Celery di scraping per la fonte indicata.

    Riservato a admin/operator: uno scan può generare traffico verso siti
    terzi e va quindi avviabile solo da chi ha responsabilità operativa,
    non dai soli viewer.
    """
    source = (
        await db.execute(select(Source).where(Source.id == source_id).with_for_update())
    ).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fonte non trovata.")
    if not source.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="La fonte è disabilitata."
        )

    if source.scrape_config is None:
        raise HTTPException(422, "La fonte non ha una configurazione di scraping.")
    active_run = (
        await db.execute(
            select(ScrapeRun).where(
                ScrapeRun.source_id == source.id,
                ScrapeRun.status.in_(("pending", "running")),
            )
        )
    ).scalar_one_or_none()
    if active_run is not None:
        raise HTTPException(409, f"Uno scan e gia attivo (run {active_run.id}).")

    task_id = str(uuid.uuid4())
    run = ScrapeRun(
        source_id=source.id,
        status="pending",
        queued_at=datetime.now(UTC),
        trigger_type="manual",
        celery_task_id=task_id,
    )
    db.add(run)
    source.next_scrape_at = None
    source.last_schedule_skip_reason = None
    await db.commit()
    await db.refresh(run)

    from app.workers.tasks_scraper import run_scrape_source

    try:
        run_scrape_source.apply_async(args=[str(source.id), str(run.id)], task_id=task_id)
    except Exception as exc:
        finished_at = datetime.now(UTC)
        run.status = "failed"
        run.finished_at = finished_at
        await db.refresh(
            source,
            attribute_names=[
                "automatic_scraping_enabled",
                "enabled",
                "scrape_config",
                "scrape_interval_minutes",
            ],
        )
        source.last_completed_scrape_at = finished_at
        if (
            source.automatic_scraping_enabled
            and source.enabled
            and source.scrape_config
            and source.scrape_interval_minutes
        ):
            source.next_scrape_at = finished_at + timedelta(minutes=source.scrape_interval_minutes)
        else:
            source.next_scrape_at = None
        source.last_schedule_skip_reason = "dispatch_failed"
        await db.commit()
        raise HTTPException(503, "Impossibile accodare lo scan.") from exc

    return ScanTriggerResponse(task_id=task_id, source_id=source.id, run_id=run.id)


@router.post("/{source_id}/check-robots", response_model=RobotsCheckRead)
async def check_source_robots(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> RobotsCheckRead:
    """Verifica live `robots.txt` per `base_url` della fonte (solo il file
    `robots.txt` stesso viene scaricato, pubblico per definizione — nessun
    altro contenuto della fonte). Utile per validare una configurazione
    prima di lanciare uno scan reale. Sola lettura, nessuna restrizione di
    ruolo oltre l'autenticazione."""
    source = await _get_source_or_404(db, source_id)

    from app.services.robots_check import check_robots

    result = await check_robots(source.base_url, user_agent=_source_user_agent(source))
    return RobotsCheckRead(
        allowed=result.allowed,
        robots_txt_found=result.robots_txt_found,
        checked_url=result.checked_url,
    )


@router.post("/{source_id}/test-config", response_model=TestConfigResult)
async def test_source_config(
    source_id: uuid.UUID,
    payload: TestConfigInput | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin", "operator")),
) -> TestConfigResult:
    """Prova la configurazione di scraping della fonte su UN solo annuncio
    (non salvato su DB): permette di verificare che i selettori CSS
    configurati estraggano davvero i campi attesi, prima di lanciare uno
    scan reale che scriverebbe su Postgres/MinIO. Richiede `scrape_config`
    già salvato (vedi `PATCH /sources/{id}`).

    Come `POST /sources/{id}/scan`, richiede admin/operator: esegue comunque
    richieste HTTP reali verso la fonte (rispettando robots.txt/rate-limit
    come ogni altra chiamata del motore).
    """
    source = await _get_source_or_404(db, source_id)
    scrape_config = (
        payload.scrape_config.model_dump() if payload is not None else source.scrape_config
    )
    proxy_pool_id = (
        payload.proxy_pool_id
        if payload is not None and "proxy_pool_id" in payload.model_fields_set
        else source.proxy_pool_id
    )
    if not scrape_config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Questa fonte non ha ancora una configurazione di scraping (scrape_config).",
        )

    from app.scrapers.generic import (
        AntiBotBlockedError,
        GenericScraper,
        PageFetchError,
        ProxyPoolExhaustedError,
        RobotsDisallowedError,
    )

    def config_value(snake_case_key: str, camel_case_key: str, default=None):
        return scrape_config.get(snake_case_key, scrape_config.get(camel_case_key, default))

    def anti_bot_actions(*, pool_exhausted: bool = False) -> list[str]:
        actions: list[str] = []
        if config_value("fetch_mode", "fetchMode") != "stealth":
            actions.append("Usa la modalita Stealth per questa fonte.")
        if not config_value("solve_cloudflare", "solveCloudflare", False):
            actions.append("Abilita Gestisci Cloudflare nella configurazione della fonte.")
        if config_value("user_agent", "userAgent"):
            actions.append(
                "Lascia vuoto lo User-Agent per usare quello coerente con il browser Scrapling."
            )
        if proxy_pool_id is None:
            actions.append(
                "Assegna un pool autorizzato con proxy adatto alla regione della fonte e riprova."
            )
        elif pool_exhausted:
            actions.append(
                "Verifica disponibilita e regione dei proxy del pool assegnato prima di riprovare."
            )
        actions.append(
            "Se il blocco persiste, sospendi la fonte: il superamento della protezione "
            "non e garantito."
        )
        return actions

    proxy_candidates = await _proxy_candidates_for_test(db, proxy_pool_id)
    scraper = GenericScraper(
        slug=source.slug,
        base_url=source.base_url,
        config=scrape_config,
        proxy_candidates=proxy_candidates,
    )
    try:
        ad_urls = await scraper.discover()
        diagnostics = scraper.discovery_diagnostics
        if not ad_urls:
            return TestConfigResult(
                ad_urls_found=0,
                error="Nessun link annuncio trovato con 'ad_link_selector'.",
                warnings=[*diagnostics.warnings, *diagnostics.errors],
                pages_visited=diagnostics.pages_visited,
                configured_max_pages=diagnostics.configured_max_pages,
                pagination_mode=diagnostics.pagination_mode,
                pagination_stop_reason=diagnostics.stop_reason,
                unique_ads_found=diagnostics.unique_ads_found,
            )
        raw = await scraper.scrape_ad(ad_urls[0])
        return TestConfigResult(
            ad_urls_found=len(ad_urls),
            sample_url=ad_urls[0],
            extracted_fields=raw,
            warnings=[
                *scraper.media_extraction_warnings(raw),
                *getattr(scraper, "field_pagination_warnings", []),
                *diagnostics.warnings,
                *diagnostics.errors,
            ],
            pages_visited=diagnostics.pages_visited,
            configured_max_pages=diagnostics.configured_max_pages,
            pagination_mode=diagnostics.pagination_mode,
            pagination_stop_reason=diagnostics.stop_reason,
            unique_ads_found=diagnostics.unique_ads_found,
            field_pagination={
                name: {
                    "pages_visited": field_diagnostic.pages_visited,
                    "items_collected": field_diagnostic.items_collected,
                    "pagination_mode": field_diagnostic.pagination_mode,
                    "stop_reason": field_diagnostic.stop_reason,
                    "complete": field_diagnostic.complete,
                }
                for name, field_diagnostic in getattr(
                    scraper, "field_pagination_diagnostics", {}
                ).items()
            },
        )
    except RobotsDisallowedError as exc:
        return TestConfigResult(
            ad_urls_found=0,
            error=f"robots.txt vieta l'accesso: {exc}",
            error_code="robots_disallowed",
        )
    except AntiBotBlockedError as exc:
        return TestConfigResult(
            ad_urls_found=0,
            error=str(exc),
            error_code="anti_bot_blocked",
            http_status=exc.http_status,
            recommended_actions=anti_bot_actions(),
        )
    except ProxyPoolExhaustedError as exc:
        return TestConfigResult(
            ad_urls_found=0,
            error=str(exc),
            error_code="proxy_pool_exhausted",
            recommended_actions=(
                anti_bot_actions(pool_exhausted=True)
                if exc.category == "anti_bot_blocked"
                else ["Verifica disponibilita, credenziali e connettivita del pool assegnato."]
            ),
        )
    except PageFetchError as exc:
        return TestConfigResult(
            ad_urls_found=0,
            error=str(exc),
            error_code="fetch_failed",
        )
    except Exception as exc:  # noqa: BLE001 - risposta diagnostica per l'operatore, non un 500
        return TestConfigResult(ad_urls_found=0, error=str(exc), error_code="fetch_failed")
    finally:
        await scraper.aclose()
