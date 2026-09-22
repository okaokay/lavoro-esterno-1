"""Test per app.security.totp: generazione/verifica/rigenerazione dei backup
codes 2FA. Nessuna dipendenza da DB."""

from __future__ import annotations

from app.security.totp import (
    BACKUP_CODES_COUNT,
    generate_backup_codes,
    hash_backup_codes,
    regenerate_backup_codes,
    verify_and_consume_backup_code,
)


def test_generate_backup_codes_produces_expected_count_and_uniqueness() -> None:
    codes = generate_backup_codes()
    assert len(codes) == BACKUP_CODES_COUNT
    assert len(set(codes)) == BACKUP_CODES_COUNT


def test_verify_and_consume_backup_code_removes_only_matched_hash() -> None:
    codes = generate_backup_codes()
    hashed = hash_backup_codes(codes)

    remaining = verify_and_consume_backup_code(codes[0], hashed)

    assert remaining is not None
    assert len(remaining) == BACKUP_CODES_COUNT - 1
    # Il codice consumato non deve più essere verificabile (monouso).
    assert verify_and_consume_backup_code(codes[0], remaining) is None


def test_verify_and_consume_backup_code_rejects_unknown_code() -> None:
    codes = generate_backup_codes()
    hashed = hash_backup_codes(codes)
    assert verify_and_consume_backup_code("NOTAREALCODE", hashed) is None


def test_regenerate_backup_codes_produces_a_fresh_disjoint_set() -> None:
    old_codes = generate_backup_codes()
    new_codes, new_hashed = regenerate_backup_codes()

    assert len(new_codes) == BACKUP_CODES_COUNT
    assert len(new_hashed) == BACKUP_CODES_COUNT
    # Nuovo set indipendente da qualunque set precedente (nessuna sovrapposizione
    # in pratica, dato lo spazio di codici a caso su 10 caratteri).
    assert set(new_codes).isdisjoint(old_codes)
    # I nuovi codici in chiaro devono essere verificabili contro i loro hash.
    remaining = verify_and_consume_backup_code(new_codes[0], new_hashed)
    assert remaining is not None
