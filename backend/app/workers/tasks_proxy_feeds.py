"""Safe manual and periodic synchronization of remote proxy feeds."""

from __future__ import annotations

import ipaddress
import socket
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import httpx
from sqlalchemy import delete, select

from app.models.proxies import ProxyEndpoint, ProxyFeed, ProxyPoolMember
from app.services.integration_crypto import decrypt_json
from app.services.proxy_credentials import encrypt_proxy_credentials
from app.services.proxy_rotation import proxy_host_is_allowed
from app.workers.celery_app import celery_app
from app.workers.tasks_scraper import SyncSessionLocal

_MAX_BYTES = 5 * 1024 * 1024
_MAX_LINES = 50_000


def _safe_sync_error(exc: Exception) -> str:
    """Return an operator-friendly code without leaking feed URLs or headers."""
    allowed = {
        "unsafe_feed_url",
        "feed_too_large",
        "too_many_lines",
        "no_valid_proxies",
    }
    value = str(exc)
    return value if value in allowed else "feed_download_failed"


def _validate_feed_target(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("unsafe_feed_url")
    for result in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(result[4][0]).is_global:
            raise ValueError("unsafe_feed_url")


def _download(feed: ProxyFeed) -> str:
    _validate_feed_target(feed.url)
    headers = decrypt_json(feed.headers_encrypted) if feed.headers_encrypted else {}
    with httpx.Client(follow_redirects=False, timeout=30) as client:
        with client.stream("GET", feed.url, headers=headers) as response:
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > _MAX_BYTES:
                    raise ValueError("feed_too_large")
                chunks.append(chunk)
    return b"".join(chunks).decode("utf-8")


@celery_app.task(name="app.workers.tasks_proxy_feeds.sync_proxy_feed_task")
def sync_proxy_feed_task(feed_id: str) -> dict:
    session = SyncSessionLocal()
    now = datetime.now(UTC)
    try:
        feed = session.get(ProxyFeed, uuid.UUID(feed_id))
        if feed is None or not feed.enabled:
            return {"status": "ignored"}
        text = _download(feed)
        lines = text.splitlines()
        if len(lines) > _MAX_LINES:
            raise ValueError("too_many_lines")
        parsed: dict[tuple[str, int], tuple[str, str]] = {}
        invalid = 0
        for line in lines:
            value = line.strip()
            if not value or value.startswith("#"):
                continue
            parts = value.split(":")
            if len(parts) != 4:
                invalid += 1
                continue
            host, port_raw, username, password = parts
            try:
                port = int(port_raw)
            except ValueError:
                invalid += 1
                continue
            if (
                not username
                or not password
                or not 1 <= port <= 65535
                or not proxy_host_is_allowed(host)
            ):
                invalid += 1
                continue
            parsed[(host, port)] = (username, password)
        if not parsed:
            raise ValueError("no_valid_proxies")
        existing = (
            session.execute(
                select(ProxyEndpoint).where(ProxyEndpoint.managed_by_feed_id == feed.id)
            )
            .scalars()
            .all()
        )
        by_key = {(item.host, item.port): item for item in existing}
        active_ids: list[uuid.UUID] = []
        for (host, port), credentials in parsed.items():
            endpoint = by_key.get((host, port))
            if endpoint is None:
                endpoint = ProxyEndpoint(
                    name=f"feed-{str(feed.id)[:8]}-{host}-{port}"[:120],
                    scheme=feed.scheme,
                    host=host,
                    port=port,
                    managed_by_feed_id=feed.id,
                )
                session.add(endpoint)
                session.flush()
            endpoint.scheme = feed.scheme
            endpoint.credentials_encrypted = encrypt_proxy_credentials(*credentials)
            endpoint.enabled = True
            active_ids.append(endpoint.id)
        for endpoint in existing:
            if endpoint.id not in active_ids:
                endpoint.enabled = False
        managed_ids = [item.id for item in existing] + [
            item for item in active_ids if item not in {row.id for row in existing}
        ]
        if managed_ids:
            session.execute(
                delete(ProxyPoolMember).where(
                    ProxyPoolMember.pool_id == feed.pool_id,
                    ProxyPoolMember.proxy_id.in_(managed_ids),
                )
            )
        session.add_all(
            [ProxyPoolMember(pool_id=feed.pool_id, proxy_id=item) for item in active_ids]
        )
        feed.last_synced_at, feed.last_sync_status = now, "success"
        feed.last_sync_message = f"{len(active_ids)} proxy attivi; {invalid} righe ignorate."
        feed.last_imported_count = len(active_ids)
        feed.next_sync_at = now + timedelta(minutes=feed.sync_interval_minutes)
        session.commit()
        return {"status": "success", "imported": len(active_ids), "invalid": invalid}
    except Exception as exc:
        session.rollback()
        feed = session.get(ProxyFeed, uuid.UUID(feed_id))
        if feed:
            feed.last_synced_at, feed.last_sync_status = now, "failed"
            feed.last_sync_message = _safe_sync_error(exc)
            feed.next_sync_at = now + timedelta(minutes=feed.sync_interval_minutes)
            session.commit()
        return {"status": "failed"}
    finally:
        session.close()


@celery_app.task(name="app.workers.tasks_proxy_feeds.dispatch_due_proxy_feeds")
def dispatch_due_proxy_feeds() -> dict:
    session = SyncSessionLocal()
    try:
        now = datetime.now(UTC)
        ids = list(
            session.execute(
                select(ProxyFeed.id)
                .where(ProxyFeed.enabled.is_(True), ProxyFeed.next_sync_at <= now)
                .limit(100)
            )
            .scalars()
            .all()
        )
        for feed_id in ids:
            feed = session.get(ProxyFeed, feed_id)
            feed.next_sync_at = now + timedelta(minutes=feed.sync_interval_minutes)
        session.commit()
        for feed_id in ids:
            sync_proxy_feed_task.delay(str(feed_id))
        return {"published": len(ids)}
    finally:
        session.close()
