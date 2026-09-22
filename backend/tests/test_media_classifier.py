"""Classificazione locale dei media, soglie e aggregazione fail-safe."""

import io

from PIL import Image

from app.services.media_classifier import NudeNetOnnxMediaClassifier, aggregate_results


def test_explicit_face_requires_human_review():
    result = NudeNetOnnxMediaClassifier.from_detections(
        [
            {"class": "FEMALE_BREAST_EXPOSED", "score": 0.91},
            {"class": "FACE_FEMALE", "score": 0.82},
        ]
    )
    assert result.classification == "explicit"
    assert result.review_required is True
    assert result.safety_signals["possibleMinorReview"] is True


def test_low_confidence_is_safe_and_does_not_require_review():
    result = NudeNetOnnxMediaClassifier.from_detections([])
    assert result.classification == "safe"
    assert result.review_required is False


def test_video_aggregation_uses_highest_risk_frame():
    safe = NudeNetOnnxMediaClassifier.from_detections([])
    explicit = NudeNetOnnxMediaClassifier.from_detections(
        [{"class": "MALE_GENITALIA_EXPOSED", "score": 0.80}]
    )
    assert aggregate_results([safe, explicit]).classification == "explicit"


def test_threshold_boundaries_and_version_are_explicit():
    uncertain = NudeNetOnnxMediaClassifier.from_detections(
        [{"class": "FEMALE_BREAST_EXPOSED", "score": 0.20}]
    )
    explicit = NudeNetOnnxMediaClassifier.from_detections(
        [{"class": "FEMALE_BREAST_EXPOSED", "score": 0.65}]
    )
    assert uncertain.classification == "unclassified"
    assert uncertain.review_required is True
    assert explicit.classification == "explicit"
    assert explicit.model_version == "nudenet-3.4.2-320n"


def test_real_nudenet_model_accepts_an_innocuous_image():
    image = Image.new("RGB", (64, 64), "white")
    data = io.BytesIO()
    image.save(data, "JPEG")
    result = NudeNetOnnxMediaClassifier().classify(data.getvalue(), "image/jpeg")
    assert result.classification in {"safe", "unclassified", "explicit"}
    assert 0 <= result.confidence <= 1
