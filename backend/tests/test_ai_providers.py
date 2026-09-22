"""Configurazione e adapter dei provider AI locali e remoti."""

import json
from types import SimpleNamespace

import httpx
import pytest

from app.api.v1.ai_settings import _provider_read
from app.models.ai_settings import AIProviderConfig, AISettings
from app.services.ai_config import ProviderRuntimeConfig, validate_custom_ai_endpoint
from app.services.ai_credentials import decrypt_ai_credential, encrypt_ai_credential
from app.services.summary_generator import (
    SUMMARY_PROMPTS,
    AnthropicSummaryProvider,
    GoogleSummaryProvider,
    OllamaSummaryProvider,
    OpenAICompatibleSummaryProvider,
    OpenAISummaryProvider,
    ProviderError,
    _StructuredSummary,
    create_summary_provider,
    prompt_for,
)
from app.workers.tasks_ai import AIDisabledError, _reserve_budget, summary_input_hash


def _valid_summary() -> dict:
    return {
        "summary": "Sintesi sintetica.",
        "advertisement_information": [
            {"source_ref": "source-1", "title": "Test", "facts": ["Fatto"]}
        ],
        "forum_information": [],
        "unverified_claims": [],
        "sources": ["source-1"],
    }


def test_ai_credentials_are_randomized_and_round_trip() -> None:
    first = encrypt_ai_credential("secret-provider-key")
    second = encrypt_ai_credential("secret-provider-key")
    assert first != second
    assert b"secret-provider-key" not in first
    assert decrypt_ai_credential(first) == "secret-provider-key"


def test_provider_read_never_serializes_credential() -> None:
    row = AIProviderConfig(
        provider="openai",
        display_name="OpenAI",
        model_name="test-model",
        enabled=False,
        api_key_encrypted=b"ciphertext",
        config_json={},
        revision=2,
    )
    dumped = _provider_read(row, "ollama").model_dump(mode="json", by_alias=True)
    assert dumped["credentialConfigured"] is True
    assert "apiKey" not in dumped
    assert "ciphertext" not in json.dumps(dumped)


def test_ollama_uses_schema_and_normalizes_usage() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "message": {"content": json.dumps(_valid_summary())},
                "prompt_eval_count": 41,
                "eval_count": 12,
            },
        )

    config = ProviderRuntimeConfig("ollama", "gemma4:e2b", "http://ollama:11434", None)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    generated = OllamaSummaryProvider(config, client).generate_structured(
        {"advertisements": [], "forum_snippets": []}
    )
    assert captured["model"] == "gemma4:e2b"
    assert captured["stream"] is False
    assert captured["format"] == _StructuredSummary.model_json_schema()
    assert (generated.input_tokens, generated.output_tokens) == (41, 12)


def test_invalid_structured_output_is_classified_as_validation_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": "not-json"}})

    config = ProviderRuntimeConfig("ollama", "gemma4:e2b", "http://ollama:11434", None)
    with pytest.raises(ProviderError) as error:
        OllamaSummaryProvider(
            config, httpx.Client(transport=httpx.MockTransport(handler))
        ).generate_structured({})
    assert error.value.validation is True
    assert error.value.retryable is False


def test_openai_responses_uses_store_false_and_usage() -> None:
    calls = {}

    class Responses:
        @staticmethod
        def parse(**kwargs):
            calls.update(kwargs)
            return SimpleNamespace(
                output_parsed=_StructuredSummary.model_validate(_valid_summary()),
                usage=SimpleNamespace(
                    input_tokens=30,
                    output_tokens=9,
                    input_tokens_details=SimpleNamespace(cached_tokens=4),
                ),
            )

    client = SimpleNamespace(responses=Responses())
    config = ProviderRuntimeConfig("openai", "gpt-test", None, "secret")
    generated = OpenAISummaryProvider(config, client).generate_structured({"test": True})
    assert calls["store"] is False
    assert calls["text_format"] is _StructuredSummary
    assert (generated.input_tokens, generated.output_tokens, generated.cached_input_tokens) == (
        30,
        9,
        4,
    )


def test_openai_compatible_uses_strict_json_schema() -> None:
    calls = {}

    class Completions:
        @staticmethod
        def create(**kwargs):
            calls.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content=json.dumps(_valid_summary())))
                ],
                usage=SimpleNamespace(
                    prompt_tokens=18,
                    completion_tokens=7,
                    prompt_tokens_details=SimpleNamespace(cached_tokens=2),
                ),
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    config = ProviderRuntimeConfig("groq", "model", "https://api.groq.com/openai/v1", "key")
    generated = OpenAICompatibleSummaryProvider(config, client).generate_structured({})
    assert calls["response_format"]["json_schema"]["strict"] is True
    schema = calls["response_format"]["json_schema"]["schema"]
    assert set(schema["$defs"]["_AdvertisementFact"]["properties"]) == set(
        schema["$defs"]["_AdvertisementFact"]["required"]
    )
    assert (generated.input_tokens, generated.output_tokens, generated.cached_input_tokens) == (
        18,
        7,
        2,
    )


