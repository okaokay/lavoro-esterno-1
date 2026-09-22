"""Funzioni pure di supporto alla deduplicazione degli annunci.

Tenute deliberatamente prive di dipendenze da DB/ORM: sono usate sia dal
flusso di scraping (per decidere se un annuncio è "nuovo" o un duplicato di
uno già visto) sia dai test unitari, senza bisogno di un database reale.
"""

from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.services.phone_crypto import normalize_phone

# Parametri di query comunemente usati per il tracciamento pubblicitario/
# analytics, da rimuovere per confrontare URL "sostanzialmente uguali" anche
# quando differiscono solo per la campagna/sorgente di provenienza del click.
_TRACKING_QUERY_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "msclkid",
    "ref",
    "referrer",
}


def normalize_phone_for_dedup(raw: str) -> str:
    """Alias esplicito su `normalize_phone`, usato dal flusso di dedup per
    rendere evidente l'intento (evitare di confrontare rappresentazioni
    testuali diverse dello stesso numero)."""
    return normalize_phone(raw)


def normalize_url(raw_url: str) -> str:
    """Normalizza un URL per il confronto di duplicati:
    - host in minuscolo (gli host sono case-insensitive, il path in generale no)
    - rimozione di parametri di tracking noti
    - query string riordinata alfabeticamente (stesso URL con parametri in
      ordine diverso deve normalizzare allo stesso risultato)
    - rimozione dello slash finale ridondante nel path
    - rimozione del fragment (#...), irrilevante lato server
    """
    parsed = urlparse(raw_url.strip())

    host = parsed.netloc.lower()

    path = parsed.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_QUERY_PARAMS
    ]
    query = urlencode(sorted(query_pairs))

    normalized = urlunparse((parsed.scheme.lower(), host, path, "", query, ""))
    return normalized


def content_sha256(text: str) -> str:
    """SHA-256 esadecimale del contenuto testuale normalizzato di un annuncio
    (tipicamente titolo+descrizione concatenati dal chiamante). Usato per
    individuare ri-pubblicazioni testualmente identiche senza confrontare
    stringhe intere ad ogni scan."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compare_core_fields(a: dict, b: dict) -> bool:
    """Confronta i campi "core" di due annunci (title, description normalizzati
    e content hash) per stabilire se sono lo stesso annuncio.

    `a` e `b` sono dict con chiavi opzionali "title", "description",
    "content_hash", "source_url". Il confronto è deliberatamente semplice e
    esatto (case/whitespace-insensitive su title/description); il confronto
    "fuzzy" più sofisticato è delegato a `text_similarity`.
    """

    def _norm_text(value: str | None) -> str:
        return " ".join((value or "").split()).lower()

    if a.get("content_hash") and b.get("content_hash"):
        if a["content_hash"] == b["content_hash"]:
            return True

    same_title = _norm_text(a.get("title")) == _norm_text(b.get("title"))
    same_description = _norm_text(a.get("description")) == _norm_text(b.get("description"))
    same_url = (
        bool(a.get("source_url"))
        and bool(b.get("source_url"))
        and normalize_url(a["source_url"]) == normalize_url(b["source_url"])
    )

    return same_url or (same_title and same_description and bool(a.get("title")))


def text_similarity(text_a: str, text_b: str) -> float | None:
    """Hook per una futura misura di similarità testuale "fuzzy" (es. TF-IDF
    cosine, o embedding + cosine similarity) tra due testi di annunci, per
    catturare ri-pubblicazioni riformulate che `compare_core_fields` non
    individua come identiche.

    TODO(dedup): implementare con un modello di embedding reale (es. sentence
    embeddings) o quantomeno con una metrica lessicale robusta (es. Jaccard su
    n-grammi). Per ora restituisce None per segnalare esplicitamente "non
    ancora implementato", cosicché il chiamante possa distinguere "non simile"
    (0.0) da "non calcolabile" (None) e non prendere decisioni basandosi su un
    valore fittizio.
    """
    return None


def image_phash_similarity(phash_a: str | None, phash_b: str | None) -> float | None:
    """Hook per il confronto di similarità tra due perceptual hash (pHash) di
    immagini, tipicamente tramite distanza di Hamming normalizzata in [0, 1].

    Il calcolo del pHash stesso è responsabilità di
    `app/services/media_classifier.py` / della pipeline media (via libreria
    `imagehash`); questa funzione si limita al confronto tra due hash già
    calcolati.

    TODO(dedup): implementare con `imagehash.hex_to_hash(...)` e distanza di
    Hamming, es.:
        a = imagehash.hex_to_hash(phash_a)
        b = imagehash.hex_to_hash(phash_b)
        return 1 - (a - b) / len(a.hash) ** 2
    Per ora restituisce None (nessun confronto disponibile) se uno dei due
    hash manca, cosicché il chiamante sappia distinguere "non calcolabile"
    da "calcolato e trovato dissimile".
    """
    if not phash_a or not phash_b:
        return None
    return None
