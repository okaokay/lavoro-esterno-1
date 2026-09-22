"""Schemi Pydantic per la dashboard operativa (KPI, attività di scraping,
stato delle fonti, attività recente).

Tutti ereditano da `CamelModel`: il frontend (`frontend/src/api/dashboard.ts`)
consuma queste risposte senza alcun layer di mapping intermedio, quindi il
JSON deve già essere in camelCase (vedi `app/schemas/common.py`).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from app.schemas.common import CamelModel


class DashboardKpisRead(CamelModel):
    """KPI aggregati per le card in cima alla dashboard (vedi
    `frontend/src/types/index.ts:DashboardKpis`).

    I campi "delta"/"Pct" che indicano variazioni rispetto a un periodo
    precedente sono approssimazioni pragmatiche: il sistema non ha una
    tabella di snapshot storici dedicata, quindi vengono derivati da
    confronti tra intervalli temporali adiacenti (oggi vs. ieri, ultime 24h
    vs. le 24h precedenti). Vedi i commenti nel router
    (`app/api/v1/dashboard.py`) per il dettaglio di ciascun calcolo.
    """

    total_records: int
    total_records_delta_pct: float
    active_sources: int
    active_sources_healthy_pct: float
    new_records_today: int
    scraping_errors: int
    scraping_errors_delta: int
    active_exports: int
    range_start: datetime
    range_end: datetime
    new_records_in_range: int
    new_records_delta_pct: float


class ScrapingActivityRead(CamelModel):
    id: uuid.UUID
    source_id: uuid.UUID
    source_name: str
    source_code: str
    status: str
    started_at: datetime | None
    duration_seconds: float | None
    items: int | None
    errors: int | None


class SourceHealthBreakdownRead(CamelModel):
    healthy: int
    rate_limited: int
    error: int
    total: int


class ActivityEventRead(CamelModel):
    id: str
    actor: str
    actor_label: str
    message: str
    occurred_at: datetime
