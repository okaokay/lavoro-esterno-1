"""Schemi Pydantic per i media associati agli annunci."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import CamelModel


class MediaSafetySignals(CamelModel):
    explicit_content: bool = False
    explicit_score: float = 0.0
    face_visible: bool = False
    face_score: float = 0.0
    watermark_present: bool = False
    possible_minor_review: bool = False


class MediaReviewInput(CamelModel):
    classification: str = Field(pattern="^(safe|explicit)$")
    notes: str = Field(min_length=1, max_length=4000)


class MediaReprocessResponse(CamelModel):
    media_id: uuid.UUID
    task_id: str
    queued: bool = True


class MediaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    advertisement_id: uuid.UUID
    original_object_key: str
    derived_object_key: str | None
    display_object_key: str | None
    thumbnail_object_key: str | None
    sha256: str
    perceptual_hash: str | None
    mime_type: str
    classification: str
    classification_confidence: float | None
    classifier_version: str | None
    safety_signals: dict
    processing_status: str
    processing_error: str | None
    review_status: str
    review_notes: str | None
    reviewed_by_user_id: uuid.UUID | None
    reviewed_at: datetime | None
    file_size_bytes: int | None
    width: int | None
    height: int | None
    duration_seconds: float | None
    original_url: str = ""
    display_url: str = ""
    thumbnail_url: str = ""
    created_at: datetime
