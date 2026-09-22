"""Reliable HMAC-signed webhook delivery with bounded retries."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import socket
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import httpx
from sqlalchemy import select

from app.models.integrations import ScrapeRunPayload, WebhookDelivery, WebhookEndpoint
from app.services.integration_crypto import decrypt_json
from app.workers.celery_app import celery_app
from app.workers.tasks_scraper import SyncSessionLocal

_DELAYS = (60, 300, 900, 3600, 14400)


def _safe_delivery_error(exc: Exception) -> str:
    """Map transport failures to bounded codes without persisting target URLs."""
    value = str(exc)
    if value.startswith("http_") and value[5:].isdigit():
        return value
    if value == "unsafe_target":
        return value
    return "delivery_failed"


def _public_https(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("unsafe_target")
    for result in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM):
        address = ipaddress.ip_address(result[4][0])
        if not address.is_global:
            raise ValueError("unsafe_target")


def _apply_phone_policy(payload: dict, policy: str) -> None:
    for item in payload.get("items", []):
        key = "phone_raw" if "phone_raw" in item else "phone"
        if key not in item:
            continue
        if policy == "excluded":
            item.pop(key, None)
        elif policy == "masked":
            digits = "".join(char for char in str(item[key]) if char.isdigit())
            item[key] = f"***{digits[-4:]}" if digits else "***"


@celery_app.task(name="app.workers.tasks_webhooks.deliver_webhook", bind=True, max_retries=5)
def deliver_webhook(self, delivery_id: str) -> dict:
    session = SyncSessionLocal()
    delivery_uuid = uuid.UUID(delivery_id)
    try:
        delivery = session.get(WebhookDelivery, delivery_uuid)
        if delivery is None or delivery.status == "succeeded":
            return {"status": "ignored"}
        endpoint = session.get(WebhookEndpoint, delivery.endpoint_id)
        payload_row = session.execute(
            select(ScrapeRunPayload).where(ScrapeRunPayload.scrape_run_id == delivery.scrape_run_id)
        ).scalar_one()
        if endpoint is None or not endpoint.enabled:
            delivery.status, delivery.last_error = "failed", "endpoint_disabled"
            session.commit()
            return {"status": "failed"}
        payload = decrypt_json(payload_row.payload_encrypted)
        _apply_phone_policy(payload, endpoint.phone_policy)
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        timestamp = str(int(datetime.now(UTC).timestamp()))
        headers = {
            "Content-Type": "application/json",
            "X-Lavoro-Esterno-Timestamp": timestamp,
            "X-Lavoro-Esterno-Event-Id": payload["eventId"],
        }
        if endpoint.secret_encrypted:
            secret = decrypt_json(endpoint.secret_encrypted)["secret"].encode()
            signature = hmac.new(
                secret, timestamp.encode() + b"." + body, hashlib.sha256
            ).hexdigest()
            headers["X-Lavoro-Esterno-Signature"] = f"sha256={signature}"
        _public_https(endpoint.url)
        delivery.status = "sending"
        delivery.attempts += 1
        session.commit()
        with httpx.Client(follow_redirects=False, timeout=15) as client:
            with client.stream("POST", endpoint.url, content=body, headers=headers) as response:
                status_code = response.status_code
        delivery = session.get(WebhookDelivery, delivery_uuid)
        delivery.last_http_status = status_code
        if 200 <= status_code < 300:
            delivery.status, delivery.delivered_at, delivery.next_attempt_at = (
                "succeeded",
                datetime.now(UTC),
                None,
            )
            session.commit()
            return {"status": "succeeded"}
        raise RuntimeError(f"http_{status_code}")
    except Exception as exc:
        session.rollback()
        delivery = session.get(WebhookDelivery, delivery_uuid)
        if delivery is None:
            return {"status": "failed"}
        delivery.attempts += 1 if delivery.status != "sending" else 0
        delivery.last_error = _safe_delivery_error(exc)
        if self.request.retries < self.max_retries:
            delay = _DELAYS[min(self.request.retries, len(_DELAYS) - 1)]
            delivery.status = "pending"
            delivery.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay)
            session.commit()
            raise self.retry(exc=exc, countdown=delay) from exc
        delivery.status, delivery.next_attempt_at = "failed", None
        session.commit()
        return {"status": "failed"}
    finally:
        session.close()
