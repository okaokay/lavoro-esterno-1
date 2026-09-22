"""Endpoint aggregati per la dashboard operativa.

Nessuno di questi endpoint esisteva nel backend originario: il frontend
(`frontend/src/api/dashboard.ts`) li chiama fin dal primo caricamento della
home, quindi la loro assenza rompeva la pagina principale dell'app. Sono
tutte query di sola lettura, aperte a qualsiasi utente autenticato (Admin,
Operator o Viewer): la dashboard è pensata come vista d'insieme per
chiunque operi sul sistema, non un'area riservata.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.audit_log import AuditLog
from app.models.export_jobs import ExportJob
from app.models.record import Record
from app.models.scrape_errors import ScrapeError
from app.models.scrape_runs import ScrapeRun
from app.models.sources import Source
from app.models.users import User
from app.schemas.dashboard import (
    ActivityEventRead,
    DashboardKpisRead,
    ScrapingActivityRead,
    SourceHealthBreakdownRead,
)
from app.security.deps import get_current_user
from app.services.dashboard_metrics import percentage_delta, safe_percentage
from app.services.dashboard_range import DashboardRange, resolve_dashboard_range
from app.services.source_health import health_breakdown

router = APIRouter()

# Numero di righe recenti restituite dagli endpoint "attività": non sono
# paginati esplicitamente dal frontend (che li mostra come liste brevi "ultimi
# eventi"), quindi limitiamo lato server per evitare risposte enormi su
# installazioni con molta storia.
_RECENT_LIMIT = 20


@router.get("/kpis", response_model=DashboardKpisRead)
async def get_dashboard_kpis(
    time_range: DashboardRange = Depends(resolve_dashboard_range),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> DashboardKpisRead:
    """Calcola i KPI della dashboard nella finestra temporale richiesta."""
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    total_records = (await db.execute(select(func.count()).select_from(Record))).scalar_one()

    new_records_in_range = (
        await db.execute(
            select(func.count())
            .select_from(Record)
            .where(
                Record.created_at >= time_range.start,
                Record.created_at < time_range.end,
            )
        )
    ).scalar_one()
    new_records_previous_range = (
        await db.execute(
            select(func.count())
            .select_from(Record)
            .where(
                Record.created_at >= time_range.previous_start,
                Record.created_at < time_range.start,
            )
        )
    ).scalar_one()
    new_records_delta_pct = percentage_delta(new_records_in_range, new_records_previous_range)

    new_records_today = (
        await db.execute(
            select(func.count()).select_from(Record).where(Record.created_at >= today_start)
        )
    ).scalar_one()
    # Campo mantenuto per compatibilita con i client precedenti. Il delta
    # rappresenta ora il confronto tra l'intervallo selezionato e quello
    # immediatamente precedente della stessa durata.
    total_records_delta_pct = new_records_delta_pct

    active_sources = (
        await db.execute(select(func.count()).select_from(Source).where(Source.enabled.is_(True)))
    ).scalar_one()
    active_healthy_sources = (
        await db.execute(
            select(func.count())
            .select_from(Source)
            .where(Source.enabled.is_(True), Source.status == "healthy")
        )
    ).scalar_one()
    active_sources_healthy_pct = safe_percentage(active_healthy_sources, active_sources)

    scraping_errors = (
        await db.execute(
            select(func.count())
            .select_from(ScrapeError)
            .where(
                ScrapeError.created_at >= time_range.start,
                ScrapeError.created_at < time_range.end,
            )
        )
    ).scalar_one()
    scraping_errors_previous = (
        await db.execute(
            select(func.count())
            .select_from(ScrapeError)
            .where(
                ScrapeError.created_at >= time_range.previous_start,
                ScrapeError.created_at < time_range.start,
            )
        )
    ).scalar_one()
    # A differenza di total_records_delta_pct, qui il frontend chiede un
    # numero assoluto ("scrapingErrorsDelta", non "...DeltaPct"): differenza
    # semplice tra le due finestre adiacenti della stessa durata.
    scraping_errors_delta = scraping_errors - scraping_errors_previous

    active_exports = (
        await db.execute(
            select(func.count())
            .select_from(ExportJob)
            .where(ExportJob.status.in_(["pending", "processing"]))
        )
    ).scalar_one()

    return DashboardKpisRead(
        total_records=total_records,
        total_records_delta_pct=total_records_delta_pct,
        active_sources=active_sources,
        active_sources_healthy_pct=active_sources_healthy_pct,
        new_records_today=new_records_today,
        scraping_errors=scraping_errors,
        scraping_errors_delta=scraping_errors_delta,
        active_exports=active_exports,
        range_start=time_range.start,
        range_end=time_range.end,
        new_records_in_range=new_records_in_range,
        new_records_delta_pct=new_records_delta_pct,
    )


@router.get("/scraping-activity", response_model=list[ScrapingActivityRead])
async def get_scraping_activity(
    time_range: DashboardRange = Depends(resolve_dashboard_range),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[ScrapingActivityRead]:
    """Run di scraping più recenti, joinati con la fonte di appartenenza.

    Nota sullo status: `ScrapeRun.status` copre solo "running"/"completed"/
    "failed" (vedi `app/models/scrape_runs.py`), mentre il frontend accetta
    anche "queued" e "rate_limited" (vedi `ScrapingRunStatus` in
    `frontend/src/types/index.ts`). Questi due stati non hanno oggi un
    corrispettivo nel modello dati (non esiste una coda persistita né un
    segnale di rate-limit sul singolo run): li lasciamo semplicemente non
    prodotti da questo endpoint, in attesa di un'eventuale estensione dello
    stato dei run.
    """
    stmt = (
        select(ScrapeRun, Source.name, Source.slug)
        .join(Source, Source.id == ScrapeRun.source_id)
        .where(
            ScrapeRun.started_at >= time_range.start,
            ScrapeRun.started_at < time_range.end,
        )
        .order_by(ScrapeRun.started_at.desc())
        .limit(_RECENT_LIMIT)
    )
    rows = (await db.execute(stmt)).all()

    results: list[ScrapingActivityRead] = []
    for run, source_name, source_slug in rows:
        duration_seconds = (
            (run.finished_at - run.started_at).total_seconds() if run.finished_at else None
        )
        results.append(
            ScrapingActivityRead(
                id=run.id,
                source_id=run.source_id,
                source_name=source_name,
                source_code=source_slug,
                status=run.status,
                started_at=run.started_at,
                duration_seconds=duration_seconds,
                items=run.items_found,
                errors=run.errors_count,
            )
        )
    return results


@router.get("/source-health", response_model=SourceHealthBreakdownRead)
async def get_source_health(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> SourceHealthBreakdownRead:
    """Aggrega il numero di fonti per stato di salute corrente."""
    statuses = (await db.execute(select(Source.status))).scalars().all()
    return SourceHealthBreakdownRead(**health_breakdown(statuses))


def _activity_actor(entity_type: str, actor_email: str | None) -> tuple[str, str]:
    """Deriva (actor, actorLabel) da entity_type + eventuale utente collegato.

    `audit_log` non ha una colonna "actor kind": la deduciamo dal tipo di
    entità coinvolta (euristica, documentata qui perché non ovvia) — le
    riclassificazioni media e i riepiloghi AI sono tipicamente iniziati da
    pipeline automatiche, quindi li etichettiamo "ai"/"scraper" quando non
    c'è un utente umano associato alla riga.
    """
    if entity_type in ("scrape_run", "source"):
        return "scraper", "Scraper automatico"
    if entity_type in ("summary_version", "media_classification"):
        return "ai", "Motore AI"
    if actor_email:
        return "admin", actor_email
    return "system", "Sistema"


def _activity_message(action: str, entity_type: str, entity_id: str | None) -> str:
    """Messaggio leggibile per un evento di audit log.

    `audit_log.action`/`entity_type` sono identificatori tecnici (es.
    "suspend_user", "users"), non frasi pronte per l'utente: qui applichiamo
    una resa generica ("Azione — entità id"), che resta comunque più
    leggibile del dato grezzo. Un affinamento futuro potrebbe mappare ogni
    `action` conosciuta a un template dedicato.
    """
    label = action.replace("_", " ").strip().capitalize()
    if entity_id:
        short_id = entity_id[:8]
        return f"{label} — {entity_type} {short_id}"
    return f"{label} — {entity_type}"


@router.get("/activity", response_model=list[ActivityEventRead])
async def get_recent_activity(
    time_range: DashboardRange = Depends(resolve_dashboard_range),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[ActivityEventRead]:
    """Attività recente derivata da `audit_log`.

    È un'approssimazione: `audit_log` traccia solo le azioni esplicitamente
    strumentate con `app.services.audit.log_action` (login/logout, azioni
    admin, pausa/disabilitazione fonte, retry export, rigenerazione
    riepilogo AI...), non ogni evento di sistema (es. un singolo item
    scrapato). Per un feed "vivo" di tutta l'attività (inclusi i run di
    scraping in corso) servirebbe unire anche `scrape_runs`/`scrape_errors`;
    lo teniamo fuori scope qui per non duplicare informazioni già esposte da
    `GET /dashboard/scraping-activity`.
    """
    stmt = (
        select(AuditLog, User.email)
        .outerjoin(User, User.id == AuditLog.user_id)
        .where(
            AuditLog.created_at >= time_range.start,
            AuditLog.created_at < time_range.end,
        )
        .order_by(AuditLog.created_at.desc())
        .limit(_RECENT_LIMIT)
    )
    rows = (await db.execute(stmt)).all()

    results: list[ActivityEventRead] = []
    for log, actor_email in rows:
        actor, actor_label = _activity_actor(log.entity_type, actor_email)
        results.append(
            ActivityEventRead(
                id=str(log.id),
                actor=actor,
                actor_label=actor_label,
                message=_activity_message(log.action, log.entity_type, log.entity_id),
                occurred_at=log.created_at,
            )
        )
    return results
