"""Idempotent Celery media validation, derivatives and ONNX classification."""

from __future__ import annotations

import io
import logging
import uuid

from PIL import Image
from sqlalchemy import select

from app.models.advertisement import Advertisement
from app.models.audit_log import AuditLog
from app.models.media import Media
from app.models.media_classification_history import MediaClassificationHistory
from app.models.operations import MediaClassifierSettings
from app.models.sources import Source
from app.services.media_classifier import NudeNetOnnxMediaClassifier, aggregate_results
from app.services.media_processing import (
    MediaValidationError,
    process_video,
    remove_image_watermark,
    validate_image,
)
from app.services.media_storage import get_object_bytes, put_object_bytes
from app.services.notifications import create_notification
from app.workers.celery_app import celery_app
from app.workers.tasks_scraper import SyncSessionLocal

logger = logging.getLogger(__name__)


def _thumbnail(data: bytes) -> bytes:
    with Image.open(io.BytesIO(data)) as source:
        image = source.convert("RGB")
        image.thumbnail((640, 640))
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=88, optimize=True)
        return output.getvalue()


@celery_app.task(name="app.workers.tasks_media.process_media", bind=True, max_retries=2)
def process_media(self, media_id: str, force: bool = False) -> dict:
    media_uuid = uuid.UUID(media_id)
    session = SyncSessionLocal()
    try:
        media = session.get(Media, media_uuid)
        if media is None:
            return {"status": "failed", "reason": "media_not_found"}
        if media.processing_status == "ready" and not force:
            return {"status": "ready", "media_id": media_id, "idempotent": True}

        media.processing_status = "processing"
        media.processing_error = None
        session.commit()

        source = session.execute(
            select(Source)
            .join(Advertisement, Advertisement.source_id == Source.id)
            .where(Advertisement.id == media.advertisement_id)
        ).scalar_one()
        record_id = session.execute(
            select(Advertisement.record_id).where(Advertisement.id == media.advertisement_id)
        ).scalar_one()
        original = get_object_bytes(media.original_object_key)
        classifier_config = session.get(MediaClassifierSettings, 1)
        classifier = NudeNetOnnxMediaClassifier(
            safe_threshold=classifier_config.safe_threshold if classifier_config else None,
            explicit_threshold=classifier_config.explicit_threshold if classifier_config else None,
            config_revision=classifier_config.revision if classifier_config else None,
        )
        base = media.original_object_key.rsplit("/", 1)[0]
        watermark = bool(source.watermark_removal_enabled and source.watermark_regions)
        regions = source.watermark_regions or []

        if media.mime_type.startswith("image/"):
            metadata = validate_image(original, media.mime_type)
            display = remove_image_watermark(original, regions) if watermark else original
            display_mime = "image/jpeg" if watermark else media.mime_type
            if watermark:
                media.display_object_key = put_object_bytes(
                    f"{base}/display.jpg", display, display_mime
                )
            else:
                media.display_object_key = media.original_object_key
            media.thumbnail_object_key = put_object_bytes(
                f"{base}/thumbnail.jpg", _thumbnail(display), "image/jpeg"
            )
            result = classifier.classify(display, display_mime)
            media.width, media.height = metadata.width, metadata.height
        elif media.mime_type.startswith("video/"):
            display, thumbnail, frames = process_video(original, regions if watermark else None)
            media.display_object_key = put_object_bytes(f"{base}/display.mp4", display, "video/mp4")
            media.thumbnail_object_key = put_object_bytes(
                f"{base}/thumbnail.jpg", thumbnail, "image/jpeg"
            )
            result = aggregate_results(
                [classifier.classify(frame, "image/jpeg") for frame in frames]
            )
        else:
            raise MediaValidationError("Tipo media non supportato.")

        signals = dict(result.safety_signals)
        signals["watermarkPresent"] = watermark
        previous = media.classification
        media.classification = result.classification
        media.classification_confidence = result.confidence
        media.classifier_version = result.model_version
        media.safety_signals = signals
        media.review_status = "required" if result.review_required else "not_required"
        media.processing_status = "ready"
        media.processing_error = None
        media.derived_object_key = media.display_object_key  # legacy compatibility

        session.add(
            MediaClassificationHistory(
                media_id=media.id,
                previous_classification=previous,
                new_classification=result.classification,
                confidence=result.confidence,
                manual_override=False,
            )
        )
        if watermark:
            session.add(
                AuditLog(
                    user_id=None,
                    action="remove_watermark",
                    entity_type="media",
                    entity_id=str(media.id),
                    details_json={
                        "source_id": str(source.id),
                        "authorization_reference": source.watermark_authorization_reference,
                        "regions_count": len(regions),
                    },
                )
            )
        if media.review_status == "required":
            create_notification(
                session,
                kind="media_review",
                severity="warning",
                title="Media da revisionare",
                message="Una classificazione media richiede revisione umana.",
                link=f"/records/{record_id}/media",
                audience="operator",
                dedup_key=f"media_review:{media.id}:{classifier.config_revision or 0}",
            )
        session.commit()
        return {"status": "ready", "media_id": media_id}
    except Exception as exc:
        session.rollback()
        media = session.get(Media, media_uuid)
        if media is not None:
            media.processing_status = "failed"
            media.processing_error = str(exc)[:2000]
            media.review_status = "required"
            session.commit()
        logger.exception("Elaborazione media fallita per %s", media_id)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=2 ** (self.request.retries + 1)) from exc
        return {"status": "failed", "media_id": media_id}
    finally:
        session.close()


@celery_app.task(name="app.workers.tasks_media.classify_media")
def classify_media(media_id: str) -> dict:
    return process_media.run(media_id, True)


@celery_app.task(name="app.workers.tasks_media.compute_perceptual_hash")
def compute_perceptual_hash(media_id: str) -> dict:
    import imagehash

    session = SyncSessionLocal()
    try:
        media = session.get(Media, uuid.UUID(media_id))
        if media is None:
            return {"status": "failed", "reason": "media_not_found"}
        if not media.mime_type.startswith("image/"):
            return {"status": "skipped", "reason": "not_image"}
        with Image.open(io.BytesIO(get_object_bytes(media.original_object_key))) as image:
            media.perceptual_hash = str(imagehash.phash(image))
        session.commit()
        return {"status": "ready", "media_id": media_id}
    finally:
        session.close()


@celery_app.task(name="app.workers.tasks_media.transcode_video")
def transcode_video(media_id: str) -> dict:
    return process_media.run(media_id, True)
