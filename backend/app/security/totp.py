"""Autenticazione a due fattori basata su TOTP (RFC 6238), via pyotp.

Include anche i backup codes monouso: 10 codici generati alla registrazione,
mostrati UNA SOLA VOLTA all'utente e salvati solo come hash Argon2 (mai in
chiaro), da usare come fallback se l'utente perde l'accesso all'app
authenticator.
"""

from __future__ import annotations

import base64
import io
import secrets

import pyotp
import qrcode
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.services.phone_crypto import decrypt_bytes, encrypt_bytes

_backup_code_hasher = PasswordHasher()

BACKUP_CODES_COUNT = 10
BACKUP_CODE_LENGTH = 10  # caratteri alfanumerici, es. "A1B2C3D4E5"


def generate_totp_secret() -> str:
    """Genera un nuovo secret TOTP (base32) in chiaro. Va cifrato con
    `encrypt_totp_secret` prima di essere persistito in `users.totp_secret_encrypted`."""
    return pyotp.random_base32()


def encrypt_totp_secret(secret: str) -> bytes:
    """Cifra il secret TOTP con lo stesso schema AES-256-GCM usato per il
    numero di telefono (vedi app.services.phone_crypto), riusando la stessa
    chiave applicativa PHONE_ENCRYPTION_KEY per non moltiplicare i segreti
    di configurazione da gestire in produzione."""
    return encrypt_bytes(secret.encode("utf-8"))


def decrypt_totp_secret(encrypted: bytes) -> str:
    """Decifra un secret TOTP cifrato con `encrypt_totp_secret`."""
    return decrypt_bytes(encrypted).decode("utf-8")


def build_provisioning_uri(secret: str, account_email: str, issuer: str = "Lavoro Esterno") -> str:
    """URI otpauth:// standard, da incorporare nel QR code per l'app authenticator."""
    return pyotp.TOTP(secret).provisioning_uri(name=account_email, issuer_name=issuer)


def generate_qr_code_base64(provisioning_uri: str) -> str:
    """Genera un QR code PNG per l'URI di provisioning e lo restituisce come
    stringa base64 (pronta per essere incorporata in una risposta JSON come
    `data:image/png;base64,...` lato frontend)."""
    img = qrcode.make(provisioning_uri)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def verify_totp_code(secret: str, code: str) -> bool:
    """Verifica un codice TOTP a 6 cifre contro il secret dell'utente.

    `valid_window=1` tollera un piccolo sfasamento dell'orologio del
    dispositivo dell'utente (accetta anche il codice del passo precedente/
    successivo di 30s), pratica standard per ridurre falsi negativi.
    """
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


def generate_backup_codes() -> list[str]:
    """Genera `BACKUP_CODES_COUNT` codici monouso casuali, da mostrare in
    chiaro UNA SOLA VOLTA all'utente (il chiamante è responsabile di non
    loggarli e di non ripresentarli dopo la creazione)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # esclusi caratteri ambigui (0/O, 1/I/L)
    return [
        "".join(secrets.choice(alphabet) for _ in range(BACKUP_CODE_LENGTH))
        for _ in range(BACKUP_CODES_COUNT)
    ]


def hash_backup_codes(codes: list[str]) -> list[str]:
    """Hasha (Argon2) una lista di backup codes, per la persistenza in
    `users.backup_codes_hash`."""
    return [_backup_code_hasher.hash(code) for code in codes]


def verify_and_consume_backup_code(code: str, hashed_codes: list[str]) -> list[str] | None:
    """Verifica un backup code contro la lista di hash salvati.

    Se valido, restituisce la lista aggiornata SENZA l'hash appena consumato
    (garantendo la proprietà "monouso": lo stesso codice non potrà essere
    riusato). Se non valido, restituisce None e la lista salvata non va
    modificata dal chiamante.
    """
    for hashed in hashed_codes:
        try:
            if _backup_code_hasher.verify(hashed, code):
                return [h for h in hashed_codes if h != hashed]
        except VerifyMismatchError:
            continue
        except Exception:
            continue
    return None


def regenerate_backup_codes() -> tuple[list[str], list[str]]:
    """Genera un nuovo set di `BACKUP_CODES_COUNT` backup codes, invalidando
    implicitamente quelli precedenti (il chiamante deve sovrascrivere
    `users.backup_codes_hash` con il secondo elemento della tupla ritornata).

    Usata sia dalla rigenerazione manuale (`POST /auth/2fa/backup-codes/
    regenerate`) sia da quella automatica quando l'utente consuma l'ultimo
    codice rimasto durante il login (`POST /auth/login-2fa`), per non
    duplicare la logica tra i due punti di chiamata.

    Ritorna `(codici_in_chiaro, hash_da_persistere)`: i codici in chiaro
    vanno mostrati all'utente UNA SOLA VOLTA nella risposta, mai loggati né
    ripresentati in seguito.
    """
    codes = generate_backup_codes()
    return codes, hash_backup_codes(codes)
