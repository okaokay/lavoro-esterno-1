"""Public contracts for asynchronous, explicitly-scoped exports."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.common import CamelModel

ExportTypeLiteral = Literal["text_only", "complete_media", "safe_complete"]


class ExportFilters(CamelModel):
    phone: str | None = None
    source: str | None = None
    status: Literal["verified", "unverified", "flagged"] | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None

    @model_validator(mode="after")
    def validate_non_empty(self) -> ExportFilters:
        if not any((self.phone, self.source, self.status, self.date_from, self.date_to)):
            raise ValueError("Specificare almeno un filtro.")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("dateFrom non può essere successiva a dateTo.")
        return self


class ExportJobCreate(CamelModel):
    type: ExportTypeLiteral
    scope: Literal["selected", "filters", "all"] | None = None
    record_ids: list[uuid.UUID] | None = Field(default=None, max_length=1_000)
    filters: ExportFilters | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> ExportJobCreate:
        has_ids = bool(self.record_ids)
        if self.scope is None:
            self.scope = "selected" if has_ids else "filters" if self.filters is not None else None
        if self.scope is None:
            raise ValueError("Specificare scope, recordIds o filters.")
        if self.scope == "selected" and not has_ids:
            raise ValueError("recordIds è obbligatorio per scope='selected'.")
        if self.scope == "selected" and self.filters is not None:
            raise ValueError("filters non è consentito per scope='selected'.")
        if self.scope == "filters" and self.filters is None:
            raise ValueError("filters è obbligatorio per scope='filters'.")
        if self.scope == "all" and (has_ids or self.filters is not None):
            raise ValueError("scope='all' non accetta recordIds o filters.")
        if self.scope != "selected" and has_ids:
            raise ValueError("recordIds è consentito solo per scope='selected'.")
        if self.record_ids and len(set(self.record_ids)) != len(self.record_ids):
            raise ValueError("recordIds contiene duplicati.")
        return self


class ExportJobOut(CamelModel):
    id: uuid.UUID
    type: str
    status: str
    progress_pct: int
    requested_by: str
    requested_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None
    record_count: int
    estimated_uncompressed_bytes: int
    archive_size_bytes: int | None = None
    phone_visibility: Literal["clear", "masked"]
    error_message: str | None = None
    download_url: str | None = None


class DownloadUrlResponse(CamelModel):
    url: str
    expires_at: datetime | None = None
