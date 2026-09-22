"""Local ONNX media classification with conservative human-review policy."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from app.config import settings

EXPLICIT_LABELS = {
    "BUTTOCKS_EXPOSED",
    "FEMALE_BREAST_EXPOSED",
    "FEMALE_GENITALIA_EXPOSED",
    "MALE_GENITALIA_EXPOSED",
    "ANUS_EXPOSED",
}
FACE_LABELS = {"FACE_FEMALE", "FACE_MALE"}


@dataclass(frozen=True)
class ClassificationResult:
    classification: str
    confidence: float
    model_version: str
    safety_signals: dict[str, Any] = field(default_factory=dict)
    review_required: bool = True


class MediaClassifier(ABC):
    @abstractmethod
    def classify(self, file_bytes: bytes, mime_type: str) -> ClassificationResult:
        raise NotImplementedError


@lru_cache(maxsize=1)
def _detector():
    from nudenet import NudeDetector

    return NudeDetector(inference_resolution=320)


class NudeNetOnnxMediaClassifier(MediaClassifier):
    """NudeNet 3.4.2 (YOLOv8n ONNX) with explicit, face and review signals."""

    MODEL_VERSION = "nudenet-3.4.2-320n"

    def __init__(
        self,
        *,
        safe_threshold: float | None = None,
        explicit_threshold: float | None = None,
        config_revision: int | None = None,
    ) -> None:
        self.safe_threshold = (
            settings.MEDIA_SAFE_THRESHOLD if safe_threshold is None else safe_threshold
        )
        self.explicit_threshold = (
            settings.MEDIA_EXPLICIT_THRESHOLD if explicit_threshold is None else explicit_threshold
        )
        self.config_revision = config_revision

    @staticmethod
    def from_detections(
        detections: list[dict[str, Any]],
        *,
        watermark_present: bool = False,
        safe_threshold: float | None = None,
        explicit_threshold: float | None = None,
        config_revision: int | None = None,
    ) -> ClassificationResult:
        explicit_score = max(
            (float(d.get("score", 0)) for d in detections if d.get("class") in EXPLICIT_LABELS),
            default=0.0,
        )
        face_score = max(
            (float(d.get("score", 0)) for d in detections if d.get("class") in FACE_LABELS),
            default=0.0,
        )
        safe_limit = settings.MEDIA_SAFE_THRESHOLD if safe_threshold is None else safe_threshold
        explicit_limit = (
            settings.MEDIA_EXPLICIT_THRESHOLD if explicit_threshold is None else explicit_threshold
        )
        explicit = explicit_score >= explicit_limit
        face_visible = face_score >= 0.50
        possible_minor_review = explicit and face_visible

        if explicit:
            classification = "explicit"
            confidence = explicit_score
            review_required = possible_minor_review
        elif explicit_score < safe_limit:
            classification = "safe"
            confidence = 1.0 - explicit_score
            review_required = False
        else:
            classification = "unclassified"
            confidence = explicit_score
            review_required = True

        return ClassificationResult(
            classification=classification,
            confidence=round(confidence, 6),
            model_version=NudeNetOnnxMediaClassifier.MODEL_VERSION,
            review_required=review_required,
            safety_signals={
                "explicitContent": explicit,
                "explicitScore": round(explicit_score, 6),
                "faceVisible": face_visible,
                "faceScore": round(face_score, 6),
                "watermarkPresent": watermark_present,
                # Policy escalation only; never an automated age estimate.
                "possibleMinorReview": possible_minor_review,
                "safeThreshold": safe_limit,
                "explicitThreshold": explicit_limit,
                "classifierConfigRevision": config_revision,
            },
        )

    def classify(self, file_bytes: bytes, mime_type: str) -> ClassificationResult:
        if not mime_type.startswith("image/"):
            raise ValueError("NudeNet richiede un'immagine o un frame video.")
        detections = _detector().detect(file_bytes)
        return self.from_detections(
            detections,
            safe_threshold=self.safe_threshold,
            explicit_threshold=self.explicit_threshold,
            config_revision=self.config_revision,
        )


# Backwards-compatible import name; it is no longer rule based.
RuleBasedMediaClassifier = NudeNetOnnxMediaClassifier


def aggregate_results(results: list[ClassificationResult]) -> ClassificationResult:
    """Conservative video aggregation: retain the frame with greatest risk."""
    if not results:
        raise ValueError("Nessun frame classificabile.")
    return max(results, key=lambda item: float(item.safety_signals.get("explicitScore", 0)))
