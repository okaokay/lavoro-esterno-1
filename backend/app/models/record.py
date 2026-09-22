"""Modello `Record`: l'entità "persona/numero di telefono" attorno a cui
ruota la deduplicazione. Un Record raggruppa N Advertisement che si ritiene
appartengano allo stesso numero.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:
    from app.models.advertisement import Advertisement


class Record(UUIDPKMixin, TimestampMixin, Base):
    """Aggregato per numero di telefono.

    Il numero di telefono NON è mai conservato né interrogato in chiaro:
    - `phone_encrypted` contiene il ciphertext AES-256-GCM (a riposo, per poterlo
      eventualmente decifrare in contesti autorizzati, es. export "complete");
    - `phone_lookup_hash` è un HMAC-SHA256 deterministico del numero normalizzato,
      usato come UNICA via di ricerca ("il numero X esiste già?") senza mai
      esporre né dover decifrare il dato. Essendo HMAC con chiave segreta non è
      invertibile: soddisfa il requisito di minimizzazione dei dati personali
      pur mantenendo la deduplicazione esatta per numero.
    Vedi `app/services/phone_crypto.py` per l'implementazione.
    """

    __tablename__ = "records"
    __table_args__ = (Index("ix_records_created_at", "created_at"),)

    phone_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    phone_lookup_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    content_revision: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    # FK verso l'annuncio scelto come "canonico" per questo record (vedi
    # app/services/canonical.py per la regola di selezione). Nullable perché un
    # record può non avere ancora un canonico assegnato (es. appena creato).
    # `use_alter=True` spezza il ciclo di dipendenza DDL con `advertisements`
    # (che a sua volta referenzia `records.id`): senza questo, CREATE TABLE
    # fallirebbe perché nessuna delle due tabelle può essere creata per prima.
    canonical_ad_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("advertisements.id", use_alter=True, name="fk_records_canonical_ad_id"),
        nullable=True,
    )

    advertisements: Mapped[list[Advertisement]] = relationship(
        "Advertisement",
        back_populates="record",
        foreign_keys="Advertisement.record_id",
    )
