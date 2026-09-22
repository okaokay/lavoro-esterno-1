"""Persistent ingestion settings and reliable webhook outbox."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin, utcnow


class IngestionSettings(Base):
    __tablename__ = "ingestion_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_ingestion_settings_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    publish_batch_size: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class WebhookEndpoint(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "webhook_endpoints"

    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    all_sources: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    phone_policy: Mapped[str] = mapped_column(String(20), default="masked", nullable=False)
    secret_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class WebhookEndpointSource(Base):
    __tablename__ = "webhook_endpoint_sources"
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), primary_key=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )


class ScrapeRunPayload(UUIDPKMixin, Base):
    __tablename__ = "scrape_run_payloads"
    scrape_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scrape_runs.id", ondelete="CASCADE"), unique=True, index=True
    )
    payload_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class WebhookDelivery(UUIDPKMixin, Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        sa.UniqueConstraint(
            "endpoint_id", "scrape_run_id", name="uq_webhook_delivery_endpoint_run"
        ),
    )

    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), index=True
    )
    scrape_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scrape_runs.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_http_status: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(String(200))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