def test_anthropic_native_adapter_uses_schema_and_usage() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        assert request.headers["x-api-key"] == "anthropic-secret"
        return httpx.Response(
            200,
            json={
                "content": [{"text": json.dumps(_valid_summary())}],
                "usage": {"input_tokens": 22, "output_tokens": 8, "cache_read_input_tokens": 3},
            },
        )

    config = ProviderRuntimeConfig("anthropic", "claude-test", None, "anthropic-secret")
    generated = AnthropicSummaryProvider(
        config, httpx.Client(transport=httpx.MockTransport(handler))
    ).generate_structured({})
    assert captured["output_config"]["format"]["type"] == "json_schema"
    assert (generated.input_tokens, generated.output_tokens, generated.cached_input_tokens) == (
        22,
        8,
        3,
    )


def test_google_native_adapter_keeps_key_out_of_url_and_uses_schema() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        assert request.headers["x-goog-api-key"] == "google-secret"
        assert "google-secret" not in str(request.url)
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": json.dumps(_valid_summary())}]}}],
                "usageMetadata": {
                    "promptTokenCount": 17,
                    "candidatesTokenCount": 6,
                    "cachedContentTokenCount": 1,
                },
            },
        )

    config = ProviderRuntimeConfig("google", "gemini-test", None, "google-secret")
    generated = GoogleSummaryProvider(
        config, httpx.Client(transport=httpx.MockTransport(handler))
    ).generate_structured({})
    assert captured["generationConfig"]["responseMimeType"] == "application/json"
    assert "responseJsonSchema" in captured["generationConfig"]
    assert (generated.input_tokens, generated.output_tokens, generated.cached_input_tokens) == (
        17,
        6,
        1,
    )


def test_factory_never_falls_back_for_unknown_provider() -> None:
    with pytest.raises(ProviderError, match="non supportato"):
        create_summary_provider(ProviderRuntimeConfig("unknown", "model", None, None))


def test_prompt_versions_preserve_history_and_default_to_italian() -> None:
    historical = ProviderRuntimeConfig(
        "ollama", "model", "http://ollama:11434", None, {"prompt_version": "summary-v1"}
    )
    italian = ProviderRuntimeConfig(
        "ollama", "model", "http://ollama:11434", None, {"prompt_version": "summary-v2-it"}
    )
    assert prompt_for(historical) == SUMMARY_PROMPTS["summary-v1"]
    assert "interamente in italiano" in prompt_for(italian)
    assert prompt_for(ProviderRuntimeConfig("ollama", "model", None, None)) == prompt_for(italian)
    with pytest.raises(ProviderError, match="Versione prompt"):
        prompt_for(
            ProviderRuntimeConfig("ollama", "model", None, None, {"prompt_version": "inesistente"})
        )


def test_cache_hash_separates_provider_model_and_prompt() -> None:
    payload = {"advertisements": [], "forum_snippets": []}
    base = summary_input_hash(payload, "ollama", "gemma4:e2b", "summary-v1")
    assert base != summary_input_hash(payload, "openai", "gemma4:e2b", "summary-v1")
    assert base != summary_input_hash(payload, "ollama", "gemma4:e4b", "summary-v1")
    assert base != summary_input_hash(payload, "ollama", "gemma4:e2b", "summary-v2")


def test_custom_endpoint_rejects_http_and_private_addresses() -> None:
    with pytest.raises(ValueError):
        validate_custom_ai_endpoint("http://example.com/v1")
    with pytest.raises(ValueError):
        validate_custom_ai_endpoint("https://127.0.0.1/v1")


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    def expire(self, _key: str, _seconds: int) -> None:
        return None

    def incrby(self, key: str, value: int) -> int:
        self.values[key] = self.values.get(key, 0) + value
        return self.values[key]

    def decrby(self, key: str, value: int) -> int:
        self.values[key] = self.values.get(key, 0) - value
        return self.values[key]


def test_local_provider_runs_with_zero_cloud_budget(monkeypatch) -> None:
    monkeypatch.setattr("app.workers.tasks_ai._redis", lambda: _FakeRedis())
    ai = AISettings(
        user_daily_request_limit=20,
        provider_requests_per_minute=10,
        global_daily_token_budget=0,
    )
    assert _reserve_budget(__import__("uuid").uuid4(), 500, ai, "ollama") is None


def test_remote_provider_is_blocked_with_zero_cloud_budget() -> None:
    ai = AISettings(
        user_daily_request_limit=20,
        provider_requests_per_minute=10,
        global_daily_token_budget=0,
    )
    with pytest.raises(AIDisabledError, match="budget token"):
        _reserve_budget(__import__("uuid").uuid4(), 500, ai, "openai")
