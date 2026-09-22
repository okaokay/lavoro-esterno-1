"""Selezione, cooldown, fail-closed e sicurezza della rotazione proxy."""

from __future__ import annotations

import asyncio
import base64
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import settings
from app.models.proxies import ProxyEndpoint, ProxyPool, ProxyPoolMember
from app.schemas.proxies import ProxyEndpointCreate, ProxyEndpointUpdate
from app.scrapers.generic import GenericScraper, ProxyPoolExhaustedError
from app.services.proxy_credentials import decrypt_proxy_credentials, encrypt_proxy_credentials
from app.services.proxy_rotation import ProxyRuntimeConfig, reserve_proxy_candidates


def _config() -> dict:
    return {
        "start_urls": ["https://example.test/list"],
        "ad_link_selector": "a.ad",
        "rate_limit_seconds": 1,
        "fields": {"phone": {"selector": ".phone", "attribute": "text"}},
    }


def _runtime(port: int) -> ProxyRuntimeConfig:
    return ProxyRuntimeConfig(uuid.uuid4(), "http", "proxy.example", port)


def test_proxy_credentials_round_trip_without_exposure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings,
        "PROXY_CREDENTIAL_ENCRYPTION_KEY",
        base64.b64encode(b"p" * 32).decode(),
    )
    encrypted = encrypt_proxy_credentials("alice", "secret")
    assert b"alice" not in encrypted
    assert b"secret" not in encrypted
    assert decrypt_proxy_credentials(encrypted) == ("alice", "secret")


def test_proxy_credentials_must_be_supplied_as_pair() -> None:
    with pytest.raises(ValidationError):
        ProxyEndpointCreate(
            name="one", scheme="http", host="proxy.example", port=8080, username="alice"
        )
    with pytest.raises(ValidationError):
        ProxyEndpointUpdate(username="alice", password="secret", clear_credential=True)


@pytest.mark.asyncio
async def test_rotates_on_transport_error_and_keeps_successful_proxy() -> None:
    first, second = _runtime(8001), _runtime(8002)
    scraper = GenericScraper("test", "https://example.test", _config(), [first, second])

    async def operation() -> str:
        if scraper._active_proxy() == first:
            raise httpx.ConnectError("unavailable")
        return "ok"

    assert await scraper._with_proxy_rotation("page", operation) == "ok"
    assert [event.outcome for event in scraper.proxy_events] == ["failed", "success"]
    assert scraper._active_proxy() == second


@pytest.mark.asyncio
async def test_proxy_rotation_closes_browser_session_before_recreation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, second = _runtime(8001), _runtime(8002)
    sessions: list[object] = []

    class FakeSession:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.closed = False
            sessions.append(self)

        async def start(self) -> None:
            return None

        async def close(self) -> None:
            self.closed = True

    monkeypatch.setattr("scrapling.fetchers.AsyncStealthySession", FakeSession)
    scraper = GenericScraper(
        "test",
        "https://example.test",
        {**_config(), "fetch_mode": "stealth"},
        [first, second],
    )

    original = await scraper._ensure_browser_session()
    assert await scraper._rotate_proxy() is True
    replacement = await scraper._ensure_browser_session()

    assert original.closed is True
    assert replacement is not original
    assert len(sessions) == 2
    assert sessions[0].kwargs["proxy"] == first.scrapling_value()
    assert sessions[1].kwargs["proxy"] == second.scrapling_value()


@pytest.mark.asyncio
async def test_proxy_pool_is_fail_closed_after_last_candidate() -> None:
    scraper = GenericScraper("test", "https://example.test", _config(), [_runtime(8001)])

    async def operation() -> None:
        raise httpx.ConnectError("unavailable")

    with pytest.raises(ProxyPoolExhaustedError):
        await scraper._with_proxy_rotation("media", operation)
    assert len(scraper.proxy_events) == 1
    assert scraper.proxy_events[0].failure_category == "network"


def test_lru_reservation_excludes_disabled_and_cooldown(monkeypatch) -> None:
    monkeypatch.setattr("app.services.proxy_rotation.proxy_host_is_allowed", lambda _host: True)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ProxyPool.__table__.create(engine)
    ProxyEndpoint.__table__.create(engine)
    ProxyPoolMember.__table__.create(engine)
    now = datetime.now(UTC)
    with Session(engine, expire_on_commit=False) as session:
        pool = ProxyPool(name="main")
        oldest = ProxyEndpoint(
            name="oldest",
            scheme="http",
            host="one.example",
            port=8001,
            last_used_at=now - timedelta(hours=2),
        )
        recent = ProxyEndpoint(
            name="recent",
            scheme="http",
            host="two.example",
            port=8002,
            last_used_at=now - timedelta(hours=1),
        )
        cooling = ProxyEndpoint(
            name="cooling",
            scheme="http",
            host="three.example",
            port=8003,
            cooldown_until=now + timedelta(minutes=5),
        )
        disabled = ProxyEndpoint(
            name="disabled", scheme="http", host="four.example", port=8004, enabled=False
        )
        session.add_all([pool, oldest, recent, cooling, disabled])
        session.flush()
        session.add_all(
            [
                ProxyPoolMember(pool_id=pool.id, proxy_id=item.id)
                for item in (oldest, recent, cooling, disabled)
            ]
        )
        session.commit()

        selected = reserve_proxy_candidates(session, pool.id, limit=3)

    assert [item.endpoint_id for item in selected] == [oldest.id, recent.id]


def test_runtime_formats_credentials_for_browser_and_httpx() -> None:
    runtime = ProxyRuntimeConfig(uuid.uuid4(), "socks5", "proxy.example", 1080, "a b", "p@ss")
    assert runtime.scrapling_value() == {
        "server": "socks5://proxy.example:1080",
        "username": "a b",
        "password": "p@ss",
    }
    assert runtime.httpx_url() == "socks5://a%20b:p%40ss@proxy.example:1080"


def test_runtime_brackets_ipv6_literal() -> None:
    runtime = ProxyRuntimeConfig(uuid.uuid4(), "socks4", "2001:4860:4860::8888", 1080)
    assert runtime.httpx_url() == "socks4://[2001:4860:4860::8888]:1080"
    assert runtime.scrapling_value() == "socks4://[2001:4860:4860::8888]:1080"


def test_proxy_http_throttling_is_retryable() -> None:
    response = httpx.Response(429, request=httpx.Request("GET", "https://example.test"))
    error = httpx.HTTPStatusError("throttled", request=response.request, response=response)
    assert GenericScraper._proxy_failure_category(error) == "http_429"


@pytest.mark.asyncio
async def test_media_request_really_traverses_configured_http_proxy() -> None:
    request_seen = asyncio.Event()

    async def proxy_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readuntil(b"\r\n\r\n")
        request_seen.set()
        body = b"proxy-ok"
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\n"
            + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
            + body
        )
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(proxy_handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    scraper = GenericScraper(
        "test",
        "http://127.0.0.1",
        _config(),
        [ProxyRuntimeConfig(uuid.uuid4(), "http", "127.0.0.1", port)],
    )
    try:
        body = await scraper._download_media_stream("http://127.0.0.1:9/media.bin")
    finally:
        server.close()
        await server.wait_closed()
    assert body == b"proxy-ok"
    assert request_seen.is_set()
