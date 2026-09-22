"""Aggregazione pura dello stato delle fonti (`Source.status`) nelle due
forme richieste dal frontend:

- `summarize_sources_by_status`: conteggio per stato con il vocabolario
  nativo del dominio (`total`/`active`/`degraded`/`offline`), usato da
  `GET /sources/summary` (vedi `frontend/src/api/sources.ts:SourcesSummary`).
- `health_breakdown`: la stessa aggregazione rimappata sul vocabolario
  `healthy`/`rateLimited`/`error` atteso da `GET /dashboard/source-health`
  (vedi `frontend/src/types/index.ts:SourceHealthBreakdown`).

I tre stati nativi di `Source` ("healthy", "degraded", "offline") non
combaciano 1:1 col vocabolario di dashboard ("healthy", "rateLimited",
"error"): la mappatura qui sotto è una scelta pragmatica, documentata perché
non ovvia — "degraded" è tipicamente causato da rate limiting/blocchi
temporanei della fonte, quindi lo trattiamo come "rateLimited"; "offline" è
un guasto conclamato, quindi "error". Se in futuro il dominio distinguerà
esplicitamente le cause (rate limit vs. altri tipi di errore), questa
funzione andrà aggiornata di conseguenza.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable


def summarize_sources_by_status(statuses: Iterable[str]) -> dict[str, int]:
    counts = Counter(statuses)
    return {
        "total": sum(counts.values()),
        "active": counts.get("healthy", 0),
        "degraded": counts.get("degraded", 0),
        "offline": counts.get("offline", 0),
    }


def health_breakdown(statuses: Iterable[str]) -> dict[str, int]:
    counts = Counter(statuses)
    return {
        "healthy": counts.get("healthy", 0),
        "rate_limited": counts.get("degraded", 0),
        "error": counts.get("offline", 0),
        "total": sum(counts.values()),
    }
