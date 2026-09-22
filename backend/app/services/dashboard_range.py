"""Validation shared by the time-filtered dashboard endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Query, status

DEFAULT_DASHBOARD_RANGE = timedelta(hours=24)
MAX_DASHBOARD_RANGE = timedelta(days=90)


@dataclass(frozen=True)
class DashboardRange:
    start: datetime
    end: datetime

    @property
    def duration(self) -> timedelta:
        return self.end - self.start

    @property
    def previous_start(self) -> datetime:
        return self.start - self.duration


def resolve_dashboard_range(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
) -> DashboardRange:
    """Return a bounded, timezone-aware UTC interval, defaulting to 24 hours."""
    now = datetime.now(UTC)
    if start is None and end is None:
        return DashboardRange(start=now - DEFAULT_DASHBOARD_RANGE, end=now)
    if start is None or end is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Sono richiesti sia l'inizio sia la fine dell'intervallo",
        )
    if start.tzinfo is None or end.tzinfo is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Le date della panoramica devono includere il fuso orario",
        )

    start_utc = start.astimezone(UTC)
    end_utc = end.astimezone(UTC)
    if start_utc >= end_utc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="L'inizio dell'intervallo deve precedere la fine",
        )
    if end_utc > now:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La fine dell'intervallo non può essere nel futuro",
        )
    if end_utc - start_utc > MAX_DASHBOARD_RANGE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="L'intervallo della panoramica non può superare 90 giorni",
        )
    return DashboardRange(start=start_utc, end=end_utc)
