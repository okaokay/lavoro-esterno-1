"""Test per app.services.canonical: regola di selezione dell'annuncio canonico."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.services.canonical import (
    BAKECA_INCONTRI_SLUG,
    CandidateAdvertisement,
    CandidateSource,
    SourcePriority,
    resolve_canonical,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _source(slug: str, priority: SourcePriority = SourcePriority.medium) -> CandidateSource:
    return CandidateSource(id=uuid.uuid4(), slug=slug, priority=priority)


def _ad(
    source: CandidateSource, *, minutes_ago: int, status: str = "active", **kwargs
) -> CandidateAdvertisement:
    return CandidateAdvertisement(
        id=uuid.uuid4(),
        source=source,
        scraped_at=_NOW - timedelta(minutes=minutes_ago),
        status=status,
        **kwargs,
    )


def test_configured_priority_replaces_bakeca_special_case() -> None:
    bakeca = _source(BAKECA_INCONTRI_SLUG, SourcePriority.low)
    other = _source("megaescort", SourcePriority.high)

    # Nessuno slug è privilegiato: la priorità configurata è il primo criterio.
    ad_other_recent = _ad(other, minutes_ago=1)
    ad_bakeca_older = _ad(bakeca, minutes_ago=60)

    resolution = resolve_canonical([ad_other_recent, ad_bakeca_older])

    assert resolution.chosen.id == ad_other_recent.id
    assert "high" in resolution.reason


def test_same_priority_picks_most_recent_regardless_of_slug() -> None:
    bakeca = _source(BAKECA_INCONTRI_SLUG)
    older = _ad(bakeca, minutes_ago=120)
    newer = _ad(bakeca, minutes_ago=5)

    resolution = resolve_canonical([older, newer])

    assert resolution.chosen.id == newer.id


def test_same_priority_picks_most_recent_active() -> None:
    source_a = _source("megaescort")
    source_b = _source("moscarossa")

    older = _ad(source_a, minutes_ago=100)
    newer = _ad(source_b, minutes_ago=10)

    resolution = resolve_canonical([older, newer])

    assert resolution.chosen.id == newer.id
    assert "medium" in resolution.reason


def test_ignores_non_active_advertisements() -> None:
    source = _source("megaescort")
    removed_recent = _ad(source, minutes_ago=1, status="removed")
    active_older = _ad(source, minutes_ago=50, status="active")

    resolution = resolve_canonical([removed_recent, active_older])

    assert resolution.chosen.id == active_older.id


def test_raises_when_no_active_candidates() -> None:
    source = _source("megaescort")
    only_removed = _ad(source, minutes_ago=1, status="removed")

    with pytest.raises(ValueError):
        resolve_canonical([only_removed])


def test_tie_break_prefers_more_non_empty_fields() -> None:
    source = _source("megaescort")
    same_time = 10

    sparse = _ad(source, minutes_ago=same_time, title=None, description=None, source_url=None)
    rich = _ad(
        source,
        minutes_ago=same_time,
        title="Titolo",
        description="Descrizione",
        source_url="https://example.com/ad/1",
    )

    resolution = resolve_canonical([sparse, rich])

    assert resolution.chosen.id == rich.id


def test_tie_break_prefers_higher_source_priority_when_fields_equal() -> None:
    same_time = 10
    low_priority_source = _source("megaescort", SourcePriority.low)
    high_priority_source = _source("moscarossa", SourcePriority.high)

    ad_low = _ad(low_priority_source, minutes_ago=same_time, title="X", description="Y")
    ad_high = _ad(high_priority_source, minutes_ago=same_time, title="X", description="Y")

    resolution = resolve_canonical([ad_low, ad_high])

    assert resolution.chosen.id == ad_high.id


def test_lower_listing_page_precedes_source_priority() -> None:
    low_source = _source("low-page", SourcePriority.low)
    high_source = _source("high-late", SourcePriority.high)
    early = _ad(low_source, minutes_ago=100, listing_page_number=2)
    late = _ad(high_source, minutes_ago=1, listing_page_number=5)

    assert resolve_canonical([late, early]).chosen.id == early.id


def test_known_listing_page_precedes_unknown_page() -> None:
    source = _source("source")
    known = _ad(source, minutes_ago=100, listing_page_number=20)
    unknown = _ad(source, minutes_ago=1, listing_page_number=None)

    assert resolve_canonical([unknown, known]).chosen.id == known.id
