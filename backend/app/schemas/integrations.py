"""Admin contracts for ingestion batching and webhook destinations."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator

from app.schemas.common import CamelModel


class IngestionSettingsRead(CamelModel):
    publish_batch_size: int
    revision: int
    sanitization_provider: str = "ollama"
    sanitization_model: str


class IngestionSettingsUpdate(CamelModel):
    publish_batch_size: int = Field(ge=1, le=500)
    expected_revision: int = Field(ge=1)


class WebhookEndpointInput(CamelModel):
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(max_length=2000)
    enabled: bool = True
    all_sources: bool = True
    source_ids: list[uuid.UUID] = Field(default_factory=list)
    phone_policy: Literal["clear", "masked", "excluded"] = "masked"
    secret: str | None = Field(default=None, min_length=16, max_length=1000)

    @field_validator("url")
    @classmethod
    def https_public_shape(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Il webhook deve usare HTTPS senza credenziali nell'URL.")
        return value

    @model_validator(mode="after")
    def source_scope(self):
        if self.all_sources and self.source_ids:
            raise ValueError("sourceIds deve essere vuoto per tutte le fonti.")
        if not self.all_sources and not self.source_ids:
            raise ValueError("Selezionare almeno una fonte.")
        return self


class WebhookEndpointUpdate(WebhookEndpointInput):
    clear_secret: bool = False


class WebhookEndpointRead(CamelModel):
    id: uuid.UUID
    name: str
    url: str
    enabled: bool
    all_sources: bool
    source_ids: list[uuid.UUID]
    phone_policy: Literal["clear", "masked", "excluded"]
    secret_configured: bool
    revision: int
    created_at: datetime
    updated_at: datetime


class SanitizationBackfillRead(CamelModel):
    task_id: str
    queued: bool = True
