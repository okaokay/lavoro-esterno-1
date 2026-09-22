"""Hashing e verifica delle password con Argon2 (via argon2-cffi).

Argon2id (default di `PasswordHasher`) è la scelta raccomandata da OWASP per
il password hashing: resistente sia ad attacchi GPU (memory-hard) sia a
side-channel (variante "id" combina le proprietà di Argon2i e Argon2d).
"""

from __future__ import annotations

import re

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.config import settings

_hasher = PasswordHasher()

# Le prime ~20 password più comuni (fonti pubbliche tipo "NCSC/Have I Been
# Pwned top passwords"): un controllo di buon senso a costo zero, non un
# sostituto di una vera verifica contro un dataset di password compromesse.
_COMMON_PASSWORDS = {
    "123456",
    "123456789",
    "qwerty",
    "password",
    "12345",
    "12345678",
    "111111",
    "1234567",
    "sunshine",
    "iloveyou",
    "1234567890",
    "123123",
    "000000",
    "abc123",
    "password1",
    "qwerty123",
    "letmein",
    "monkey",
    "dragon",
    "football",
}


class WeakPasswordError(ValueError):
    """Password che non soddisfa la policy minima di complessità."""


def hash_password(plain: str) -> str:
    """Restituisce l'hash Argon2 (stringa auto-descrittiva, include salt e
    parametri) da salvare in `users.password_hash`."""
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verifica una password in chiaro contro il suo hash. Non solleva mai
    eccezioni verso il chiamante: restituisce semplicemente True/False."""
    try:
        return _hasher.verify(hashed, plain)
    except VerifyMismatchError:
        return False
    except Exception:
        # Hash malformato/incompatibile: trattato come mismatch, non come
        # errore di sistema, per non far trapelare dettagli utili a un
        # attaccante tramite differenze di comportamento.
        return False


def validate_password_strength(password: str, *, email: str | None = None) -> None:
    """Applica la policy minima di complessità password (nessuna scadenza:
    decisione esplicita di prodotto, vedi PROGETTO.md). Solleva
    `WeakPasswordError` con un messaggio adatto a essere mostrato
    all'utente se la password non è accettabile.

    Requisiti: lunghezza minima (`PASSWORD_MIN_LENGTH`), almeno 3 delle 4
    classi di caratteri (minuscole/maiuscole/cifre/simboli), non deve
    contenere la parte locale dell'email (evita password ovvie tipo
    "mario.rossi2024"), non deve essere tra le password più comuni note.
    """
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        raise WeakPasswordError(
            f"La password deve contenere almeno {settings.PASSWORD_MIN_LENGTH} caratteri."
        )

    character_classes = [
        bool(re.search(r"[a-z]", password)),
        bool(re.search(r"[A-Z]", password)),
        bool(re.search(r"\d", password)),
        bool(re.search(r"[^a-zA-Z0-9]", password)),
    ]
    if sum(character_classes) < 3:
        raise WeakPasswordError(
            "La password deve contenere almeno 3 tra: lettere minuscole, "
            "lettere maiuscole, cifre, simboli."
        )

    if password.lower() in _COMMON_PASSWORDS:
        raise WeakPasswordError("Questa password è troppo comune, scegline un'altra.")

    if email:
        # Local part troppo corta (es. "a@...") darebbe falsi positivi quasi
        # su ogni password: il controllo ha senso solo da 3 caratteri in su.
        local_part = email.split("@", 1)[0].lower()
        if len(local_part) >= 3 and local_part in password.lower():
            raise WeakPasswordError("La password non può contenere il tuo indirizzo email.")
