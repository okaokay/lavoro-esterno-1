"""Modello `Media`: file (immagine/video) collegato a un annuncio."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin, utcnow

MediaClassification = sa.Enum(
    "explicit", "safe", "unclassified", name="media_classification", create_type=True
)
MediaProcessingStatus = sa.Enum(
    "pending", "processing", "ready", "failed", name="media_processing_status", create_type=True
)
MediaReviewStatus = sa.Enum(
    "not_required", "required", "reviewed", name="media_review_status", create_type=True
)


class Media(UUIDPKMixin, Base):
    """File media associato a un `Advertisement`, con relativa classificazione."""

    __tablename__ = "media"

    advertisement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("advertisements.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Chiave oggetto in MinIO/S3 per il file originale così come scaricato.
    original_object_key: Mapped[str] = mapped_column(Text, nullable=False)
    # Chiave oggetto per una eventuale variante derivata (es. thumbnail, versione
    # "safe" con blur, transcodifica video via FFmpeg). Nullable finché non generata.
    derived_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)

    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Perceptual hash (pHash) per il rilevamento di duplicati "quasi identici"
    # (stesso soggetto, ricompressione/resize diversi). Nullable per i video o
    # finché non calcolato in background.
    # Indicizzato: usato per il matching di duplicati "quasi identici" tramite
    # pHash (vedi app/services/dedup.py, TODO di implementazione reale).
    perceptual_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)

    classification: Mapped[str] = mapped_column(
        MediaClassification, default="unclassified", nullable=False
    )
    classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    classifier_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    safety_signals: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    processing_status: Mapped[str] = mapped_column(
        MediaProcessingStatus, default="pending", nullable=False
    )
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str] = mapped_column(
        MediaReviewStatus, default="required", nullable=False
    )
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_current: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=sa.true(), nullable=False, index=True
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
