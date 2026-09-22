"""Modello `Advertisement`: un singolo annuncio scaricato da una fonte."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPKMixin, utcnow

if TYPE_CHECKING:
    from app.models.record import Record
    from app.models.sources import Source

AdvertisementStatus = sa.Enum(
    "active", "removed", "invalid", name="advertisement_status", create_type=True
)


class Advertisement(UUIDPKMixin, Base):
    """Annuncio raccolto da una fonte esterna, associato a un `Record`."""

    __tablename__ = "advertisements"
    __table_args__ = (
        # Filtro "annunci attivi di una fonte" (selezione canonica, dashboard).
        # L'indice full-text GIN su title/description (ix_advertisements_fulltext)
        # è un'espressione funzionale, non dichiarabile qui come Index ORM
        # "portabile": vive solo nella migrazione dedicata (vedi
        # migrations/versions/20260829091500_additional_indexes.py).
        Index("ix_advertisements_source_id_status", "source_id", "status"),
        UniqueConstraint(
            "record_id", "source_id", "source_url", name="uq_advertisements_occurrence"
        ),
    )

    record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    listing_page_number: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    original_content_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    sanitization_metadata: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=sa.text("'{}'::jsonb"), nullable=False
    )
    custom_fields: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=sa.text("'{}'::jsonb"), nullable=False
    )

    # SHA-256 del contenuto normalizzato (title+description+...), usato dal
    # servizio di dedup per rilevare ri-pubblicazioni identiche senza dover
    # ricalcolare/confrontare il testo intero.
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    media_set_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    # Confidenza (0..1) che questo annuncio appartenga davvero al Record a cui è
    # associato (utile quando l'associazione deriva da euristiche di matching
    # più deboli del solo numero di telefono, es. testo/immagini simili).
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    status: Mapped[str] = mapped_column(AdvertisementStatus, default="active", nullable=False)

    record: Mapped[Record] = relationship(
        "Record", back_populates="advertisements", foreign_keys=[record_id]
    )
    source: Mapped[Source] = relationship("Source")
