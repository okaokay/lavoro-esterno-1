"""Contratto fail-closed della pulizia editoriale locale con Gemma."""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from app.services.content_sanitizer import ContentSanitizationError, sanitize_normalized
from app.services.integration_crypto import decrypt_json


class _Result:
    def __init__(self, provider):
        self.provider = provider

    def scalar_one_or_none(self):
        return self.provider


class _Session:
    def __init__(self):
        self.provider = SimpleNamespace(
            provider="ollama",
            enabled=True,
            model_name="gemma3:4b",
            base_url=None,
            api_key_encrypted=None,
            config_json={},
            revision=7,
        )

    def execute(self, _statement):
        return _Result(self.provider)


class _Response:
    def __init__(self, fields):
        self.fields = fields

    def raise_for_status(self):
        return None

    def json(self):
        return {"message": {"content": json.dumps({"fields": self.fields})}}


def test_clean_text_is_preserved_byte_for_byte(monkeypatch) -> None:
    original = {"title": "Titolo  25", "description": "Descrizione pulita", "custom_fields": {}}
    rows = [
        {"path": "title", "changed": False, "value": original["title"]},
        {"path": "description", "changed": False, "value": original["description"]},
    ]
    monkeypatch.setattr(
        "app.services.content_sanitizer.httpx.post", lambda *a, **k: _Response(rows)
    )

    result = sanitize_normalized(_Session(), original, {})

    assert result.normalized == original
    assert result.metadata["changed"] == []
    assert decrypt_json(result.original_encrypted)["fields"]["title"] == "Titolo  25"


def test_flagged_nested_review_is_rewritten(monkeypatch) -> None:
    original = {
        "title": "Pulito",
        "description": "Pulita",
        "custom_fields": {"reviews": [{"body": "testo spinto 25"}]},
    }
    rows = [
        {"path": "title", "changed": False, "value": "Pulito"},
        {"path": "description", "changed": False, "value": "Pulita"},
        {
            "path": "custom_fields.reviews.0.body",
            "changed": True,
            "value": "testo adulto 25",
        },
    ]
    monkeypatch.setattr(
        "app.services.content_sanitizer.httpx.post", lambda *a, **k: _Response(rows)
    )
    config = {
        "fields": {
            "reviews": {
                "itemFields": {"body": {"sanitizeWithAi": True}},
            }
        }
    }

    result = sanitize_normalized(_Session(), original, config)

    assert result.normalized["custom_fields"]["reviews"][0]["body"] == "testo adulto 25"


def test_changed_text_cannot_alter_numbers(monkeypatch) -> None:
    rows = [
        {"path": "title", "changed": True, "value": "Titolo 30"},
        {"path": "description", "changed": False, "value": "Pulita"},
    ]
    monkeypatch.setattr(
        "app.services.content_sanitizer.httpx.post", lambda *a, **k: _Response(rows)
    )

    with pytest.raises(ContentSanitizationError) as caught:
        sanitize_normalized(
            _Session(),
            {"title": "Titolo 25", "description": "Pulita", "custom_fields": {}},
            {},
        )

    assert caught.value.error_code == "content_sanitization_numbers_changed"
    assert "dati numerici" in str(caught.value)
    assert "Titolo 25" not in str(caught.value)


def test_timeout_has_specific_safe_diagnostic(monkeypatch) -> None:
    def timeout(*_args, **_kwargs):
        raise httpx.ReadTimeout("https://internal-sensitive-target/path")

    monkeypatch.setattr("app.services.content_sanitizer.httpx.post", timeout)

    with pytest.raises(ContentSanitizationError) as caught:
        sanitize_normalized(
            _Session(),
            {"title": "Titolo", "description": "Descrizione", "custom_fields": {}},
            {},
        )

    assert caught.value.error_code == "content_sanitization_timeout"
    assert "3 tentativi" in str(caught.value)
    assert "internal-sensitive-target" not in str(caught.value)


def test_incomplete_response_has_specific_diagnostic(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.content_sanitizer.httpx.post", lambda *a, **k: _Response([])
    )

    with pytest.raises(ContentSanitizationError) as caught:
        sanitize_normalized(
            _Session(),
            {"title": "Titolo", "description": "Descrizione", "custom_fields": {}},
            {},
        )

    assert caught.value.error_code == "content_sanitization_incomplete_response"
    assert "tutti i campi richiesti" in str(caught.value)
