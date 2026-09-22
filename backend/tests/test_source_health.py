"""Test per app.services.source_health: aggregazione degli stati delle fonti
usata sia da GET /api/v1/sources/summary sia da
GET /api/v1/dashboard/source-health (vedi il modulo per la mappatura tra i
due vocabolari, non ovvia: "degraded" -> "rateLimited", "offline" -> "error").

Come per test_dashboard_metrics.py, testiamo solo la funzione pura: niente
DB coinvolto (vedi la nota in quel file sulla mancanza di una fixture DB
nei test esistenti di questo repo).
"""

from __future__ import annotations

from app.services.source_health import health_breakdown, summarize_sources_by_status


def test_summarize_sources_by_status_counts_each_bucket() -> None:
    statuses = ["healthy", "healthy", "degraded", "offline", "healthy"]
    summary = summarize_sources_by_status(statuses)
    assert summary == {"total": 5, "active": 3, "degraded": 1, "offline": 1}


def test_summarize_sources_by_status_empty() -> None:
    assert summarize_sources_by_status([]) == {"total": 0, "active": 0, "degraded": 0, "offline": 0}


def test_health_breakdown_remaps_degraded_and_offline() -> None:
    statuses = ["healthy", "degraded", "degraded", "offline"]
    breakdown = health_breakdown(statuses)
    assert breakdown == {"healthy": 1, "rate_limited": 2, "error": 1, "total": 4}


def test_health_breakdown_all_healthy() -> None:
    statuses = ["healthy"] * 3
    breakdown = health_breakdown(statuses)
    assert breakdown == {"healthy": 3, "rate_limited": 0, "error": 0, "total": 3}
