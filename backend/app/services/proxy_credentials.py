"""AES-256-GCM encryption for proxy usernames and passwords."""

from __future__ import annotations

import base64
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

_NONCE_BYTES = 12
_AAD = b"lavoro-esterno:proxy-credential:v1"


def _key() -> bytes:
    if not settings.PROXY_CREDENTIAL_ENCRYPTION_KEY:
        raise RuntimeError("PROXY_CREDENTIAL_ENCRYPTION_KEY non configurata.")
    try:
        value = base64.b64decode(settings.PROXY_CREDENTIAL_ENCRYPTION_KEY, validate=True)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("PROXY_CREDENTIAL_ENCRYPTION_KEY non e base64 valida.") from exc
    if len(value) != 32:
        raise RuntimeError("PROXY_CREDENTIAL_ENCRYPTION_KEY deve contenere 32 byte.")
    return value


def encrypt_proxy_credentials(username: str, password: str) -> bytes:
    nonce = os.urandom(_NONCE_BYTES)
    payload = json.dumps(
        {"username": username, "password": password}, separators=(",", ":")
    ).encode()
    return nonce + AESGCM(_key()).encrypt(nonce, payload, _AAD)


def decrypt_proxy_credentials(ciphertext: bytes | None) -> tuple[str, str] | None:
    if ciphertext is None:
        return None
    if len(ciphertext) <= _NONCE_BYTES:
        raise RuntimeError("Credenziale proxy cifrata non valida.")
    payload = AESGCM(_key()).decrypt(ciphertext[:_NONCE_BYTES], ciphertext[_NONCE_BYTES:], _AAD)
    data = json.loads(payload)
    return str(data["username"]), str(data["password"])
