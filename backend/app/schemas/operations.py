"""Contratti API della console operativa: priorità, classifier, notifiche e salute."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.common import CamelModel


class SourcePriorityRead(CamelModel):
    source_id: uuid.UUID
    name: str
    code: str
    status: str
    priority: Literal["high", "medium", "low"]
    affected_records: int
    latest_job: SourcePriorityJobRead | None = None


class SourcePriorityUpdate(CamelModel):
    priority: Literal["high", "medium", "low"]


class SourcePriorityJobRead(CamelModel):
    id: uuid.UUID
    source_id: uuid.UUID
    previous_priority: str
    requested_priority: str
    status: str
    records_total: int
    records_processed: int
    canonicals_changed: int
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class ClassifierSettingsUpdate(CamelModel):
    safe_threshold: float = Field(ge=0, le=1)
    explicit_threshold: float = Field(ge=0, le=1)
    expected_revision: int = Field(ge=1)

    @model_validator(mode="after")
    def thresholds_are_ordered(self):
        if self.safe_threshold >= self.explicit_threshold:
            raise ValueError("La soglia safe deve essere inferiore alla soglia explicit.")
        return self


class ClassifierStats(CamelModel):
    classifications: dict[str, int]
    processing: dict[str, int]
    reviews: dict[str, int]


class ClassifierSettingsRead(CamelModel):
    model_name: str
    model_version: str
    safe_threshold: float
    explicit_threshold: float
    revision: int
    stats: ClassifierStats


class ClassifierReprocessInput(CamelModel):
    scope: Literal["failed", "needs_review"]


class ClassifierReprocessResult(CamelModel):
    scope: str
    queued: int


class NotificationReadOut(CamelModel):
    id: uuid.UUID
    kind: str
    severity: str
    title: str
    message: str
    link: str | None
    is_read: bool
    created_at: datetime


class NotificationList(CamelModel):
    items: list[NotificationReadOut]
    unread_count: int


class SystemComponentRead(CamelModel):
    name: str
    status: Literal["healthy", "degraded", "unavailable"]
    latency_ms: int | None = None
    message: str | None = None


class SystemStatusRead(CamelModel):
    status: Literal["healthy", "degraded", "unavailable"]
    checked_at: datetime
    components: list[SystemComponentRead]
