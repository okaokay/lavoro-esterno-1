"""AES-GCM envelope for protected integration and original content data."""

from __future__ import annotations

import base64
import json
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

_AAD = b"lavoro-esterno:integration:v1"
_NONCE_BYTES = 12


def _key() -> bytes:
    encoded = settings.INTEGRATION_ENCRYPTION_KEY
    if not encoded:
        raise RuntimeError("INTEGRATION_ENCRYPTION_KEY non configurata.")
    try:
        value = base64.b64decode(encoded, validate=True)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("INTEGRATION_ENCRYPTION_KEY non è base64 valida.") from exc
    if len(value) != 32:
        raise RuntimeError("INTEGRATION_ENCRYPTION_KEY deve contenere 32 byte.")
    return value


def encrypt_json(value: Any) -> bytes:
    nonce = os.urandom(_NONCE_BYTES)
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    return nonce + AESGCM(_key()).encrypt(nonce, payload, _AAD)


def decrypt_json(ciphertext: bytes | None) -> Any:
    if ciphertext is None or len(ciphertext) <= _NONCE_BYTES:
        raise RuntimeError("Payload cifrato non valido.")
    payload = AESGCM(_key()).decrypt(ciphertext[:_NONCE_BYTES], ciphertext[_NONCE_BYTES:], _AAD)
    return json.loads(payload)
