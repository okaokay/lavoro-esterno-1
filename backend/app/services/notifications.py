"""Small, safe notification writer shared by synchronous workers."""

from __future__ import annotations

import uuid

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.operations import NotificationEvent


def create_notification(
    session: Session,
    *,
    kind: str,
    severity: str,
    title: str,
    message: str,
    dedup_key: str,
    audience: str = "operator",
    link: str | None = None,
    owner_user_id: uuid.UUID | None = None,
) -> None:
    """Insert once. Messages must already be sanitized and contain no private data."""
    session.execute(
        insert(NotificationEvent)
        .values(
            id=uuid.uuid4(),
            kind=kind,
            severity=severity,
            title=title,
            message=message,
            dedup_key=dedup_key[:250],
            audience=audience,
            link=link,
            owner_user_id=owner_user_id,
            details_json={},
        )
        .on_conflict_do_nothing(index_elements=[NotificationEvent.dedup_key])
    )
