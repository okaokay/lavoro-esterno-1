"""Reusable proxy pools and safe operational history for scraper runs."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class ProxyPool(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "proxy_pools"

    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ProxyEndpoint(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "proxy_endpoints"

    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    scheme: Mapped[str] = mapped_column(String(10), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    credentials_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    managed_by_feed_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("proxy_feeds.id", ondelete="SET NULL"), nullable=True, index=True
    )


class ProxyFeed(UUIDPKMixin, TimestampMixin, Base):
    """File remoto HTTPS che mantiene automaticamente un pool proxy."""

    __tablename__ = "proxy_feeds"

    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    scheme: Mapped[str] = mapped_column(String(10), nullable=False, default="http")
    pool_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("proxy_pools.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    headers_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    header_names: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sync_interval_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    next_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_status: Mapped[str | None] = mapped_column(String(30))
    last_sync_message: Mapped[str | None] = mapped_column(String(500))
    last_imported_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ProxyPoolMember(Base):
    __tablename__ = "proxy_pool_members"

    pool_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("proxy_pools.id", ondelete="CASCADE"), primary_key=True
    )
    proxy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("proxy_endpoints.id", ondelete="RESTRICT"), primary_key=True
    )


class ScrapeRunProxyAttempt(UUIDPKMixin, Base):
    __tablename__ = "scrape_run_proxy_attempts"
    __table_args__ = (
        UniqueConstraint("scrape_run_id", "attempt_number", name="uq_proxy_attempt_run_number"),
    )

    scrape_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scrape_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    proxy_endpoint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("proxy_endpoints.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    operation: Mapped[str] = mapped_column(String(30), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_category: Mapped[str | None] = mapped_column(String(40), nullable=True)
