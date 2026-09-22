"""Interfaccia comune per i connettori di scraping.

Ogni fonte (sito di annunci) implementa questa classe. Lo `slug` DEVE
corrispondere alla colonna `sources.slug` nel database e alla chiave usata in
`registry.py`, così che il worker Celery possa risolvere "source_id -> classe
scraper" passando per lo slug.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MediaDownloadFailure:
    """Errore sicuro relativo a un singolo URL media.

    Non conserva deliberatamente l'URL: i link media possono contenere token
    o altri identificatori e non devono finire nei log o nello storico run.
    """

    message: str


@dataclass
class MediaDownloadResult:
    """Esito best-effort del download dei media di un annuncio."""

    attempted_count: int = 0
    media_bytes: list[bytes] = field(default_factory=list)
    failures: list[MediaDownloadFailure] = field(default_factory=list)

    @property
    def failed_count(self) -> int:
        return len(self.failures)

    def __iter__(self) -> Iterator[bytes]:
        """Compatibilità con i consumer storici che iteravano la lista di byte."""
        return iter(self.media_bytes)

    def __len__(self) -> int:
        return len(self.media_bytes)


class Scraper(ABC):
    """Contratto che ogni connettore di scraping deve rispettare.

    Nessun metodo qui esegue realmente richieste HTTP: sono tutti stub che
    definiscono la forma dell'interfaccia, da implementare nel rispetto dei
    Termini di Servizio della fonte e dei rate limit dichiarati.
    """

    slug: str
    base_url: str
    rate_limit_seconds: float = 2.0
    """Intervallo minimo, in secondi, tra due richieste consecutive verso la
    stessa fonte. Valore di default prudenziale; ogni connettore concreto può
    sovrascriverlo in base alle policy della fonte specifica."""

    user_agent: str = "LavoroEsternoBot/1.0 (+https://lavoro.internal/bot)"
    """User-Agent predefinito inviato dalle richieste reali quando una fonte
    non ne configura uno esplicitamente in `Source.scrape_config`."""

    @abstractmethod
    async def discover(self) -> list[str]:
        """Individua gli URL dei singoli annunci da visitare (es. tramite le
        pagine di elenco/categoria della fonte). Restituisce una lista di URL
        assoluti."""
        raise NotImplementedError

    @abstractmethod
    async def scrape_ad(self, url: str) -> dict[str, Any]:
        """Scarica ed estrae i dati grezzi di un singolo annuncio dato il suo URL."""
        raise NotImplementedError

    @abstractmethod
    async def download_media(self, ad: dict[str, Any]) -> MediaDownloadResult:
        """Scarica i file media (immagini/video) referenziati da un annuncio già estratto."""
        raise NotImplementedError

    @abstractmethod
    def normalize(self, data: dict[str, Any]) -> dict[str, Any]:
        """Normalizza i dati grezzi estratti nel formato comune atteso dal
        resto della pipeline (campi coerenti con `app.models.advertisement.Advertisement`:
        title, description, source_url, phone, ecc.)."""
        raise NotImplementedError

    async def aclose(self) -> None:
        """Rilascia eventuali risorse di rete tenute aperte per la durata di
        un run (client HTTP, browser headless, ...). No-op di default: solo
        i connettori che tengono risorse persistenti (vedi
        `app/scrapers/generic.py:GenericScraper`) hanno bisogno di
        sovrascriverlo."""
        return None
