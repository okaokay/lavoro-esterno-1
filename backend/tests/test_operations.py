"""Regressioni della console operativa e delle relative regole di dominio."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.v1.operations import router as operations_router
from app.schemas.operations import ClassifierSettingsUpdate, NotificationList
from app.services.media_classifier import NudeNetOnnxMediaClassifier


def test_classifier_uses_database_thresholds_and_records_revision() -> None:
    result = NudeNetOnnxMediaClassifier.from_detections(
        [{"class": "FEMALE_BREAST_EXPOSED", "score": 0.55}],
        safe_threshold=0.10,
        explicit_threshold=0.50,
        config_revision=7,
    )
    assert result.classification == "explicit"
    assert result.safety_signals["explicitThreshold"] == 0.50
    assert result.safety_signals["classifierConfigRevision"] == 7


def test_classifier_thresholds_must_not_overlap() -> None:
    with pytest.raises(ValidationError):
        ClassifierSettingsUpdate(safe_threshold=0.7, explicit_threshold=0.6, expected_revision=1)


def test_notification_contract_is_camel_case() -> None:
    dumped = NotificationList(items=[], unread_count=3).model_dump(by_alias=True)
    assert dumped == {"items": [], "unreadCount": 3}


def test_read_all_notification_route_precedes_uuid_route() -> None:
    """The literal path must not be consumed as an invalid UUID parameter."""
    paths = [route.path for route in operations_router.routes]
    assert paths.index("/notifications/read-all") < paths.index(
        "/notifications/{notification_id}/read"
    )
