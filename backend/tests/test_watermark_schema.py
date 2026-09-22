"""Validazione della configurazione autorizzata per la rimozione watermark."""

import pytest
from pydantic import ValidationError

from app.schemas.sources import WatermarkRemovalConfig


def test_enabled_watermark_requires_authorization_and_region():
    with pytest.raises(ValidationError):
        WatermarkRemovalConfig(enabled=True)


def test_authorized_watermark_region_is_normalized():
    config = WatermarkRemovalConfig(
        enabled=True,
        authorizationReference="contract-42",
        regions=[{"x": 0.7, "y": 0.8, "width": 0.2, "height": 0.1}],
    )
    assert config.enabled


def test_region_must_stay_inside_frame():
    with pytest.raises(ValidationError):
        WatermarkRemovalConfig(
            enabled=True,
            authorizationReference="contract-42",
            regions=[{"x": 0.9, "y": 0.8, "width": 0.2, "height": 0.1}],
        )
