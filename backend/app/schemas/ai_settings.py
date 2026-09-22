"""Contratti API per la pagina amministrativa delle impostazioni AI."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, HttpUrl, model_validator

from app.schemas.common import CamelModel

AIProviderName = Literal[
    "ollama",
    "openai",
    "anthropic",
    "google",
    "groq",
    "mistral",
    "openrouter",
    "custom_openai",
]


class AIProviderConfigRead(CamelModel):
    provider: AIProviderName
    display_name: str
    model: str
    enabled: bool
    active: bool
    base_url: str | None
    credential_configured: bool
    options: dict[str, str]
    revision: int
    last_tested_at: datetime | None
    last_test_success: bool | None


class AISettingsRead(CamelModel):
    active_provider: AIProviderName
    prompt_version: str
    user_daily_request_limit: int
    provider_requests_per_minute: int
    global_daily_token_budget: int
    revision: int
    providers: list[AIProviderConfigRead]


class AISettingsUpdate(CamelModel):
    active_provider: AIProviderName | None = None
    user_daily_request_limit: int | None = Field(default=None, ge=1, le=10000)
    provider_requests_per_minute: int | None = Field(default=None, ge=1, le=10000)
    global_daily_token_budget: int | None = Field(default=None, ge=0)
    expected_revision: int


class AIProviderConfigUpdate(CamelModel):
    model: str | None = Field(default=None, min_length=1, max_length=200)
    enabled: bool | None = None
    base_url: HttpUrl | None = None
    api_key: str | None = Field(default=None, min_length=8, max_length=1000)
    clear_credential: bool = False
    options: dict[str, str] | None = None
    expected_revision: int

    @model_validator(mode="after")
    def validate_credential_change(self) -> AIProviderConfigUpdate:
        if self.api_key and self.clear_credential:
            raise ValueError("apiKey e clearCredential sono mutuamente esclusivi.")
        return self


class AIModelCatalogRead(CamelModel):
    provider: AIProviderName
    models: list[str]
    cached: bool


class AIProviderTestRead(CamelModel):
    provider: AIProviderName
    success: bool
    latency_ms: int
    message: str
