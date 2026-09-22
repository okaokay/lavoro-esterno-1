"""Upload dei media scaricati durante lo scraping su MinIO/S3.

Prima pipeline del progetto che scrive DAVVERO su MinIO (finora il client
MinIO era usato solo per rimuovere oggetti scaduti, vedi
`app/workers/tasks_maintenance.py`): qui creiamo anche il bucket se non
esiste ancora, dato che nessun altro punto del codice lo fa.
"""

from __future__ import annotations

import io
import uuid
from datetime import timedelta

from minio import Minio

from app.config import settings

# Firme "magic bytes" per i formati immagine più comuni: evitiamo il modulo
# `imghdr` della stdlib (rimosso in Python 3.13) e non abbiamo l'URL
# originale a disposizione qui per un guess-by-extension affidabile.
_MAGIC_BYTES: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"\x1aE\xdf\xa3", "video/webm"),
]


def sniff_mime_type(data: bytes) -> str:
    """Indovina il MIME type dai byte del file. Fallback generico se nessuna
    firma nota corrisponde: meglio un MIME type onesto ma poco specifico che
    una diagnosi sbagliata sul contenuto."""
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12]
        return "video/quicktime" if brand == b"qt  " else "video/mp4"
    for signature, mime_type in _MAGIC_BYTES:
        if data.startswith(signature):
            return mime_type
    return "application/octet-stream"


_EXTENSION_BY_MIME = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
    "video/mp4": "mp4",
    "video/webm": "webm",
    "video/quicktime": "mov",
}


def _client() -> Minio:
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
        region=settings.MINIO_REGION,
    )


def _public_client() -> Minio:
    endpoint = settings.MINIO_PUBLIC_ENDPOINT or settings.MINIO_ENDPOINT
    secure = settings.MINIO_SECURE
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        secure = endpoint.startswith("https://")
        endpoint = endpoint.split("://", 1)[1]
    return Minio(
        endpoint,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=secure,
        # Senza una regione esplicita il client prova GetBucketLocation
        # sull'endpoint pubblico. Dentro Docker, "localhost" identifica il
        # container API e non MinIO: la firma deve quindi essere interamente
        # locale e usare la stessa regione configurata sul server.
        region=settings.MINIO_REGION,
    )


def _ensure_bucket(client: Minio) -> None:
    if not client.bucket_exists(settings.MINIO_BUCKET):
        client.make_bucket(settings.MINIO_BUCKET)


def upload_media_object(record_id: uuid.UUID, data: bytes, mime_type: str) -> str:
    """Carica un media originale scaricato durante lo scraping, seguendo la
    convenzione di path documentata in `docs/DATABASE.md`:
    `media/{record_uuid}/{media_uuid}/original.<ext>`. Restituisce
    l'`object_key` da salvare in `media.original_object_key`.
    """
    client = _client()
    _ensure_bucket(client)

    extension = _EXTENSION_BY_MIME.get(mime_type, "bin")
    media_id = uuid.uuid4()
    object_key = f"media/{record_id}/{media_id}/original.{extension}"

    client.put_object(
        settings.MINIO_BUCKET,
        object_key,
        io.BytesIO(data),
        length=len(data),
        content_type=mime_type,
    )
    return object_key


def put_object_bytes(object_key: str, data: bytes, mime_type: str) -> str:
    client = _client()
    _ensure_bucket(client)
    client.put_object(
        settings.MINIO_BUCKET,
        object_key,
        io.BytesIO(data),
        length=len(data),
        content_type=mime_type,
    )
    return object_key


def get_object_bytes(object_key: str) -> bytes:
    response = _client().get_object(settings.MINIO_BUCKET, object_key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def remove_object(object_key: str) -> None:
    _client().remove_object(settings.MINIO_BUCKET, object_key)


def upload_file(object_key: str, path: str, content_type: str) -> str:
    client = _client()
    _ensure_bucket(client)
    client.fput_object(settings.MINIO_BUCKET, object_key, path, content_type=content_type)
    return object_key


def download_object_to_file(object_key: str, path: str) -> None:
    _client().fget_object(settings.MINIO_BUCKET, object_key, path)


def list_objects(prefix: str):
    return _client().list_objects(settings.MINIO_BUCKET, prefix=prefix, recursive=True)


def presigned_media_url(object_key: str | None) -> str:
    if not object_key:
        return ""
    return _public_client().presigned_get_object(
        settings.MINIO_BUCKET,
        object_key,
        expires=timedelta(minutes=settings.MINIO_PRESIGNED_TTL_MINUTES),
    )


def presigned_download_url(object_key: str, filename: str) -> str:
    return _public_client().presigned_get_object(
        settings.MINIO_BUCKET,
        object_key,
        expires=timedelta(minutes=settings.MINIO_PRESIGNED_TTL_MINUTES),
        response_headers={"response-content-disposition": f'attachment; filename="{filename}"'},
    )
