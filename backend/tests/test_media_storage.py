"""Contratti dello storage MinIO e generazione sicura degli URL firmati."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from minio import Minio

from app.config import settings
from app.services.media_storage import presigned_download_url, presigned_media_url


def _forbid_network(*args, **kwargs):
    raise AssertionError("La generazione di un URL presigned non deve usare la rete.")


def _configure_presigning(monkeypatch) -> None:
    monkeypatch.setattr(settings, "MINIO_PUBLIC_ENDPOINT", "localhost:9000")
    monkeypatch.setattr(settings, "MINIO_ACCESS_KEY", "test-access-key")
    monkeypatch.setattr(settings, "MINIO_SECRET_KEY", "test-secret-key")
    monkeypatch.setattr(settings, "MINIO_BUCKET", "test-media")
    monkeypatch.setattr(settings, "MINIO_REGION", "eu-test-1")
    monkeypatch.setattr(settings, "MINIO_PRESIGNED_TTL_MINUTES", 12)
    monkeypatch.setattr(Minio, "_url_open", _forbid_network)


def _assert_presigned_url(url: str) -> dict[str, list[str]]:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "http"
    assert parsed.netloc == "localhost:9000"
    assert parsed.path == "/test-media/media/record/display.jpg"
    assert query["X-Amz-Expires"] == ["720"]
    assert "/eu-test-1/s3/aws4_request" in query["X-Amz-Credential"][0]
    assert "X-Amz-Signature" in query
    return query


def test_presigned_media_url_is_signed_locally(monkeypatch) -> None:
    _configure_presigning(monkeypatch)

    url = presigned_media_url("media/record/display.jpg")

    _assert_presigned_url(url)


def test_presigned_download_url_is_signed_locally(monkeypatch) -> None:
    _configure_presigning(monkeypatch)

    url = presigned_download_url("media/record/display.jpg", "export.zip")

    query = _assert_presigned_url(url)
    assert query["response-content-disposition"] == ['attachment; filename="export.zip"']
