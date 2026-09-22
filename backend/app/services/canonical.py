"""Selezione dell'annuncio "canonico" per un Record.

Regola deterministica (in quest'ordine): pagina di listing più bassa,
priorità della fonte (`high > medium > low`), completezza, recenza e ID
dell'annuncio. Sono eleggibili soltanto annunci attivi e nessuno slug riceve
un trattamento speciale.

Il modulo è volutamente privo di dipendenze da SQLAlchemy/DB: la funzione di
risoluzione opera su semplici dataclass, così è testabile in isolamento e
riusabile sia da un task Celery post-scraping sia da un endpoint di override
manuale.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum


class SourcePriority(IntEnum):
    """Priorità numerica crescente usata come primo criterio di scelta."""

    low = 0
    medium = 1
    high = 2


# Kept as an import-compatible identifier for integrations; it no longer has
# special precedence in the canonical selection policy.
BAKECA_INCONTRI_SLUG = "bakeca_incontri"


@dataclass(frozen=True)
class CandidateSource:
    """Rappresentazione minima di una fonte, sufficiente per la regola."""

    id: uuid.UUID
    slug: str
    priority: SourcePriority


@dataclass(frozen=True)
class CandidateAdvertisement:
    """Rappresentazione minima di un annuncio, sufficiente per la regola.

    `status` atteso: "active" | "removed" | "invalid" (solo "active" è
    eleggibile a canonico).
    """

    id: uuid.UUID
    source: CandidateSource
    scraped_at: datetime
    status: str
    title: str | None = None
    description: str | None = None
    source_url: str | None = None
    extra_non_empty_fields: int = 0
    listing_page_number: int | None = None
    """Conteggio aggiuntivo di campi "informativi" non vuoti oltre a
    title/description/source_url (es. prezzo, città, età dichiarata...),
    fornito dal chiamante per non dover conoscere qui l'intero schema
    Advertisement."""


@dataclass(frozen=True)
class CanonicalResolution:
    """Esito della risoluzione: l'annuncio scelto e la motivazione testuale
    pronta per essere salvata in `canonical_history.reason`."""

    chosen: CandidateAdvertisement
    reason: str


def _non_empty_field_count(ad: CandidateAdvertisement) -> int:
    core_fields = (ad.title, ad.description, ad.source_url)
    return sum(1 for f in core_fields if f and f.strip()) + ad.extra_non_empty_fields


def _tie_break_key(ad: CandidateAdvertisement) -> tuple:
    """Chiave decrescente usata con ``max()`` per la scelta canonica."""
    return (
        -(ad.listing_page_number if ad.listing_page_number is not None else 2**31 - 1),
        int(ad.source.priority),
        _non_empty_field_count(ad),
        ad.scraped_at,
        str(ad.id),
    )


def resolve_canonical(
    advertisements: list[CandidateAdvertisement],
) -> CanonicalResolution:
    """Applica la regola di selezione del canonico a una lista di candidati
    (tutti relativi allo stesso Record) e restituisce l'esito.

    Solleva ValueError se non c'è nessun annuncio "active" tra i candidati:
    la chiamata a questa funzione presuppone che almeno un annuncio valido
    esista (il chiamante è responsabile di gestire il caso "nessun canonico
    possibile", es. record appena creato senza ancora annunci attivi).
    """
    active_ads = [ad for ad in advertisements if ad.status == "active"]
    if not active_ads:
        raise ValueError(
            "Nessun annuncio con status 'active' tra i candidati: impossibile scegliere "
            "un canonico."
        )

    chosen = max(active_ads, key=_tie_break_key)
    reason = (
        "Selezionato applicando pagina listing, priorità fonte, completezza, recenza e ID "
        f"deterministico (fonte='{chosen.source.slug}', priorità={chosen.source.priority.name}, "
        f"pagina={chosen.listing_page_number}, scraped_at={chosen.scraped_at.isoformat()})."
    )
    return CanonicalResolution(chosen=chosen, reason=reason)


def build_history_entry(
    record_id: uuid.UUID,
    previous_advertisement_id: uuid.UUID | None,
    resolution: CanonicalResolution,
    overridden_by_user_id: uuid.UUID | None = None,
) -> dict:
    """Costruisce il dict pronto per popolare una riga `canonical_history`,
    a partire dall'esito di `resolve_canonical` (o da un override manuale,
    nel qual caso `overridden_by_user_id` va valorizzato dal chiamante e la
    `reason` tipicamente sovrascritta con la motivazione fornita dall'operatore).
    """
    return {
        "record_id": record_id,
        "previous_advertisement_id": previous_advertisement_id,
        "new_advertisement_id": resolution.chosen.id,
        "reason": resolution.reason,
        "overridden_by_user_id": overridden_by_user_id,
    }
