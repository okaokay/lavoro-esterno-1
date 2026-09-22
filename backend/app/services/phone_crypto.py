"""Cifratura e hashing del numero di telefono.

Principio guida (privacy-by-design / GDPR data minimization):
il numero di telefono è un dato personale e NON deve mai essere usato in
chiaro come chiave primaria o come criterio di ricerca in un database che
potrebbe essere letto da chi non dovrebbe vedere il dato in chiaro (backup,
log, query di debug, ecc.).

Adottiamo quindi due rappresentazioni distinte, entrambe derivate dal numero
normalizzato:

1. `phone_encrypted` (AES-256-GCM): ciphertext reversibile, decifrabile SOLO
   con la chiave segreta `PHONE_ENCRYPTION_KEY`. Serve per poter mostrare il
   numero in chiaro in contesti autorizzati (es. export "complete_media" per
   un operatore con i permessi giusti).
2. `phone_lookup_hash` (HMAC-SHA256): hash deterministico ma NON invertibile,
   calcolato con una chiave segreta separata `PHONE_HMAC_SECRET`. Due numeri
   normalizzati identici producono sempre lo stesso hash, quindi può essere
   usato come chiave di lookup/deduplicazione ("questo numero esiste già?")
   senza mai dover decifrare né esporre il dato in chiaro. Non essendo un hash
   "nudo" (es. semplice SHA-256) ma un HMAC con chiave segreta, non è
   attaccabile per forza bruta/rainbow-table da chi non conosce la chiave.

Le due chiavi sono volutamente distinte: compromettere l'una non compromette
l'altra proprietà (riservatezza vs. capacità di dedup).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re

import phonenumbers
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from phonenumbers.phonenumberutil import NumberParseException

from app.config import settings

# Lunghezza del nonce raccomandata per AES-GCM (96 bit).
_GCM_NONCE_LENGTH = 12


class PhoneCryptoError(ValueError):
    """Errore di normalizzazione, cifratura o decifratura del numero di telefono."""


def normalize_phone(raw: str, default_region: str | None = "IT") -> str:
    """Validate and normalize a phone number to E.164.

    An explicit international prefix (``+`` or ``00``) always wins and the
    source country does not alter it. A national number instead requires a
    region: ingestion passes ``Source.country_code`` while the ``IT`` default
    preserves compatibility for older non-source callers.
    """
    if not raw or not raw.strip():
        raise PhoneCryptoError("Numero di telefono vuoto.")

    value = raw.strip()
    if value.lower().startswith("tel:"):
        value = value[4:]

    cleaned = re.sub(r"[\s\-().\u200b\u200c\u200d\ufeff]", "", value)

    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    explicit_international = cleaned.startswith("+")
    region = None
    if not explicit_international:
        if default_region is None:
            raise PhoneCryptoError(
                "Numero privo di prefisso internazionale e Paese della fonte non configurato."
            )
        region = default_region.upper()
        if region not in phonenumbers.SUPPORTED_REGIONS:
            raise PhoneCryptoError("Paese della fonte non valido per la numerazione telefonica.")

    try:
        parsed = phonenumbers.parse(cleaned, region)
    except NumberParseException as exc:
        raise PhoneCryptoError("Formato numero di telefono non valido.") from exc

    # is_possible_number verifies country calling code and length/shape without
    # rejecting valid-but-not-yet-assigned ranges as is_valid_number would.
    if not phonenumbers.is_possible_number(parsed):
        raise PhoneCryptoError("Lunghezza o formato del numero non validi per il Paese indicato.")

    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def _encryption_key() -> bytes:
    key = base64.b64decode(settings.PHONE_ENCRYPTION_KEY)
    if len(key) != 32:
        raise PhoneCryptoError("PHONE_ENCRYPTION_KEY deve decodificare a 32 byte (AES-256).")
    return key


def encrypt_bytes(plaintext: bytes) -> bytes:
    """Cifra byte arbitrari con AES-256-GCM usando `PHONE_ENCRYPTION_KEY`.

    Primitiva generica riusata sia per il numero di telefono (`encrypt_phone`)
    sia per altri segreti da cifrare a riposo con lo stesso schema (es. il
    secret TOTP in `users.totp_secret_encrypted`, vedi app/security/totp.py).
    Il risultato è `nonce || ciphertext_con_tag`, concatenati: è il layout
    minimo sufficiente per decifrare senza dover salvare il nonce altrove.
    """
    aesgcm = AESGCM(_encryption_key())
    nonce = os.urandom(_GCM_NONCE_LENGTH)
    ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data=None)
    return nonce + ciphertext


def decrypt_bytes(encrypted: bytes) -> bytes:
    """Decifra un blob prodotto da `encrypt_bytes`."""
    if len(encrypted) < _GCM_NONCE_LENGTH:
        raise PhoneCryptoError("Blob cifrato troppo corto per contenere un nonce valido.")
    nonce, ciphertext = encrypted[:_GCM_NONCE_LENGTH], encrypted[_GCM_NONCE_LENGTH:]
    aesgcm = AESGCM(_encryption_key())
    return aesgcm.decrypt(nonce, ciphertext, associated_data=None)


def encrypt_phone(plain: str) -> bytes:
    """Cifra un numero di telefono già normalizzato con AES-256-GCM."""
    normalized = normalize_phone(plain)
    return encrypt_bytes(normalized.encode("utf-8"))


def decrypt_phone(encrypted: bytes) -> str:
    """Decifra un blob prodotto da `encrypt_phone`. Da usare solo in contesti
    autorizzati (es. export "complete" richiesto da un operatore con i
    permessi adeguati): la sua stessa esistenza come funzione va auditata
    (vedi app/models/audit_log.py)."""
    return decrypt_bytes(encrypted).decode("utf-8")


def mask_phone(phone: str) -> str:
    """Mask a normalized phone while preserving only a routing hint."""
    if len(phone) <= 5:
        return "*" * len(phone)
    return f"{phone[:3]}{'*' * (len(phone) - 5)}{phone[-2:]}"


def phone_lookup_hash(raw_or_normalized: str) -> str:
    """Calcola l'hash di lookup deterministico (HMAC-SHA256, esadecimale)
    per un numero di telefono, dopo averlo normalizzato.

    Usare SEMPRE questa funzione (mai un hash "a mano") per garantire che lo
    stesso numero produca sempre lo stesso hash indipendentemente da come è
    stato digitato.
    """
    normalized = normalize_phone(raw_or_normalized)
    secret = settings.PHONE_HMAC_SECRET.encode("utf-8")
    digest = hmac.new(secret, normalized.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()
