"""Regressions for per-source fixed-delay automatic scraping."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.sources import SourceScheduleUpdate
from app.workers.tasks_scraper import _set_next_after_completion


def _source(**overrides):
    values = {
        "automatic_scraping_enabled": True,
        "enabled": True,
        "scrape_config": {"start_urls": ["https://example.test"]},
        "scrape_interval_minutes": 60,
        "next_scrape_at": None,
        "last_completed_scrape_at": None,
        "last_schedule_skip_reason": "active_run",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_fixed_delay_starts_at_completion_not_start_time() -> None:
    source = _source()
    finished_at = datetime(2026, 9, 8, 10, 20, tzinfo=UTC)

    _set_next_after_completion(source, finished_at)

    assert source.last_completed_scrape_at == finished_at
    assert source.next_scrape_at == datetime(2026, 9, 8, 11, 20, tzinfo=UTC)
    assert source.last_schedule_skip_reason is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"automatic_scraping_enabled": False},
        {"enabled": False},
        {"scrape_config": None},
        {"scrape_interval_minutes": None},
    ],
)
def test_completion_does_not_schedule_ineligible_source(overrides: dict) -> None:
    source = _source(**overrides)
    finished_at = datetime.now(UTC)

    _set_next_after_completion(source, finished_at)

    assert source.last_completed_scrape_at == finished_at
    assert source.next_scrape_at is None


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [(15, "minutes", 15), (3, "hours", 180), (30, "days", 43_200)],
)
def test_schedule_input_normalizes_supported_units(value: int, unit: str, expected: int) -> None:
    payload = SourceScheduleUpdate(
        enabled=True,
        intervalValue=value,
        intervalUnit=unit,
        revision=1,
    )
    assert payload.normalized_minutes() == expected


@pytest.mark.parametrize(
    ("value", "unit"),
    [(14, "minutes"), (31, "days")],
)
def test_schedule_input_rejects_out_of_range_intervals(value: int, unit: str) -> None:
    with pytest.raises(ValidationError):
        SourceScheduleUpdate(
            enabled=True,
            intervalValue=value,
            intervalUnit=unit,
            revision=1,
        )


def test_manual_completion_replaces_an_existing_deadline() -> None:
    source = _source(next_scrape_at=datetime(2026, 9, 8, 11, tzinfo=UTC))
    manual_finished_at = datetime(2026, 9, 8, 10, 45, tzinfo=UTC)

    _set_next_after_completion(source, manual_finished_at)

    assert source.next_scrape_at == manual_finished_at + timedelta(hours=1)
