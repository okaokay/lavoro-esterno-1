"""Modello `Source`: una fonte/sito da cui vengono raccolti annunci."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin

SourcePriority = sa.Enum("high", "medium", "low", name="source_priority", create_type=True)
SourceStatus = sa.Enum("healthy", "degraded", "offline", name="source_status", create_type=True)


class Source(UUIDPKMixin, TimestampMixin, Base):
    """Fonte configurata (es. un sito di annunci). Lo `slug` collega la riga
    DB al connettore scraper concreto registrato in `app/scrapers/registry.py`.
    """

    __tablename__ = "sources"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True, index=True)

    # Primo criterio nella selezione dell'annuncio canonico: vince la fonte
    # con priorità più alta, poi completezza, recenza e ID deterministico.
    priority: Mapped[str] = mapped_column(SourcePriority, default="medium", nullable=False)
    status: Mapped[str] = mapped_column(SourceStatus, default="healthy", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    automatic_scraping_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    scrape_interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_scrape_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_completed_scrape_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_schedule_skip_reason: Mapped[str | None] = mapped_column(String(80))
    schedule_revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Configurazione del motore di scraping generico (vedi
    # app/scrapers/generic.py:GenericScraper), validata a livello di schema
    # Pydantic (app/schemas/sources.py:ScrapeConfigInput) prima di essere
    # salvata qui. Nullable: una fonte registrata come classe Python stub
    # in app/scrapers/registry.py non ha bisogno di questa configurazione
    # finché non viene riattivata tramite il motore generico.
    scrape_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    proxy_pool_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("proxy_pools.id", ondelete="SET NULL"), nullable=True, index=True
    )
    watermark_removal_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    watermark_authorization_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    watermark_regions: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
