"""Verifica che gli schemi di risposta "view" (quelli che ereditano da
`CamelModel`, vedi app/schemas/common.py) serializzino davvero in camelCase.

È un dettaglio facile da rompere per errore (basta dimenticare
`CamelModel` come base, o un typo nel nome campo) e critico: i moduli
`frontend/src/api/dashboard.ts`, `records.ts`, `sources.ts`, `exports.ts` e
`admin.ts` chiamano `apiRequest<T>` con il tipo TypeScript camelCase
DIRETTAMENTE, senza alcun mapping snake->camel lato client (a differenza di
`auth.ts`). Se il backend rispondesse in snake_case, il frontend leggerebbe
semplicemente `undefined` per ogni campo, silenziosamente.

Testiamo qui la sola serializzazione Pydantic (`model_dump(mode="json",
by_alias=True)`, lo stesso meccanismo che FastAPI usa di default per i
response_model, vedi APIRoute.response_model_by_alias=True) — senza
coinvolgere il layer DB/router, per gli stessi motivi di
tests/test_dashboard_metrics.py.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.schemas.dashboard import DashboardKpisRead, SourceHealthBreakdownRead
from app.schemas.exports import ExportJobOut
from app.schemas.records import RecordAiSummaryVersionRead, RecordSearchResultRead
from app.schemas.sources import ScrapeErrorRead, ScrapeRunRead, SourceRead, SourcesSummaryRead


def test_dashboard_kpis_serializes_camel_case() -> None:
    kpis = DashboardKpisRead(
        total_records=10,
        total_records_delta_pct=5.0,
        active_sources=3,
        active_sources_healthy_pct=100.0,
        new_records_today=2,
        scraping_errors=0,
        scraping_errors_delta=0,
        active_exports=1,
        range_start=datetime(2026, 1, 1, tzinfo=UTC),
        range_end=datetime(2026, 1, 2, tzinfo=UTC),
        new_records_in_range=2,
        new_records_delta_pct=25.0,
    )
    dumped = kpis.model_dump(mode="json", by_alias=True)
    assert dumped["totalRecords"] == 10
    assert dumped["totalRecordsDeltaPct"] == 5.0
    assert dumped["activeSourcesHealthyPct"] == 100.0
    assert dumped["scrapingErrorsDelta"] == 0
    assert dumped["newRecordsInRange"] == 2
    assert dumped["newRecordsDeltaPct"] == 25.0
    assert dumped["rangeStart"] == "2026-01-01T00:00:00Z"
    assert "total_records" not in dumped


def test_source_health_breakdown_serializes_camel_case() -> None:
    breakdown = SourceHealthBreakdownRead(healthy=1, rate_limited=2, error=3, total=6)
    dumped = breakdown.model_dump(mode="json", by_alias=True)
    assert dumped == {"healthy": 1, "rateLimited": 2, "error": 3, "total": 6}


def test_sources_summary_serializes_camel_case() -> None:
    summary = SourcesSummaryRead(total=4, active=2, degraded=1, offline=1)
    dumped = summary.model_dump(mode="json", by_alias=True)
    assert dumped == {"total": 4, "active": 2, "degraded": 1, "offline": 1}


def test_source_read_items_last_24h_uses_lowercase_h() -> None:
    """Regressione: `to_camel("items_last_24h")` produce "itemsLast24H" (H
    maiuscola) per via del confine cifra/lettera — bug reale osservato dal
    vivo (vedi PROGETTO.md § 2, sezione 12) e corretto con un alias
    esplicito in `SourceRead`. Senza questo test, un futuro refactor dello
    schema potrebbe reintrodurre silenziosamente lo stesso difetto."""
    source = SourceRead(
        id=uuid.uuid4(),
        code="bakeca_incontri",
        name="Bakeca Incontri",
        status="healthy",
        enabled=True,
        priority="medium",
        last_run_at=None,
        items_last_24h=42,
        error_rate=0.1,
        consecutive_failures=0,
        has_scrape_config=False,
    )
    dumped = source.model_dump(mode="json", by_alias=True)
    assert dumped["itemsLast24h"] == 42
    assert dumped["enabled"] is True
    assert "itemsLast24H" not in dumped
    assert "items_last_24h" not in dumped


def test_scrape_run_read_serializes_camel_case_with_nested_errors() -> None:
    run_id = uuid.uuid4()
    error_id = uuid.uuid4()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    run = ScrapeRunRead(
        id=run_id,
        started_at=now,
        queued_at=now,
        finished_at=now,
        status="failed",
        items_found=10,
        items_new=2,
        errors_count=1,
        errors=[
            ScrapeErrorRead(
                id=error_id, url="https://example.invalid", error_message="boom", created_at=now
            )
        ],
    )
    dumped = run.model_dump(mode="json", by_alias=True)
    assert dumped["itemsFound"] == 10
    assert dumped["itemsNew"] == 2
    assert dumped["errorsCount"] == 1
    assert dumped["errors"][0]["errorMessage"] == "boom"


def test_record_ai_summary_version_read_serializes_camel_case() -> None:
    version = RecordAiSummaryVersionRead(
        version=3,
        generated_at=None,
        executive_synthesis="Sintesi",
        unverified_claims=["claim"],
        forum_chatter=[],
        sources_used=[],
        provider="ollama",
        model="gemma4:e2b",
    )
    dumped = version.model_dump(mode="json", by_alias=True)
    assert dumped["version"] == 3
    assert dumped["executiveSynthesis"] == "Sintesi"
    assert dumped["unverifiedClaims"] == ["claim"]
    assert dumped["provider"] == "ollama"
    assert dumped["model"] == "gemma4:e2b"


def test_record_search_result_serializes_camel_case() -> None:
    now = datetime.now(UTC)
    result = RecordSearchResultRead(
        id=uuid.uuid4(),
        phone="+393331234567",
        phone_visibility="clear",
        canonical_title="Titolo",
        sources_count=2,
        occurrences_count=5,
        first_seen_at=now,
        last_seen_at=now,
        status="verified",
    )
    dumped = result.model_dump(mode="json", by_alias=True)
    expected_keys = {
        "id",
        "phone",
        "phoneVisibility",
        "canonicalTitle",
        "sourcesCount",
        "occurrencesCount",
        "firstSeenAt",
        "lastSeenAt",
        "status",
    }
    assert expected_keys <= set(dumped.keys())
    assert "canonical_title" not in dumped


def test_export_job_out_serializes_camel_case() -> None:
    job = ExportJobOut(
        id=uuid.uuid4(),
        type="text_only",
        status="pending",
        progress_pct=0,
        requested_by="analyst@example.com",
        requested_at=datetime.now(UTC),
        record_count=1,
        estimated_uncompressed_bytes=0,
        phone_visibility="masked",
        download_url=None,
    )
    dumped = job.model_dump(mode="json", by_alias=True)
    assert dumped["progressPct"] == 0
    assert dumped["requestedBy"] == "analyst@example.com"
    assert dumped["recordCount"] == 1
    assert dumped["downloadUrl"] is None
