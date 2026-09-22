"""Admin-only GDPR erasure request contracts; no phone hash is ever returned."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.common import CamelModel


class ErasureRequestCreate(CamelModel):
    phone: str = Field(min_length=6, max_length=40)
    reason: str = Field(min_length=3, max_length=2_000)
    authorization_reference: str = Field(min_length=3, max_length=500)


class ErasureRequestRead(CamelModel):
    id: uuid.UUID
    record_id: uuid.UUID | None = None
    status: str
    reason: str
    authorization_reference: str
    impact: dict
    result: dict | None = None
    error_message: str | None = None
    created_at: datetime
    confirmed_at: datetime | None = None
    completed_at: datetime | None = None
