"""Test per app.services.record_search: le decisioni di dominio non banali
usate da GET /api/v1/records/search (paginata).

Come per gli altri test in questo file di gap, verifichiamo solo le
funzioni pure isolate dal router (niente DB): vedi tests/test_dashboard_metrics.py
per la nota sull'assenza di una fixture DB in questo repo.
"""

from __future__ import annotations

from app.services.record_search import (
    VERIFIED_CONFIDENCE_THRESHOLD,
    confidence_to_status,
    looks_like_full_phone,
)


def test_looks_like_full_phone_true_for_complete_italian_number() -> None:
    assert looks_like_full_phone("+39 333 1234567") is True
    assert looks_like_full_phone("3331234567") is True


def test_looks_like_full_phone_false_for_short_fragment() -> None:
    # Un frammento breve non è possibile nel piano telefonico italiano e non
    # ha comunque abbastanza cifre per essere considerato un numero completo:
    # vedi la docstring di looks_like_full_phone per il perché questa
    # distinzione conta (ricerca per hash esatto vs. nessun filtro).
    assert looks_like_full_phone("333") is False
    assert looks_like_full_phone("12") is False


def test_looks_like_full_phone_false_for_garbage() -> None:
    assert looks_like_full_phone("not-a-phone-number") is False
    assert looks_like_full_phone("") is False


def test_confidence_to_status_verified_at_and_above_threshold() -> None:
    assert confidence_to_status(VERIFIED_CONFIDENCE_THRESHOLD) == "verified"
    assert confidence_to_status(0.99) == "verified"


def test_confidence_to_status_unverified_below_threshold() -> None:
    assert confidence_to_status(VERIFIED_CONFIDENCE_THRESHOLD - 0.01) == "unverified"
    assert confidence_to_status(0.1) == "unverified"


def test_confidence_to_status_unverified_when_missing() -> None:
    assert confidence_to_status(None) == "unverified"
