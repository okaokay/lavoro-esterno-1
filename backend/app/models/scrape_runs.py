"""Modello `ScrapeRun`: esecuzione di uno scraping per una fonte."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin, utcnow

ScrapeRunStatus = sa.Enum(
    "pending", "running", "completed", "failed", name="scrape_run_status", create_type=True
)


class ScrapeRun(UUIDPKMixin, Base):
    __tablename__ = "scrape_runs"
    __table_args__ = (Index("ix_scrape_runs_started_at", "started_at"),)

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    trigger_type: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    status: Mapped[str] = mapped_column(ScrapeRunStatus, default="running", nullable=False)
    items_found: Mapped[int] = mapped_column(Integer, default=0)
    items_new: Mapped[int] = mapped_column(Integer, default=0)
    items_updated: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    items_unchanged: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    errors_count: Mapped[int] = mapped_column(Integer, default=0)
    pages_visited: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pagination_mode: Mapped[str] = mapped_column(
        String(20), default="none", server_default="none", nullable=False
    )
    pagination_stop_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    proxy_attempts_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    proxy_rotations_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    proxy_stop_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
