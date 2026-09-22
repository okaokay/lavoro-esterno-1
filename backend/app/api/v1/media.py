"""Endpoint di lettura per i media associati agli annunci."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.media import Media
from app.models.media_classification_history import MediaClassificationHistory
from app.models.users import User
from app.schemas.media import MediaRead, MediaReprocessResponse, MediaReviewInput
from app.security.deps import get_current_user, require_role
from app.services.audit import log_action
from app.services.media_storage import presigned_media_url

router = APIRouter()


def _media_read(media: Media) -> MediaRead:
    payload = MediaRead.model_validate(media).model_copy(
        update={
            "original_url": presigned_media_url(media.original_object_key),
            "display_url": presigned_media_url(
                media.display_object_key or media.derived_object_key or media.original_object_key
            ),
            "thumbnail_url": presigned_media_url(
                media.thumbnail_object_key or media.display_object_key or media.original_object_key
            ),
        }
    )
    return payload


@router.get("/by-advertisement/{advertisement_id}", response_model=list[MediaRead])
async def list_media_for_advertisement(
    advertisement_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[MediaRead]:
    """Elenca le versioni media correnti associate a un'occorrenza."""
    result = await db.execute(
        select(Media).where(Media.advertisement_id == advertisement_id, Media.is_current.is_(True))
    )
    return [_media_read(m) for m in result.scalars().all()]


@router.get("/{media_id}", response_model=MediaRead)
async def get_media(
    media_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> MediaRead:
    """Restituisce metadati e stato di elaborazione di un media."""
    media = await db.get(Media, media_id)
    if media is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media non trovato.")
    return _media_read(media)


@router.post("/{media_id}/review", response_model=MediaRead)
async def review_media(
    media_id: uuid.UUID,
    payload: MediaReviewInput,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
) -> MediaRead:
    """Registra la revisione manuale della classificazione di un media."""
    media = await db.get(Media, media_id)
    if media is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media non trovato.")
    previous = media.classification
    media.classification = payload.classification
    media.review_status = "reviewed"
    media.review_notes = payload.notes
    media.reviewed_by_user_id = user.id
    media.reviewed_at = datetime.now(UTC)
    db.add(
        MediaClassificationHistory(
            media_id=media.id,
            previous_classification=previous,
            new_classification=payload.classification,
            confidence=media.classification_confidence,
            manual_override=True,
            changed_by_user_id=user.id,
        )
    )
    await log_action(
        db,
        user_id=user.id,
        action="review_media",
        entity_type="media",
        entity_id=str(media.id),
        details={"classification": payload.classification},
    )
    await db.commit()
    await db.refresh(media)
    return _media_read(media)


@router.post("/{media_id}/reprocess", response_model=MediaReprocessResponse, status_code=202)
async def reprocess_media(
    media_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "operator")),
) -> MediaReprocessResponse:
    """Azzera l'errore e riaccoda la pipeline media richiesta."""
    media = await db.get(Media, media_id)
    if media is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media non trovato.")
    media.processing_status = "pending"
    media.processing_error = None
    media.review_status = "required"
    await log_action(
        db, user_id=user.id, action="reprocess_media", entity_type="media", entity_id=str(media.id)
    )
    await db.commit()
    from app.workers.tasks_media import process_media

    task = process_media.delay(str(media.id), True)
    return MediaReprocessResponse(media_id=media.id, task_id=task.id)
