"""Verifica del `robots.txt` di una fonte.

Usato in due punti, entrambi obbligatori e non aggirabili da configurazione:
1. `app/scrapers/generic.py:GenericScraper` — controllato PRIMA di ogni
   richiesta reale durante uno scraping, non solo come check manuale.
2. `POST /sources/{id}/check-robots` — strumento di verifica manuale in UI,
   utile per validare una configurazione prima di lanciare un run reale.

Scarica solo il file `robots.txt` stesso (pubblico per definizione, non
contiene dati personali) — nessun altro contenuto della fonte viene
richiesto da questo modulo.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import httpx

_ROBOTS_FETCH_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class RobotsCheckResult:
    allowed: bool
    robots_txt_found: bool
    checked_url: str


async def fetch_robots_txt(base_url: str, client: httpx.AsyncClient | None = None) -> str | None:
    """Scarica `robots.txt` per `base_url`. Restituisce `None` se il file non
    esiste (404) o non è raggiungibile — in quel caso, per convenzione dello
    standard robots.txt, tutto è implicitamente consentito."""
    robots_url = urljoin(base_url, "/robots.txt")
    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=_ROBOTS_FETCH_TIMEOUT_SECONDS)
    try:
        response = await client.get(robots_url)
        if response.status_code >= 400:
            return None
        return response.text
    except httpx.HTTPError:
        return None
    finally:
        if owns_client:
            await client.aclose()


def is_allowed(robots_txt: str | None, url: str, user_agent: str) -> bool:
    """Valuta se `url` è consentito per `user_agent` secondo `robots_txt`
    (testo grezzo, o `None` se il file non esiste — in quel caso tutto è
    consentito, come da standard)."""
    if robots_txt is None:
        return True
    parser = RobotFileParser()
    parser.parse(robots_txt.splitlines())
    return parser.can_fetch(user_agent, url)


async def check_robots(
    base_url: str, user_agent: str, path: str = "/", client: httpx.AsyncClient | None = None
) -> RobotsCheckResult:
    """Verifica se `path` (relativo a `base_url`) è consentito. Usata sia
    dall'endpoint manuale `POST /sources/{id}/check-robots` sia, con un
    `client` condiviso per riuso della connessione, da `GenericScraper`."""
    robots_txt = await fetch_robots_txt(base_url, client=client)
    target_url = urljoin(base_url, path)
    return RobotsCheckResult(
        allowed=is_allowed(robots_txt, target_url, user_agent),
        robots_txt_found=robots_txt is not None,
        checked_url=target_url,
    )
