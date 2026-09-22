"""Fixture condivise per i test del motore di scraping generico.

Serve le cartelle sintetiche in `tests/scrapers/sites/` via un vero server
HTTP locale (`http.server`, stdlib): i test esercitano il percorso di rete
reale di `GenericScraper` (Scrapling + robots.txt + rate limit) senza mai
uscire da `127.0.0.1` — nessuna richiesta verso siti reali.
"""

from __future__ import annotations

import functools
import threading
from collections.abc import Iterator
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

_SITES_DIR = Path(__file__).parent / "sites"


def _serve_directory(directory: Path) -> tuple[ThreadingHTTPServer, str]:
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    return server, f"http://{host}:{port}"


@pytest.fixture
def open_site_url() -> Iterator[str]:
    """Fonte sintetica senza `robots.txt` (quindi tutto implicitamente
    consentito): 3 annunci su 2 pagine, 2 immagini sul primo, il terzo
    annuncio senza numero di telefono (per testare lo scarto esplicito)."""
    server, base_url = _serve_directory(_SITES_DIR / "open")
    try:
        yield base_url
    finally:
        server.shutdown()


@pytest.fixture
def closed_site_url() -> Iterator[str]:
    """Fonte sintetica con `robots.txt` che vieta tutto (`Disallow: /`):
    verifica che il motore non scarichi MAI l'annuncio elencato."""
    server, base_url = _serve_directory(_SITES_DIR / "closed")
    try:
        yield base_url
    finally:
        server.shutdown()
