"""Persistent GDPR erasure workflow and re-ingestion suppression registry."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin, utcnow

ErasureStatus = sa.Enum(
    "draft",
    "pending",
    "processing",
    "completed",
    "failed",
    name="erasure_request_status",
    create_type=True,
)


class ErasureRequest(UUIDPKMixin, Base):
    __tablename__ = "erasure_requests"

    phone_lookup_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("records.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(ErasureStatus, default="draft", nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    authorization_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    impact_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    result_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SuppressionEntry(UUIDPKMixin, Base):
    __tablename__ = "suppression_entries"

    phone_lookup_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    erasure_request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("erasure_requests.id", ondelete="RESTRICT"), nullable=False
    )
    blocked_ingestions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
