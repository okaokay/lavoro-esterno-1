"""Modello `CanonicalHistory`: traccia ogni cambio dell'annuncio canonico
di un Record (sia automatico, applicando la regola di app/services/canonical.py,
sia manuale via override di un operatore)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin, utcnow


class CanonicalHistory(UUIDPKMixin, Base):
    __tablename__ = "canonical_history"

    record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    previous_advertisement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("advertisements.id", ondelete="SET NULL"), nullable=True
    )
    new_advertisement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("advertisements.id", ondelete="CASCADE"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    # Se valorizzato, il cambio è stato un override manuale di un operatore
    # (non l'esito automatico della regola deterministica).
    overridden_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
