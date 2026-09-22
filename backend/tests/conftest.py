"""Fixture/setup condiviso per i test.

Impostiamo esplicitamente le variabili d'ambiente di cifratura PRIMA che
`app.config` venga importato altrove nella sessione di test, così i test di
`phone_crypto` sono deterministici e non dipendono da un file `.env` presente
o assente nell'ambiente di CI/sviluppo.
"""

from __future__ import annotations

import base64
import os

os.environ.setdefault("PHONE_ENCRYPTION_KEY", base64.b64encode(b"0" * 32).decode("ascii"))
os.environ.setdefault("PHONE_HMAC_SECRET", "test-hmac-secret-not-for-production")
os.environ.setdefault("AI_CREDENTIAL_ENCRYPTION_KEY", base64.b64encode(b"1" * 32).decode("ascii"))
os.environ.setdefault(
    "PROXY_CREDENTIAL_ENCRYPTION_KEY", base64.b64encode(b"2" * 32).decode("ascii")
)
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-not-for-production")
os.environ.setdefault("ENVIRONMENT", "test")
