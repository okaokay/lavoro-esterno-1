"""Modello `MediaClassificationHistory`: audit trail delle riclassificazioni
di un `Media` (automatiche dal classificatore o manuali da un operatore)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin, utcnow
from app.models.media import MediaClassification


class MediaClassificationHistory(UUIDPKMixin, Base):
    __tablename__ = "media_classification_history"

    media_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("media.id", ondelete="CASCADE"), nullable=False, index=True
    )
    previous_classification: Mapped[str | None] = mapped_column(MediaClassification, nullable=True)
    new_classification: Mapped[str] = mapped_column(MediaClassification, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
