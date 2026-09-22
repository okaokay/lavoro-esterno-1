"""Validazione e trasformazione deterministica di immagini e video."""

import io
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from app.services.media_processing import (
    MediaValidationError,
    probe_video,
    process_video,
    remove_image_watermark,
    validate_image,
)


def _jpeg() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (100, 80), "white").save(output, format="JPEG")
    return output.getvalue()


def test_image_validation_uses_decoded_dimensions():
    metadata = validate_image(_jpeg(), "image/jpeg")
    assert (metadata.width, metadata.height) == (100, 80)


def test_mime_mismatch_is_rejected():
    with pytest.raises(MediaValidationError):
        validate_image(_jpeg(), "image/png")


def test_watermark_derivative_never_mutates_original():
    original = _jpeg()
    derived = remove_image_watermark(original, [{"x": 0.7, "y": 0.7, "width": 0.2, "height": 0.2}])
    assert original == _jpeg()
    assert derived != original
    assert validate_image(derived, "image/jpeg").width == 100


def test_corrupt_video_is_rejected():
    with pytest.raises(MediaValidationError):
        probe_video(b"not-a-video", "video/mp4")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg non disponibile")
def test_ffmpeg_pipeline_transcodes_caps_resolution_and_extracts_five_frames():
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "source.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc=size=1280x800:rate=10:duration=1",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(source),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        original = source.read_bytes()
        original_copy = bytes(original)

    display, thumbnail, frames = process_video(original)
    metadata = probe_video(display, "video/mp4")
    thumbnail_metadata = validate_image(thumbnail, "image/jpeg")
    assert metadata.width <= 1280 and metadata.height <= 720
    assert thumbnail_metadata.width <= 640 and thumbnail_metadata.height <= 640
    assert len(frames) == 5
    assert all(validate_image(frame, "image/jpeg") for frame in frames)
    assert original == original_copy
