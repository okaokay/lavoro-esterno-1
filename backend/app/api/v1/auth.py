"""Endpoint di autenticazione: login (con eventuale 2FA), refresh, setup TOTP,
cambio password, rigenerazione backup codes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models.users import User
from app.schemas.auth import (
    BackupCodesRegenerateRequest,
    BackupCodesRegenerateResponse,
    ChangePasswordRequest,
    Login2FARequest,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RefreshRequest,
    TokenPairResponse,
    TOTPSetupResponse,
    TOTPVerifyRequest,
    UserPublic,
)
from app.security.deps import get_current_user, get_current_user_allow_unenrolled
from app.security.jwt import (
    TokenError,
    TokenType,
    create_access_token,
    create_login_ticket,
    create_refresh_token,
    decode_token,
    remaining_ttl_seconds,
)
from app.security.password import (
    WeakPasswordError,
    hash_password,
    validate_password_strength,
    verify_password,
)
from app.security.redis_client import (
    blacklist_jti,
    clear_attempts,
    is_jti_blacklisted,
    is_locked_out,
    register_failed_attempt,
)
from app.security.totp import (
    build_provisioning_uri,
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_backup_codes,
    generate_qr_code_base64,
    generate_totp_secret,
    hash_backup_codes,
    regenerate_backup_codes,
    verify_and_consume_backup_code,
    verify_totp_code,
)
from app.services.audit import log_action

router = APIRouter()

_bearer_scheme = HTTPBearer(auto_error=True)


def _too_many_attempts(retry_after_seconds: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "error_code": "too_many_attempts",
            "message": "Troppi tentativi falliti. Riprova più tardi.",
            "retry_after_seconds": retry_after_seconds,
        },
    )


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> LoginResponse:
    """Prima fase del login: verifica email+password.

    Se l'utente ha la 2FA attiva, NON emette token pienamente operativi:
    restituisce invece un `mfa_token` effimero (internamente è un "login
    ticket" JWT di breve durata) che il client deve inviare, insieme a un
    codice TOTP o a un backup code, a `POST /auth/login-2fa`.

    Se l'utente ha un ruolo per cui la 2FA è obbligatoria (admin/operator) e
    non l'ha ancora attivata, i token vengono comunque emessi (servono per
    completare il setup) ma con `status="mfa_setup_required"`:
    `get_current_user` blocca ogni altro endpoint finché il setup non è
    completato (vedi app/security/deps.py).

    Rate limiting: la chiave di lockout è l'email normalizzata (non l'id
    utente, per non rivelare via timing se l'email esiste) con soglia
    `LOGIN_MAX_ATTEMPTS`/`LOGIN_LOCKOUT_MINUTES`.
    """
    lockout_key = f"login:{payload.email.lower()}"
    locked_seconds = await is_locked_out(lockout_key)
    if locked_seconds is not None:
        raise _too_many_attempts(locked_seconds)

    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    # Messaggio identico per email inesistente e password errata: evita di
    # rivelare quali email sono registrate (enumeration attack).
    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Email o password non validi."
    )
    password_ok = user is not None and verify_password(payload.password, user.password_hash)
    if user is None or not user.is_active or not password_ok:
        lockout_seconds = await register_failed_attempt(
            lockout_key, settings.LOGIN_MAX_ATTEMPTS, settings.LOGIN_LOCKOUT_MINUTES * 60
        )
        if lockout_seconds is not None:
            raise _too_many_attempts(lockout_seconds)
        raise invalid_credentials

    await clear_attempts(lockout_key)

    if user.totp_enabled:
        ticket = create_login_ticket(user.id, user.role)
        return LoginResponse(status="mfa_required", mfa_token=ticket)

    access = create_access_token(user.id, user.role, user.security_stamp_at)
    refresh = create_refresh_token(user.id, user.role, user.security_stamp_at)
    mfa_enrollment_required = user.role in ("admin", "operator")
    return LoginResponse(
        status="mfa_setup_required" if mfa_enrollment_required else "authenticated",
        access_token=access,
        refresh_token=refresh,
        user=UserPublic.from_user(user),
    )


@router.post("/login-2fa", response_model=TokenPairResponse)
async def login_2fa(
    payload: Login2FARequest, db: AsyncSession = Depends(get_db)
) -> TokenPairResponse:
    """Seconda fase del login per utenti con 2FA attiva: completa
    l'autenticazione verificando un codice TOTP a 6 cifre oppure un backup
    code monouso.

    Se il codice usato era l'ultimo backup code rimasto, rigenera
    automaticamente un nuovo set di 10 codici e li include nella risposta
    (`new_backup_codes`): l'utente non deve mai restare silenziosamente
    senza via di recovery.
    """
    try:
        ticket_payload = decode_token(payload.mfa_token, expected_type=TokenType.LOGIN_2FA)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Login ticket non valido o scaduto."
        ) from exc

    user = await db.get(User, uuid.UUID(ticket_payload["sub"]))
    mfa_ready = user is not None and user.totp_enabled and user.totp_secret_encrypted
    if user is None or not user.is_active or not mfa_ready:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login non valido.")

    lockout_key = f"mfa:{user.id}"
    locked_seconds = await is_locked_out(lockout_key)
    if locked_seconds is not None:
        raise _too_many_attempts(locked_seconds)

    code_is_valid = False
    new_backup_codes: list[str] | None = None

    if len(payload.code) == 6 and payload.code.isdigit():
        secret = decrypt_totp_secret(user.totp_secret_encrypted)
        code_is_valid = verify_totp_code(secret, payload.code)

    if not code_is_valid and user.backup_codes_hash:
        remaining = verify_and_consume_backup_code(payload.code, user.backup_codes_hash)
        if remaining is not None:
            code_is_valid = True
            if remaining:
                user.backup_codes_hash = remaining
            else:
                # Ultimo backup code appena consumato: rigenera subito un
                # nuovo set, altrimenti l'utente resta senza fallback in
                # caso perda anche l'accesso all'app authenticator.
                new_backup_codes, hashed = regenerate_backup_codes()
                user.backup_codes_hash = hashed
            db.add(user)

    if not code_is_valid:
        lockout_seconds = await register_failed_attempt(
            lockout_key, settings.MFA_MAX_ATTEMPTS, settings.MFA_LOCKOUT_MINUTES * 60
        )
        if lockout_seconds is not None:
            raise _too_many_attempts(lockout_seconds)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Codice 2FA non valido."
        )

    await clear_attempts(lockout_key)
    if new_backup_codes is not None:
        await log_action(
            db,
            user_id=user.id,
            action="regenerate_backup_codes",
            entity_type="user",
            entity_id=str(user.id),
            details={"reason": "last_code_consumed_at_login"},
        )
    await db.commit()

    access = create_access_token(user.id, user.role, user.security_stamp_at)
    refresh = create_refresh_token(user.id, user.role, user.security_stamp_at)
    return TokenPairResponse(
        access_token=access,
        refresh_token=refresh,
        user=UserPublic.from_user(user),
        new_backup_codes=new_backup_codes,
    )


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh_token(
    payload: RefreshRequest, db: AsyncSession = Depends(get_db)
) -> TokenPairResponse:
    """Scambia un refresh token valido con una nuova coppia access+refresh.

    Rifiuta il token se il suo claim `sst` non combacia più con
    `user.security_stamp_at` (revocato in blocco da logout/cambio password/
    reset 2FA) o se il suo `jti` è stato messo in blacklist esplicitamente.
    """
    invalid_refresh = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token non valido o scaduto."
    )
    try:
        token_payload = decode_token(payload.refresh_token, expected_type=TokenType.REFRESH)
    except TokenError as exc:
        raise invalid_refresh from exc

    if await is_jti_blacklisted(token_payload.get("jti", "")):
        raise invalid_refresh

    user = await db.get(User, uuid.UUID(token_payload["sub"]))
    if user is None or not user.is_active:
        raise invalid_refresh

    token_sst = token_payload.get("sst")
    if token_sst is None or int(token_sst) != int(user.security_stamp_at.timestamp()):
        raise invalid_refresh

    access = create_access_token(user.id, user.role, user.security_stamp_at)
    refresh = create_refresh_token(user.id, user.role, user.security_stamp_at)
    return TokenPairResponse(access_token=access, refresh_token=refresh)


@router.get("/me", response_model=UserPublic)
async def read_current_user(user: User = Depends(get_current_user_allow_unenrolled)) -> UserPublic:
    """Restituisce il profilo anche durante il flusso obbligatorio di enrollment MFA."""
    return UserPublic.from_user(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def logout(
    payload: LogoutRequest | None = None,
    user: User = Depends(get_current_user_allow_unenrolled),
    db: AsyncSession = Depends(get_db),
    _credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> None:
    """Logout lato server: revoca puntualmente i token della sessione
    corrente mettendo in blacklist Redis i loro `jti` (TTL = tempo residuo
    alla scadenza naturale), oltre a registrare l'evento in `audit_log`.

    L'access token corrente viene sempre revocato; se il client invia anche
    il refresh token nel body, viene revocato pure quello. Un logout
    "globale" (tutte le sessioni, non solo quella corrente) è invece
    ottenuto aggiornando `security_stamp_at` — vedi cambio password e reset
    2FA, che lo fanno esplicitamente.
    """
    access_payload = decode_token(_credentials.credentials, expected_type=TokenType.ACCESS)
    await blacklist_jti(access_payload["jti"], remaining_ttl_seconds(access_payload))

    if payload and payload.refresh_token:
        try:
            refresh_payload = decode_token(payload.refresh_token, expected_type=TokenType.REFRESH)
        except TokenError:
            refresh_payload = None
        if refresh_payload is not None:
            await blacklist_jti(refresh_payload["jti"], remaining_ttl_seconds(refresh_payload))

    await log_action(
        db, user_id=user.id, action="logout", entity_type="user", entity_id=str(user.id)
    )
    await db.commit()


@router.post("/setup-2fa", response_model=TOTPSetupResponse)
async def setup_2fa(
    user: User = Depends(get_current_user_allow_unenrolled), db: AsyncSession = Depends(get_db)
) -> TOTPSetupResponse:
    """Avvia il setup della 2FA: genera un nuovo secret TOTP e 10 backup
    codes, mostrati UNA SOLA VOLTA nella risposta.

    Il secret viene salvato cifrato ma `totp_enabled` resta False finché
    l'utente non conferma di aver configurato correttamente l'app
    authenticator tramite `POST /auth/verify-2fa`: evita di "attivare" una
    2FA che l'utente non è di fatto in grado di usare.
    """
    secret = generate_totp_secret()
    provisioning_uri = build_provisioning_uri(secret, account_email=user.email)
    qr_code = generate_qr_code_base64(provisioning_uri)

    backup_codes = generate_backup_codes()

    user.totp_secret_encrypted = encrypt_totp_secret(secret)
    user.backup_codes_hash = hash_backup_codes(backup_codes)
    user.totp_enabled = False
    db.add(user)
    await db.commit()

    return TOTPSetupResponse(secret=secret, qr_code_base64=qr_code, backup_codes=backup_codes)


@router.post("/verify-2fa", response_model=UserPublic)
async def verify_2fa(
    payload: TOTPVerifyRequest,
    user: User = Depends(get_current_user_allow_unenrolled),
    db: AsyncSession = Depends(get_db),
) -> UserPublic:
    """Conferma il setup 2FA: se il codice è valido, attiva definitivamente
    `totp_enabled`. Stesso rate limiting delle altre verifiche 2FA, per non
    lasciare un canale di brute-force sul codice iniziale."""
    lockout_key = f"mfa_setup:{user.id}"
    locked_seconds = await is_locked_out(lockout_key)
    if locked_seconds is not None:
        raise _too_many_attempts(locked_seconds)

    if not user.totp_secret_encrypted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nessun setup 2FA in corso: chiama prima POST /auth/setup-2fa.",
        )

    secret = decrypt_totp_secret(user.totp_secret_encrypted)
    if not verify_totp_code(secret, payload.code):
        lockout_seconds = await register_failed_attempt(
            lockout_key, settings.MFA_MAX_ATTEMPTS, settings.MFA_LOCKOUT_MINUTES * 60
        )
        if lockout_seconds is not None:
            raise _too_many_attempts(lockout_seconds)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Codice TOTP non valido."
        )

    await clear_attempts(lockout_key)
    user.totp_enabled = True
    db.add(user)
    await log_action(
        db, user_id=user.id, action="enable_2fa", entity_type="user", entity_id=str(user.id)
    )
    await db.commit()

    return UserPublic.from_user(user)


@router.post("/2fa/backup-codes/regenerate", response_model=BackupCodesRegenerateResponse)
async def regenerate_backup_codes_endpoint(
    payload: BackupCodesRegenerateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BackupCodesRegenerateResponse:
    """Rigenerazione manuale dei backup codes: invalida tutti i codici
    precedenti. Richiede di ri-dimostrare il possesso del dispositivo TOTP
    (un access token valido da solo non basta), per impedire che un token
    rubato possa da solo invalidare la via di recovery della vittima."""
    if not user.totp_enabled or not user.totp_secret_encrypted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="La 2FA non è attiva su questo account."
        )

    secret = decrypt_totp_secret(user.totp_secret_encrypted)
    if not verify_totp_code(secret, payload.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Codice TOTP non valido."
        )

    codes, hashed = regenerate_backup_codes()
    user.backup_codes_hash = hashed
    db.add(user)
    await log_action(
        db,
        user_id=user.id,
        action="regenerate_backup_codes",
        entity_type="user",
        entity_id=str(user.id),
        details={"reason": "manual"},
    )
    await db.commit()

    return BackupCodesRegenerateResponse(backup_codes=codes)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user_allow_unenrolled),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Cambia la password dell'utente corrente e revoca in blocco tutti i
    refresh/access token già emessi (aggiornando `security_stamp_at`): un
    cambio password deve invalidare qualunque sessione aperta con la
    vecchia credenziale, non solo quella corrente."""
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Password corrente non corretta."
        )

    try:
        validate_password_strength(payload.new_password, email=user.email)
    except WeakPasswordError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    user.password_hash = hash_password(payload.new_password)
    user.security_stamp_at = datetime.now(UTC)
    db.add(user)
    await log_action(
        db, user_id=user.id, action="change_password", entity_type="user", entity_id=str(user.id)
    )
    await db.commit()
