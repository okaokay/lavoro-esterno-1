"""Test per app.services.dashboard_metrics: le funzioni pure usate da
GET /api/v1/dashboard/kpis per calcolare le percentuali/delta.

Non esiste nel repo una fixture di database async configurata per i test
(vedi tests/conftest.py: solo variabili d'ambiente per la cifratura/JWT,
nessun engine/sessione di test) — coerentemente con lo stile degli altri
test in questa cartella (test_canonical.py, test_dedup.py), che verificano
la logica di dominio isolandola dal layer DB invece di introdurre una
dipendenza pesante (un Postgres di test) solo per questo scaffold. Le query
SQLAlchemy vere e proprie nei router (app/api/v1/dashboard.py) non sono
quindi coperte qui: la logica "interessante" (i calcoli) è isolata in
questo modulo apposta per essere testabile senza DB.
"""

from __future__ import annotations

from app.services.dashboard_metrics import percentage_delta, safe_percentage


def test_safe_percentage_normal_case() -> None:
    assert safe_percentage(25, 200) == 12.5


def test_safe_percentage_zero_whole_returns_zero() -> None:
    assert safe_percentage(5, 0) == 0.0
    assert safe_percentage(0, 0) == 0.0


def test_percentage_delta_growth() -> None:
    assert percentage_delta(120, 100) == 20.0


def test_percentage_delta_decline() -> None:
    assert percentage_delta(80, 100) == -20.0


def test_percentage_delta_no_change() -> None:
    assert percentage_delta(50, 50) == 0.0


def test_percentage_delta_previous_zero_with_current_growth() -> None:
    assert percentage_delta(10, 0) == 100.0


def test_percentage_delta_previous_zero_and_current_zero() -> None:
    assert percentage_delta(0, 0) == 0.0
