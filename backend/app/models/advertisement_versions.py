"""Immutable material-change snapshots for scraped advertisements."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin, utcnow


class AdvertisementVersion(UUIDPKMixin, Base):
    __tablename__ = "advertisement_versions"
    __table_args__ = (
        UniqueConstraint("advertisement_id", "revision", name="uq_advertisement_versions_revision"),
    )

    advertisement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("advertisements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    scrape_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("scrape_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    media_set_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    changed_fields: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    snapshot_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
