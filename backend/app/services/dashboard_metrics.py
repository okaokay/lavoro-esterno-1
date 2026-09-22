"""Funzioni pure di supporto al calcolo dei KPI della dashboard.

Isolate dal router (`app/api/v1/dashboard.py`, che esegue le query
SQLAlchemy) per essere testabili senza un database, seguendo lo stesso
principio già adottato in `app/services/canonical.py` e
`app/services/dedup.py`.
"""

from __future__ import annotations


def safe_percentage(part: int, whole: int) -> float:
    """Percentuale `part/whole*100`, arrotondata a 1 decimale.

    Restituisce 0.0 se `whole` è 0 invece di sollevare `ZeroDivisionError`:
    capita ad es. su un'installazione appena avviata, senza ancora fonti o
    record.
    """
    if whole <= 0:
        return 0.0
    return round((part / whole) * 100, 1)


def percentage_delta(current: int, previous: int) -> float:
    """Variazione percentuale di `current` rispetto a `previous`.

    Se `previous` è 0 non esiste un tasso di crescita ben definito
    (divisione per zero): restituiamo 100.0 se `current` > 0 ("crescita da
    zero"), altrimenti 0.0 (nessuna crescita, nessun dato pregresso).
    """
    if previous <= 0:
        return 100.0 if current > 0 else 0.0
    return round(((current - previous) / previous) * 100, 1)
