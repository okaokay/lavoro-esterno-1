"""Operational configuration, background jobs and user notifications."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class MediaClassifierSettings(TimestampMixin, Base):
    __tablename__ = "media_classifier_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    model_name: Mapped[str] = mapped_column(String(100), default="NudeNet", nullable=False)
    model_version: Mapped[str] = mapped_column(
        String(100), default="nudenet-3.4.2-320n", nullable=False
    )
    safe_threshold: Mapped[float] = mapped_column(Float, default=0.20, nullable=False)
    explicit_threshold: Mapped[float] = mapped_column(Float, default=0.65, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class SourcePriorityRecalculationJob(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "source_priority_recalculation_jobs"

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    previous_priority: Mapped[str] = mapped_column(String(20), nullable=False)
    requested_priority: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    records_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    canonicals_changed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NotificationEvent(UUIDPKMixin, Base):
    __tablename__ = "notification_events"

    kind: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    audience: Mapped[str] = mapped_column(String(20), default="operator", nullable=False)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    dedup_key: Mapped[str] = mapped_column(String(250), nullable=False, unique=True, index=True)
    details_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True
    )


class NotificationRead(Base):
    __tablename__ = "notification_reads"

    notification_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notification_events.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
