"""Media validation, FFmpeg derivatives and authorized watermark removal."""

from __future__ import annotations

import io
import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.config import settings

ALLOWED_IMAGES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_VIDEOS = {"video/mp4", "video/webm", "video/quicktime"}


class MediaValidationError(ValueError):
    pass


@dataclass(frozen=True)
class MediaMetadata:
    mime_type: str
    file_size_bytes: int
    width: int
    height: int
    duration_seconds: float | None = None


def validate_image(data: bytes, mime_type: str) -> MediaMetadata:
    if mime_type not in ALLOWED_IMAGES:
        raise MediaValidationError(f"MIME immagine non consentito: {mime_type}")
    if len(data) > settings.MEDIA_IMAGE_MAX_BYTES:
        raise MediaValidationError("Immagine oltre il limite configurato.")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            detected = Image.MIME.get(image.format)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise MediaValidationError("File immagine non valido.") from exc
    if detected != mime_type and not (detected == "image/jpeg" and mime_type == "image/jpeg"):
        raise MediaValidationError("Il contenuto non corrisponde al MIME dichiarato.")
    if width * height > settings.MEDIA_IMAGE_MAX_PIXELS:
        raise MediaValidationError("Immagine oltre il limite di pixel configurato.")
    return MediaMetadata(mime_type, len(data), width, height)


def _run(command: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        timeout=timeout,
        shell=False,
    )


def probe_video(data: bytes, mime_type: str) -> MediaMetadata:
    if mime_type not in ALLOWED_VIDEOS:
        raise MediaValidationError(f"MIME video non consentito: {mime_type}")
    if len(data) > settings.MEDIA_VIDEO_MAX_BYTES:
        raise MediaValidationError("Video oltre il limite configurato.")
    suffix = {"video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov"}[mime_type]
    with tempfile.TemporaryDirectory(prefix="lavoro-media-") as directory:
        path = Path(directory) / f"input{suffix}"
        path.write_bytes(data)
        try:
            result = _run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration:stream=width,height,codec_type",
                    "-of",
                    "json",
                    str(path),
                ],
                timeout=30,
            )
            payload = json.loads(result.stdout)
        except (subprocess.SubprocessError, json.JSONDecodeError) as exc:
            raise MediaValidationError("Video non valido o non leggibile da FFmpeg.") from exc
    video_stream = next(
        (item for item in payload.get("streams", []) if item.get("codec_type") == "video"), None
    )
    if not video_stream:
        raise MediaValidationError("Il file non contiene uno stream video.")
    duration = float(payload.get("format", {}).get("duration") or 0)
    if duration <= 0 or duration > settings.MEDIA_VIDEO_MAX_SECONDS:
        raise MediaValidationError("Durata video non consentita.")
    return MediaMetadata(
        mime_type,
        len(data),
        int(video_stream.get("width") or 0),
        int(video_stream.get("height") or 0),
        duration,
    )


def remove_image_watermark(data: bytes, regions: list[dict]) -> bytes:
    import cv2
    import numpy as np

    source = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if source is None:
        raise MediaValidationError("Immagine non decodificabile per inpainting.")
    height, width = source.shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    for region in regions:
        x1, y1 = int(region["x"] * width), int(region["y"] * height)
        x2 = min(width, int((region["x"] + region["width"]) * width))
        y2 = min(height, int((region["y"] + region["height"]) * height))
        cv2.rectangle(mask, (x1, y1), (x2, y2), 255, thickness=-1)
    output = cv2.inpaint(source, mask, 3, cv2.INPAINT_TELEA)
    ok, encoded = cv2.imencode(".jpg", output, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise MediaValidationError("Impossibile codificare la variante senza watermark.")
    return encoded.tobytes()


def process_video(
    data: bytes, regions: list[dict] | None = None
) -> tuple[bytes, bytes, list[bytes]]:
    """Return browser MP4, JPEG thumbnail and five JPEG classification frames."""
    with tempfile.TemporaryDirectory(prefix="lavoro-video-") as directory:
        root = Path(directory)
        source, output, thumb = root / "input.bin", root / "display.mp4", root / "thumbnail.jpg"
        source.write_bytes(data)
        filters: list[str] = []
        for region in regions or []:
            # FFmpeg delogo accepts expressions based on input dimensions.
            filters.append(
                "delogo="
                f"x=iw*{region['x']}:y=ih*{region['y']}:"
                f"w=iw*{region['width']}:h=ih*{region['height']}"
            )
        filters.append(
            "scale=w='min(1280,iw)':h='min(720,ih)':force_original_aspect_ratio=decrease"
        )
        _run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                str(source),
                "-vf",
                ",".join(filters),
                "-c:v",
                "libx264",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(output),
            ]
        )
        probe = probe_video(output.read_bytes(), "video/mp4")
        seek = max(0.0, (probe.duration_seconds or 1) * 0.10)
        _run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-ss",
                str(seek),
                "-i",
                str(output),
                "-frames:v",
                "1",
                "-vf",
                "scale=640:640:force_original_aspect_ratio=decrease",
                str(thumb),
            ]
        )
        frames: list[bytes] = []
        for index, ratio in enumerate((0.1, 0.3, 0.5, 0.7, 0.9)):
            frame = root / f"frame-{index}.jpg"
            _run(
                [
                    "ffmpeg",
                    "-y",
                    "-v",
                    "error",
                    "-ss",
                    str((probe.duration_seconds or 1) * ratio),
                    "-i",
                    str(output),
                    "-frames:v",
                    "1",
                    str(frame),
                ]
            )
            frames.append(frame.read_bytes())
        return output.read_bytes(), thumb.read_bytes(), frames
