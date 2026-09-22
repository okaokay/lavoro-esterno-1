"""Contratto pubblico /metrics e aggregazione dello stato scraping."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app import main
from app.db import get_db
from app.services.observability_metrics import build_source_snapshots


def _source(slug: str = "fonte-test") -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), slug=slug)


def _run(source_id, status: str, started_at: datetime, items_new: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        source_id=source_id,
        status=status,
        started_at=started_at,
        items_new=items_new,
    )


def test_source_snapshot_handles_empty_history() -> None:
    source = _source()
    snapshot = build_source_snapshots([source], [], datetime.now(UTC))[0]
    assert snapshot.last_status is None
    assert snapshot.consecutive_failures == 0
    assert snapshot.runs_24h == {"running": 0, "completed": 0, "failed": 0}


def test_source_snapshot_counts_windows_failures_and_running_age() -> None:
    now = datetime.now(UTC)
    source = _source()
    failures = [
        _run(source.id, "failed", now - timedelta(minutes=5), 0),
        _run(source.id, "failed", now - timedelta(hours=2), 0),
        _run(source.id, "failed", now - timedelta(hours=3), 0),
        _run(source.id, "completed", now - timedelta(days=2), 7),
    ]
    snapshot = build_source_snapshots([source], failures, now)[0]
    assert snapshot.runs_24h["failed"] == 3
    assert snapshot.runs_7d["completed"] == 1
    assert snapshot.items_new_7d == 7
    assert snapshot.consecutive_failures == 3
    assert snapshot.last_success_timestamp == failures[-1].started_at.timestamp()

    running = build_source_snapshots(
        [source], [_run(source.id, "running", now - timedelta(minutes=20))], now
    )[0]
    assert running.running_duration_seconds == 1200


def test_metrics_is_internal_unauthenticated_and_not_in_openapi(monkeypatch) -> None:
    refresh = AsyncMock()
    monkeypatch.setattr(main.observability_metrics, "refresh_scrape_metrics", refresh)

    async def fake_db():
        yield object()

    main.app.dependency_overrides[get_db] = fake_db
    try:
        with TestClient(main.app) as client:
            client.get("/api/v1/healthz")
            response = client.get("/metrics")
            schema = client.get("/openapi.json").json()
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "lavoro_esterno_http_requests_total" in response.text
    assert "/metrics" not in schema["paths"]
    refresh.assert_awaited_once()


def test_metrics_stays_available_when_scrape_collector_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        main.observability_metrics,
        "refresh_scrape_metrics",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
    )

    async def fake_db():
        yield object()

    main.app.dependency_overrides[get_db] = fake_db
    try:
        with TestClient(main.app) as client:
            response = client.get("/metrics")
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "lavoro_esterno_scrape_metrics_collector_up 0.0" in response.text
