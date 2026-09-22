"""Test per app.security.password.validate_password_strength: la policy di
complessità minima (nessuna scadenza, per decisione di prodotto, vedi
PROGETTO.md). Nessuna dipendenza da DB, coerente con lo stile degli altri
test in questa cartella."""

from __future__ import annotations

import pytest

from app.security.password import WeakPasswordError, validate_password_strength


def test_valid_password_passes() -> None:
    validate_password_strength("Tr0ub4dor&3xyz", email="mario.rossi@example.com")


def test_too_short_password_rejected() -> None:
    with pytest.raises(WeakPasswordError):
        validate_password_strength("Sh0rt&1", email="a@example.com")


def test_low_character_variety_rejected() -> None:
    # Solo minuscole: una sola classe di caratteri, sotto la soglia minima di 3.
    with pytest.raises(WeakPasswordError):
        validate_password_strength("onlylowercaseletters", email="a@example.com")


def test_common_password_rejected() -> None:
    with pytest.raises(WeakPasswordError):
        validate_password_strength("password1", email="a@example.com")


def test_password_containing_email_local_part_rejected() -> None:
    with pytest.raises(WeakPasswordError):
        validate_password_strength("MarioRossi2024!", email="mariorossi@example.com")


def test_password_at_exact_minimum_length_with_variety_passes() -> None:
    # 12 caratteri esatti (default PASSWORD_MIN_LENGTH), 3 classi su 4.
    validate_password_strength("Abcdefgh123!", email="user@example.com")


def test_very_short_email_local_part_is_not_checked_for_containment() -> None:
    # Local part di 1-2 caratteri darebbe falsi positivi su quasi ogni
    # password: il controllo si applica solo da 3 caratteri in su.
    validate_password_strength("Abcdefgh123!", email="a@example.com")
