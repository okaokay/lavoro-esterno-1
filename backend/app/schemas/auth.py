"""Schemi Pydantic per autenticazione, login a due fasi (password + 2FA) e setup TOTP.

I nomi campo qui DEVONO combaciare esattamente con quanto letto da
`frontend/src/api/auth.ts` (che fa il mapping snake_case -> camelCase a
mano, senza passare per un alias generator): è il contratto concordato tra
i due lati, verificato esplicitamente durante lo sviluppo.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserPublic(BaseModel):
    """Rappresentazione dell'utente esposta al frontend (login, /me, ecc.).

    `name` e `status` non hanno una colonna dedicata nel modello `User`
    (che ha solo `is_active`, non un vero ciclo di vita active/suspended/
    invited): sono derivati qui in modo esplicito e documentato, in attesa
    di un'eventuale migrazione che aggiunga queste colonne (vedi
    PROGETTO.md). Non introduciamo nuove colonne in questa fase per non
    toccare la migrazione Alembic già scritta senza necessità stringente.
    """

    id: uuid.UUID
    email: EmailStr
    name: str
    role: str
    mfa_enabled: bool
    status: str

    @staticmethod
    def from_user(user) -> UserPublic:  # noqa: ANN001 - evita import ciclico su app.models.users.User
        return UserPublic(
            id=user.id,
            email=user.email,
            # Placeholder: nessuna colonna "name" nel modello User. Deriviamo
            # un nome leggibile dalla parte locale dell'email finché non
            # viene introdotto un vero campo anagrafico.
            name=user.email.split("@", 1)[0],
            role=user.role,
            mfa_enabled=user.totp_enabled,
            # Nessun tracking di stato "invited": un utente esiste solo dopo
            # essere stato creato attivo da un Admin, quindi il solo stato
            # derivabile da is_active è active/suspended.
            status="active" if user.is_active else "suspended",
        )


class LoginResponse(BaseModel):
    """Esito del login con sola password.

    Se `status == "mfa_required"`, `access_token`/`refresh_token`/`user`
    sono assenti: il client deve chiamare `POST /auth/login-2fa` con lo
    stesso `mfa_token` e un codice TOTP (o backup code) per completare
    l'accesso.

    Se `status == "mfa_setup_required"`, l'utente ha un ruolo (admin/
    operator) per cui la 2FA è obbligatoria ma non l'ha ancora attivata:
    `access_token`/`refresh_token`/`user` sono presenti (servono per
    chiamare `POST /auth/setup-2fa` e `POST /auth/verify-2fa`), ma
    `get_current_user` (vedi app/security/deps.py) rifiuterà con 403
    qualunque altro endpoint finché il setup non è completato.
    """

    status: str  # "authenticated" | "mfa_required" | "mfa_setup_required"
    mfa_token: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    user: UserPublic | None = None


class Login2FARequest(BaseModel):
    mfa_token: str
    code: str = Field(
        min_length=6, max_length=12, description="Codice TOTP a 6 cifre o backup code."
    )


class TokenPairResponse(BaseModel):
    """Risposta di login-2fa e refresh.

    `status`/`user` sono presenti solo nella risposta di `/auth/login-2fa`
    (dove il frontend li richiede per completare `LoginResult`); `/auth/
    refresh` restituisce lo stesso schema con questi due campi assenti, dato
    che il frontend per il refresh usa solo i token.
    """

    status: str = "authenticated"
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserPublic | None = None
    new_backup_codes: list[str] | None = Field(
        default=None,
        description=(
            "Presente SOLO se il login ha appena consumato l'ultimo backup code "
            "rimasto: contiene i 10 nuovi codici generati automaticamente, da "
            "mostrare UNA SOLA VOLTA all'utente prima di procedere."
        ),
    )


class RefreshRequest(BaseModel):
    refresh_token: str


class TOTPSetupResponse(BaseModel):
    """Risposta al setup 2FA: secret + QR code + backup codes, mostrati
    UNA SOLA VOLTA. Il client deve mostrarli all'utente e invitarlo a
    salvarli in un luogo sicuro."""

    secret: str
    qr_code_base64: str
    backup_codes: list[str]


class TOTPVerifyRequest(BaseModel):
    """Conferma dell'attivazione 2FA: l'utente deve dimostrare di aver
    configurato correttamente l'app authenticator inserendo un primo codice
    valido prima che `totp_enabled` venga impostato a True."""

    code: str = Field(min_length=6, max_length=6)


class LogoutRequest(BaseModel):
    """Body opzionale del logout: se il client invia anche il refresh
    token, viene messo in blacklist insieme all'access token corrente
    (altrimenti solo l'access token viene revocato)."""

    refresh_token: str | None = None


class BackupCodesRegenerateRequest(BaseModel):
    """Rigenerazione manuale dei backup codes: richiede di ri-dimostrare il
    possesso del dispositivo TOTP (stesso principio di `verify-2fa`), non
    basta un access token valido da solo."""

    code: str = Field(min_length=6, max_length=6)


class BackupCodesRegenerateResponse(BaseModel):
    backup_codes: list[str]


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class TwoFactorResetResponse(BaseModel):
    """Esito del reset 2FA amministrativo (recovery account)."""

    id: uuid.UUID
    mfa_enabled: bool
