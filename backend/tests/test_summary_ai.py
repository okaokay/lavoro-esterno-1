"""Contratto, redazione e versionamento degli input/output dei riepiloghi AI."""

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.ai_settings import AISettings
from app.services.summary_generator import OpenAISummaryGenerator, _StructuredSummary
from app.workers.tasks_ai import (
    AIDisabledError,
    _reserve_budget,
    _sanitized_input,
    summary_input_hash,
)


class _FakeResponses:
    def __init__(self, parsed):
        self.parsed = parsed
        self.kwargs = None

    def parse(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            output_parsed=self.parsed,
            usage=SimpleNamespace(
                input_tokens=120,
                output_tokens=35,
                input_tokens_details=SimpleNamespace(cached_tokens=20),
            ),
        )


def test_structured_response_disables_storage_and_preserves_usage():
    parsed = _StructuredSummary(
        summary="Due occorrenze redatte.",
        advertisement_information=[
            {"source_ref": "source-1", "title": "Example", "facts": ["fatto redatto"]}
        ],
        forum_information=[],
        unverified_claims=[],
        sources=["source-1"],
    )
    responses = _FakeResponses(parsed)
    generated = OpenAISummaryGenerator(
        client=SimpleNamespace(responses=responses)
    ).generate_structured({"advertisements": [], "forum_snippets": []})

    assert responses.kwargs["store"] is False
    assert responses.kwargs["text_format"] is _StructuredSummary
    assert generated.payload.sources == ["source-1"]
    assert (generated.input_tokens, generated.output_tokens, generated.cached_input_tokens) == (
        120,
        35,
        20,
    )


def test_provider_input_omits_phone_and_urls_and_hash_is_deterministic():
    advertisement = SimpleNamespace(
        title="Titolo",
        description="Testo con +39 333 123 4567 e https://other.example/persona",
        source_url="https://personal.example/profile/123",
        scraped_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    source = SimpleNamespace(id=uuid.uuid4())
    payload, local_mapping = _sanitized_input([(advertisement, source)])
    encoded = json.dumps(payload)

    assert "personal.example" not in encoded
    assert "other.example" not in encoded
    assert "333 123 4567" not in encoded
    assert "[PHONE REDACTED]" in encoded
    assert local_mapping == {"source-1": advertisement.source_url}
    assert summary_input_hash(payload) == summary_input_hash(json.loads(encoded))
    assert summary_input_hash(payload, record_content_revision=1) != summary_input_hash(
        payload, record_content_revision=2
    )


def test_ai_is_disabled_without_explicit_limits():
    ai = AISettings(user_daily_request_limit=0, provider_requests_per_minute=10)
    with pytest.raises(AIDisabledError, match="disabilitata"):
        _reserve_budget(uuid.uuid4(), 100, ai, "ollama")


def test_redacted_evaluation_dataset_has_stable_shape_and_internal_sources():
    fixture_path = Path(__file__).parent / "fixtures/summary_eval.json"
    fixture = json.loads(fixture_path.read_text())
    assert fixture
    for case in fixture:
        assert set(case) == {"name", "input", "allowed_sources"}
        assert set(case["input"]) == {"advertisements", "forum_snippets"}
        refs = {item["source_ref"] for item in case["input"]["advertisements"]}
        assert set(case["allowed_sources"]) <= refs
        assert not re.search(r"(?:\+?\d[\s.-]?){7,}", json.dumps(case))
