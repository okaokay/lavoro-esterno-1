"""Modello `ScrapeError`: singolo errore verificatosi durante uno ScrapeRun."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin, utcnow


class ScrapeError(UUIDPKMixin, Base):
    __tablename__ = "scrape_errors"

    scrape_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scrape_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    # Indicizzato: query di retention (app.workers.tasks_maintenance.cleanup_expired_data).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
