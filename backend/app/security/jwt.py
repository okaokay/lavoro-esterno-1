"""Creazione e validazione di access/refresh JWT (PyJWT, HS256).

Due token distinti per due scopi distinti:
- access token: vita breve (default 15 minuti), inviato ad ogni richiesta API,
  contiene il minimo indispensabile (subject = user id, ruolo).
- refresh token: vita lunga (default 14 giorni), usato SOLO per ottenere un
  nuovo access token, non per autenticare direttamente le richieste API.
Separarli limita la finestra di validità di un token trafugato dal traffico
"quotidiano" (access) rispetto a quello, più raro, di refresh.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import jwt

from app.config import settings

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _to_unix(value: datetime) -> int:
    return int((value - _EPOCH).total_seconds())


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"
    LOGIN_2FA = "login_2fa"
    """Token effimero emesso dopo la sola verifica password quando l'utente ha
    la 2FA attiva: prova che la password è corretta, ma non basta da solo ad
    autenticare le richieste API (serve completare con un codice TOTP/backup
    su POST /auth/login-2fa)."""


class TokenError(ValueError):
    """Token JWT mancante, scaduto, malformato o di tipo inatteso."""


def _create_token(
    subject: uuid.UUID,
    role: str,
    token_type: TokenType,
    ttl: timedelta,
    *,
    security_stamp_at: datetime | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "type": token_type.value,
        "iat": now,
        "exp": now + ttl,
        # jti: identificatore univoco del singolo token, usato per la
        # blacklist mirata su logout (app/security/redis_client.py).
        "jti": str(uuid.uuid4()),
    }
    if security_stamp_at is not None:
        # sst ("security stamp"): snapshot di User.security_stamp_at al
        # momento dell'emissione. Confrontato contro il valore corrente in
        # app/security/deps.py: se non combaciano, il token è considerato
        # revocato in blocco (logout globale, cambio password, reset 2FA).
        payload["sst"] = _to_unix(security_stamp_at)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: uuid.UUID, role: str, security_stamp_at: datetime) -> str:
    return _create_token(
        user_id,
        role,
        TokenType.ACCESS,
        timedelta(minutes=settings.JWT_ACCESS_TTL_MINUTES),
        security_stamp_at=security_stamp_at,
    )


def create_refresh_token(user_id: uuid.UUID, role: str, security_stamp_at: datetime) -> str:
    return _create_token(
        user_id,
        role,
        TokenType.REFRESH,
        timedelta(days=settings.JWT_REFRESH_TTL_DAYS),
        security_stamp_at=security_stamp_at,
    )


def create_login_ticket(user_id: uuid.UUID, role: str) -> str:
    """Token effimero (5 minuti) emesso dopo la sola verifica password,
    quando serve completare il login con la 2FA (vedi TokenType.LOGIN_2FA).

    Non porta il claim `sst`: è troppo breve per avere senso rispetto alla
    revoca in blocco, e non autentica direttamente nessuna richiesta API."""
    return _create_token(user_id, role, TokenType.LOGIN_2FA, timedelta(minutes=5))


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    """Decodifica e valida un JWT, verificando anche che sia del tipo atteso
    (impedisce, ad esempio, di usare un refresh token al posto di un access
    token su un endpoint protetto)."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise TokenError(f"Token non valido o scaduto: {exc}") from exc

    if payload.get("type") != expected_type.value:
        raise TokenError(f"Tipo di token inatteso: attesto '{expected_type.value}'.")

    return payload


def remaining_ttl_seconds(payload: dict[str, Any]) -> int:
    """Secondi residui prima della scadenza naturale (claim `exp`) di un
    token già decodificato: usato per impostare il TTL della voce di
    blacklist, che non ha senso far durare più a lungo del token stesso."""
    exp = payload.get("exp")
    if exp is None:
        return 0
    return max(0, int(exp) - _to_unix(datetime.now(UTC)))
