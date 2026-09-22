"""Utility per registrare eventi nell'audit log (`app.models.audit_log.AuditLog`).

Centralizza la creazione della riga così ogni endpoint che compie
un'azione sensibile (login/logout, cambio ruolo, sospensione utente,
pausa/disabilitazione fonte, retry export, rigenerazione riepilogo AI...)
la traccia in modo uniforme, senza duplicare la logica di costruzione
dell'oggetto in ogni router.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


async def log_action(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Aggiunge una riga di audit log alla sessione corrente.

    Non esegue il commit: è responsabilità del chiamante farlo insieme alle
    altre modifiche della stessa richiesta, così l'evento di audit fa parte
    della stessa transazione dell'azione che documenta (se l'azione fallisce
    e la transazione va in rollback, non resta un audit log "orfano" di
    un'operazione che in realtà non è avvenuta).
    """
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details_json=details,
        )
    )
