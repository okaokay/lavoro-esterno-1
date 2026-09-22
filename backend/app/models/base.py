"""Base dichiarativa comune e mixin condivisi per tutti i modelli ORM.

Tenere un unico `Base`/registry qui e importare tutti i modelli concreti in
`app/models/__init__.py` è ciò che permette ad Alembic (target_metadata) di
vedere l'intero schema in un colpo solo per l'autogenerate.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    """Timestamp UTC "naive-safe" usato come default lato Python per created_at/updated_at.

    Usiamo una funzione (non `datetime.utcnow` direttamente) così SQLAlchemy la
    richiama ad ogni insert/update invece di congelare un unico valore al
    momento dell'import del modulo.
    """
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Base dichiarativa condivisa da tutti i modelli dell'applicazione."""

    pass


class UUIDPKMixin:
    """Mixin: chiave primaria UUID generata lato applicazione (uuid4)."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    """Mixin: colonne created_at/updated_at gestite automaticamente."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
