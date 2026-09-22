"""Modello `User`: operatori del sistema (non utenti finali)."""

from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin

UserRole = sa.Enum("admin", "operator", "viewer", name="user_role", create_type=True)


class User(UUIDPKMixin, TimestampMixin, Base):
    """Account operatore, con RBAC a 3 ruoli e 2FA TOTP opzionale (ma
    obbligatoria per operazioni sensibili se il ruolo è admin, vedi
    app/api/v1/admin.py)."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(UserRole, default="viewer", nullable=False)

    # Il secret TOTP non è mai salvato in chiaro: viene cifrato con lo stesso
    # schema AES-256-GCM usato per il telefono (vedi app/services/phone_crypto.py
    # per lo schema di cifratura; il secret TOTP usa la stessa primitiva ma è
    # concettualmente indipendente dal dominio "telefono").
    totp_secret_encrypted: Mapped[bytes | None] = mapped_column(sa.LargeBinary, nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Lista di hash argon2 dei backup codes monouso (uno consumato = rimosso
    # dalla lista, o marcato; qui li trattiamo come lista JSON di hash per
    # semplicità dello scaffold).
    backup_codes_hash: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    can_view_clear_phone: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Timestamp di "validità minima" dei token: ogni access/refresh JWT porta
    # con sé il claim `sst` (security stamp), preso da questo campo al momento
    # dell'emissione. Aggiornarlo a `now()` invalida in blocco TUTTI i token
    # già emessi per l'utente (confrontato in app/security/deps.py), senza
    # dover tracciare ogni singolo jti mai emesso: usato su logout, cambio
    # password e reset/disattivazione 2FA (anche da parte di un Admin).
    security_stamp_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
