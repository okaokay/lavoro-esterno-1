"""Schemi Pydantic per la ricerca (per hash telefono)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class PhoneSearchRequest(BaseModel):
    """Corpo della richiesta di ricerca per numero di telefono.

    Riceviamo il numero in chiaro dal client (necessario: l'utente lo digita
    così), ma lo trasformiamo IMMEDIATAMENTE in hash di lookup lato server e
    non lo salviamo né lo logghiamo in chiaro (vedi app/services/phone_crypto.py).
    """

    phone: str = Field(description="Numero di telefono da cercare, in un formato qualsiasi.")


class PhoneSearchResult(BaseModel):
    record_id: uuid.UUID
    canonical_ad_id: uuid.UUID | None
    advertisement_count: int
