"""Cifratura dedicata delle credenziali AI; nessun segreto viene serializzato."""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

_NONCE_BYTES = 12
_AAD = b"lavoro-esterno:ai-provider-credential:v1"


def _key() -> bytes:
    if not settings.AI_CREDENTIAL_ENCRYPTION_KEY:
        raise RuntimeError("AI_CREDENTIAL_ENCRYPTION_KEY non configurata.")
    try:
        value = base64.b64decode(settings.AI_CREDENTIAL_ENCRYPTION_KEY, validate=True)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("AI_CREDENTIAL_ENCRYPTION_KEY non e base64 valida.") from exc
    if len(value) != 32:
        raise RuntimeError("AI_CREDENTIAL_ENCRYPTION_KEY deve contenere 32 byte.")
    return value


def encrypt_ai_credential(secret: str) -> bytes:
    nonce = os.urandom(_NONCE_BYTES)
    return nonce + AESGCM(_key()).encrypt(nonce, secret.encode(), _AAD)


def decrypt_ai_credential(ciphertext: bytes | None) -> str | None:
    if ciphertext is None:
        return None
    if len(ciphertext) <= _NONCE_BYTES:
        raise RuntimeError("Credenziale AI cifrata non valida.")
    return (
        AESGCM(_key()).decrypt(ciphertext[:_NONCE_BYTES], ciphertext[_NONCE_BYTES:], _AAD).decode()
    )
