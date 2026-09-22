"""Metriche Prometheus specifiche del dominio applicativo.

Le metriche HTTP sono raccolte dal middleware Instrumentator. Questo modulo
aggiunge lo stato degli scraping leggendo ``scrape_runs``: il database resta
cosi la fonte di verita anche dopo un riavvio dell'API o dei worker.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from prometheus_client import Gauge
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.scrape_runs import ScrapeRun
from app.models.sources import Source

_RUN_STATUSES = ("running", "completed", "failed")

SCRAPE_RUNS = Gauge(
    "lavoro_esterno_scrape_runs",
    "Run di scraping presenti nella finestra indicata.",
    ("source_id", "source", "status", "window"),
)
SCRAPE_ITEMS_NEW = Gauge(
    "lavoro_esterno_scrape_items_new",
    "Nuovi annunci trovati dai run nella finestra indicata.",
    ("source_id", "source", "window"),
)
SCRAPE_LAST_RUN_STATUS = Gauge(
    "lavoro_esterno_scrape_last_run_status",
    "Stato one-hot dell'ultimo run della fonte.",
    ("source_id", "source", "status"),
)
SCRAPE_LAST_RUN_TIMESTAMP = Gauge(
    "lavoro_esterno_scrape_last_run_timestamp_seconds",
    "Timestamp Unix di avvio dell'ultimo run della fonte.",
    ("source_id", "source"),
)
SCRAPE_LAST_SUCCESS_TIMESTAMP = Gauge(
    "lavoro_esterno_scrape_last_success_timestamp_seconds",
    "Timestamp Unix dell'ultimo run completato della fonte.",
    ("source_id", "source"),
)
SCRAPE_CONSECUTIVE_FAILURES = Gauge(
    "lavoro_esterno_scrape_consecutive_failures",
    "Numero di run falliti consecutivi a partire dal piu recente.",
    ("source_id", "source"),
)
SCRAPE_RUNNING_DURATION = Gauge(
    "lavoro_esterno_scrape_running_duration_seconds",
    "Durata corrente dell'ultimo run, se ancora in esecuzione.",
    ("source_id", "source"),
)
SCRAPE_COLLECTOR_UP = Gauge(
    "lavoro_esterno_scrape_metrics_collector_up",
    "Vale 1 se l'ultimo aggiornamento delle metriche scraping dal DB e riuscito.",
)

_SOURCE_GAUGES = (
    SCRAPE_RUNS,
    SCRAPE_ITEMS_NEW,
    SCRAPE_LAST_RUN_STATUS,
    SCRAPE_LAST_RUN_TIMESTAMP,
    SCRAPE_LAST_SUCCESS_TIMESTAMP,
    SCRAPE_CONSECUTIVE_FAILURES,
    SCRAPE_RUNNING_DURATION,
)


@dataclass(frozen=True)
class SourceMetricSnapshot:
    """Valori gia aggregati per una fonte, indipendenti da Prometheus/SQL."""

    source_id: str
    source: str
    runs_24h: dict[str, int]
    runs_7d: dict[str, int]
    items_new_24h: int
    items_new_7d: int
    last_status: str | None
    last_run_timestamp: float | None
    last_success_timestamp: float | None
    consecutive_failures: int
    running_duration_seconds: float


def build_source_snapshots(
    sources: Iterable[Source], runs: Iterable[ScrapeRun], now: datetime
) -> list[SourceMetricSnapshot]:
    """Aggrega run ordinandoli internamente, gestendo anche fonti senza storico."""

    by_source: dict[str, list[ScrapeRun]] = {}
    for run in runs:
        by_source.setdefault(str(run.source_id), []).append(run)

    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d = now - timedelta(days=7)
    snapshots: list[SourceMetricSnapshot] = []
    for source in sources:
        source_runs = sorted(
            by_source.get(str(source.id), []), key=lambda item: item.started_at, reverse=True
        )
        counts_24h = {status: 0 for status in _RUN_STATUSES}
        counts_7d = {status: 0 for status in _RUN_STATUSES}
        items_24h = 0
        items_7d = 0
        for run in source_runs:
            if run.started_at >= cutoff_7d:
                counts_7d[run.status] = counts_7d.get(run.status, 0) + 1
                items_7d += run.items_new
            if run.started_at >= cutoff_24h:
                counts_24h[run.status] = counts_24h.get(run.status, 0) + 1
                items_24h += run.items_new

        consecutive_failures = 0
        for run in source_runs:
            if run.status != "failed":
                break
            consecutive_failures += 1

        latest = source_runs[0] if source_runs else None
        last_success = next((run for run in source_runs if run.status == "completed"), None)
        running_duration = 0.0
        if latest is not None and latest.status == "running":
            running_duration = max(0.0, (now - latest.started_at).total_seconds())

        snapshots.append(
            SourceMetricSnapshot(
                source_id=str(source.id),
                source=source.slug,
                runs_24h=counts_24h,
                runs_7d=counts_7d,
                items_new_24h=items_24h,
                items_new_7d=items_7d,
                last_status=latest.status if latest else None,
                last_run_timestamp=latest.started_at.timestamp() if latest else None,
                last_success_timestamp=(
                    last_success.started_at.timestamp() if last_success else None
                ),
                consecutive_failures=consecutive_failures,
                running_duration_seconds=running_duration,
            )
        )
    return snapshots


def _publish_snapshots(snapshots: Iterable[SourceMetricSnapshot]) -> None:
    for gauge in _SOURCE_GAUGES:
        gauge.clear()

    for snapshot in snapshots:
        labels = (snapshot.source_id, snapshot.source)
        for status in _RUN_STATUSES:
            SCRAPE_RUNS.labels(*labels, status, "24h").set(snapshot.runs_24h[status])
            SCRAPE_RUNS.labels(*labels, status, "7d").set(snapshot.runs_7d[status])
            SCRAPE_LAST_RUN_STATUS.labels(*labels, status).set(
                1 if snapshot.last_status == status else 0
            )
        SCRAPE_ITEMS_NEW.labels(*labels, "24h").set(snapshot.items_new_24h)
        SCRAPE_ITEMS_NEW.labels(*labels, "7d").set(snapshot.items_new_7d)
        SCRAPE_CONSECUTIVE_FAILURES.labels(*labels).set(snapshot.consecutive_failures)
        SCRAPE_RUNNING_DURATION.labels(*labels).set(snapshot.running_duration_seconds)
        if snapshot.last_run_timestamp is not None:
            SCRAPE_LAST_RUN_TIMESTAMP.labels(*labels).set(snapshot.last_run_timestamp)
        if snapshot.last_success_timestamp is not None:
            SCRAPE_LAST_SUCCESS_TIMESTAMP.labels(*labels).set(snapshot.last_success_timestamp)


async def refresh_scrape_metrics(db: AsyncSession) -> None:
    """Aggiorna atomicamente quanto possibile le gauge dal database applicativo."""

    now = datetime.now(UTC)
    sources = (await db.execute(select(Source).order_by(Source.slug))).scalars().all()
    runs_stmt = select(ScrapeRun).order_by(ScrapeRun.started_at.desc())
    if settings.TECHNICAL_LOG_RETENTION_DAYS > 0:
        runs_stmt = runs_stmt.where(
            ScrapeRun.started_at
            >= now - timedelta(days=max(7, settings.TECHNICAL_LOG_RETENTION_DAYS))
        )
    runs = (await db.execute(runs_stmt)).scalars().all()
    _publish_snapshots(build_source_snapshots(sources, runs, now))
    SCRAPE_COLLECTOR_UP.set(1)


def mark_scrape_collector_failed() -> None:
    """Segnala il fallimento senza eliminare l'ultimo snapshot valido."""

    SCRAPE_COLLECTOR_UP.set(0)
