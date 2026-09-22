"""Endpoint amministrativi: gestione utenti e consultazione audit log.

Nota RBAC: le operazioni di sola lettura (`GET /admin/users`,
`GET /admin/audit-log`) richiedono il ruolo "admin"; le operazioni che
creano account o ne cambiano i permessi (`POST /admin/users`) restano
protette con `require_admin_with_2fa` (vedi app/security/deps.py) per
impedire che un account admin compromesso, privo di 2FA, possa da solo
alterare la base utenti. Il cambio ruolo/sospensione (`PATCH`, `.../suspend`)
usa lo stesso vincolo per lo stesso motivo: sono modifiche dirette ai
permessi di un altro utente.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.audit_log import AuditLog
from app.models.users import User
from app.schemas.admin import (
    AdminUserRead,
    AdminUserUpdate,
    AuditLogEntryRead,
    UserCreate,
    display_name_from_email,
    status_from_is_active,
)
from app.schemas.auth import TwoFactorResetResponse
from app.security.deps import require_admin_with_2fa, require_role
from app.security.password import hash_password
from app.services.audit import log_action

router = APIRouter()

# Ruoli validi lato dominio (stessi valori dell'enum Postgres `user_role`,
# vedi app/models/users.py): validati qui esplicitamente perché
# AdminUserUpdate.role è un semplice `str` (per non duplicare l'enum
# SQLAlchemy in Pydantic) e un valore non valido andrebbe comunque
# rifiutato con un errore chiaro invece di un IntegrityError generico del DB.
_VALID_ROLES = {"admin", "operator", "viewer"}


def _to_admin_user_read(user: User) -> AdminUserRead:
    return AdminUserRead(
        id=user.id,
        name=display_name_from_email(user.email),
        email=user.email,
        role=user.role,
        status=status_from_is_active(user.is_active),
        mfa_enabled=user.totp_enabled,
        last_login_at=None,
        can_view_clear_phone=user.role == "admin" or user.can_view_clear_phone,
    )


@router.get("/users", response_model=list[AdminUserRead])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
) -> list[AdminUserRead]:
    """Elenco utenti per la pagina Admin > Users.

    Cambiato da `UserRead` (snake_case, 1:1 con le colonne ORM) ad
    `AdminUserRead` (camelCase): `frontend/src/api/admin.ts:fetchAdminUsers`
    consuma la risposta direttamente come `AdminUser[]`, senza mapping
    intermedio (vedi `app/schemas/common.py:CamelModel`), quindi la forma
    precedente non corrispondeva al contratto atteso dalla UI.
    """
    result = await db.execute(select(User).order_by(User.email))
    return [_to_admin_user_read(u) for u in result.scalars().all()]


@router.post("/users", response_model=AdminUserRead, status_code=201)
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin_with_2fa),
) -> AdminUserRead:
    """Crea un nuovo utente operatore.

    Operazione sensibile (crea account con potenzialmente ampi permessi):
    richiede non solo il ruolo admin ma anche la 2FA attiva sull'account
    admin richiedente (vedi require_admin_with_2fa).

    Risponde con `AdminUserRead` (camelCase), non `UserRead` (bug corretto:
    ogni altro endpoint di quest'area — `GET /users`, `PATCH /users/{id}`,
    `POST /users/{id}/suspend` — risponde già in questa forma, consumata
    direttamente dal frontend come `AdminUser` senza mapping; `UserRead`
    (snake_case) avrebbe fatto leggere `undefined` per `name`/`status`/
    `mfaEnabled` al form "Crea utente" di `frontend/src/routes/AdminPage.tsx`).
    """
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        can_view_clear_phone=payload.can_view_clear_phone if payload.role != "admin" else False,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _to_admin_user_read(user)


async def _get_user_or_404(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utente non trovato.")
    return user


@router.patch("/users/{user_id}", response_model=AdminUserRead)
async def update_user(
    user_id: uuid.UUID,
    payload: AdminUserUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin_with_2fa),
) -> AdminUserRead:
    """Cambia il ruolo di un utente (`frontend/src/api/admin.ts:updateAdminUserRole`).

    Riservato ad admin con 2FA attiva: cambiare il ruolo di un altro utente
    (in particolare promuoverlo ad admin) è un'operazione ad alto impatto
    sui permessi del sistema, stesso criterio già applicato a
    `POST /admin/users`.
    """
    if payload.role is not None and payload.role not in _VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Ruolo non valido: '{payload.role}'. Valori ammessi: {sorted(_VALID_ROLES)}.",
        )

    target = await _get_user_or_404(db, user_id)
    previous_role = target.role
    previous_phone_permission = target.can_view_clear_phone
    if payload.role is not None:
        target.role = payload.role
    if target.role == "admin":
        target.can_view_clear_phone = False
    elif payload.can_view_clear_phone is not None:
        target.can_view_clear_phone = payload.can_view_clear_phone
    db.add(target)

    await log_action(
        db,
        user_id=admin.id,
        action="update_user_role",
        entity_type="user",
        entity_id=str(user_id),
        details={
            "previous_role": previous_role,
            "new_role": target.role,
            "previous_clear_phone": previous_phone_permission,
            "new_clear_phone": target.role == "admin" or target.can_view_clear_phone,
        },
    )
    await db.commit()
    await db.refresh(target)

    return _to_admin_user_read(target)


@router.post("/users/{user_id}/suspend", response_model=AdminUserRead)
async def suspend_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin_with_2fa),
) -> AdminUserRead:
    """Sospende un utente (`is_active=False`): impedisce nuovi login (vedi
    `app/api/v1/auth.py:login`, che rifiuta esplicitamente gli utenti con
    `is_active=False`), senza cancellarne i dati/lo storico."""
    target = await _get_user_or_404(db, user_id)
    if target.id == admin.id:
        raise HTTPException(status_code=409, detail="Non puoi sospendere il tuo account.")
    if target.role == "admin" and target.is_active:
        active_admins = (
            await db.execute(
                select(func.count())
                .select_from(User)
                .where(User.role == "admin", User.is_active.is_(True))
            )
        ).scalar_one()
        if active_admins <= 1:
            raise HTTPException(status_code=409, detail="Deve rimanere almeno un Admin attivo.")
    target.is_active = False
    target.security_stamp_at = datetime.now(UTC)
    db.add(target)

    await log_action(
        db, user_id=admin.id, action="suspend_user", entity_type="user", entity_id=str(user_id)
    )
    await db.commit()
    await db.refresh(target)

    return _to_admin_user_read(target)


@router.post("/users/{user_id}/activate", response_model=AdminUserRead)
async def activate_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin_with_2fa),
) -> AdminUserRead:
    """Riattiva un account sospeso senza rendere nuovamente validi vecchi token."""
    target = await _get_user_or_404(db, user_id)
    target.is_active = True
    target.security_stamp_at = datetime.now(UTC)
    db.add(target)
    await log_action(
        db, user_id=admin.id, action="activate_user", entity_type="user", entity_id=str(user_id)
    )
    await db.commit()
    await db.refresh(target)
    return _to_admin_user_read(target)


@router.post("/users/{user_id}/reset-2fa", response_model=TwoFactorResetResponse)
async def reset_user_2fa(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin_with_2fa),
) -> TwoFactorResetResponse:
    """Procedura di recovery account: disattiva la 2FA di un utente che ha
    perso sia il dispositivo TOTP sia i backup codes, senza alcun
    meccanismo di reset via email (non esiste un servizio email nel
    progetto). Dopo il reset l'utente rifà il setup 2FA obbligatorio al
    prossimo login (stesso enforcement di `get_current_user`, vedi
    app/security/deps.py), quindi non è mai realmente "senza 2FA" per più
    di una sessione di login.

    Aggiorna anche `security_stamp_at`, revocando in blocco ogni token
    residuo dell'utente colpito: se l'account è stato compromesso insieme
    alla perdita dei fattori 2FA, un eventuale token ancora valido non deve
    restare utilizzabile dopo il reset.
    """
    target = await _get_user_or_404(db, user_id)
    target.totp_secret_encrypted = None
    target.totp_enabled = False
    target.backup_codes_hash = None
    target.security_stamp_at = datetime.now(UTC)
    db.add(target)

    await log_action(
        db, user_id=admin.id, action="reset_2fa", entity_type="user", entity_id=str(user_id)
    )
    await db.commit()
    await db.refresh(target)

    return TwoFactorResetResponse(id=target.id, mfa_enabled=target.totp_enabled)


@router.get("/audit-log", response_model=list[AuditLogEntryRead])
async def list_audit_log(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin")),
) -> list[AuditLogEntryRead]:
    """Consultazione dell'audit log (azioni sensibili: login/logout, export,
    modifiche utenti/fonti...). Riservato ai soli admin.

    Non paginato esplicitamente lato query params (il frontend
    `fetchAuditLog()` non ne passa): restituiamo le 200 righe più recenti,
    un compromesso ragionevole tra utilità e dimensione della risposta senza
    introdurre un contratto di paginazione che il frontend non usa ancora.
    """
    stmt = (
        select(AuditLog, User.email)
        .outerjoin(User, User.id == AuditLog.user_id)
        .order_by(AuditLog.created_at.desc())
        .limit(200)
    )
    rows = (await db.execute(stmt)).all()

    return [
        AuditLogEntryRead(
            id=log.id,
            actor=actor_email or "Sistema",
            action=log.action,
            target=f"{log.entity_type}:{log.entity_id}" if log.entity_id else log.entity_type,
            occurred_at=log.created_at,
        )
        for log, actor_email in rows
    ]
