"""Least-recently-used proxy leasing and passive endpoint health."""

from __future__ import annotations

import ipaddress
import socket
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.proxies import ProxyEndpoint, ProxyPool, ProxyPoolMember
from app.services.proxy_credentials import decrypt_proxy_credentials


class ProxyPoolUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProxyRuntimeConfig:
    endpoint_id: uuid.UUID
    scheme: str
    host: str
    port: int
    username: str | None = None
    password: str | None = None

    def _authority_host(self) -> str:
        """Bracket IPv6 literals when they are used in a proxy URL."""
        return f"[{self.host}]" if ":" in self.host and not self.host.startswith("[") else self.host

    def scrapling_value(self) -> str | dict[str, str]:
        server = f"{self.scheme}://{self._authority_host()}:{self.port}"
        if self.username is None:
            return server
        return {"server": server, "username": self.username, "password": self.password or ""}

    def httpx_url(self) -> str:
        host = self._authority_host()
        if self.username is None:
            return f"{self.scheme}://{host}:{self.port}"
        user = quote(self.username, safe="")
        password = quote(self.password or "", safe="")
        return f"{self.scheme}://{user}:{password}@{host}:{self.port}"


@dataclass(frozen=True)
class ProxyRuntimeEvent:
    endpoint_id: uuid.UUID
    operation: str
    outcome: str
    latency_ms: int
    failure_category: str | None = None


def reserve_proxy_candidates(
    session: Session, pool_id: uuid.UUID, *, limit: int | None = None
) -> list[ProxyRuntimeConfig]:
    """Reserve healthy candidates atomically in least-recently-used order."""
    now = datetime.now(UTC)
    pool = session.get(ProxyPool, pool_id)
    if pool is None or not pool.enabled:
        raise ProxyPoolUnavailableError("Il pool proxy non e disponibile.")
    rows = (
        session.execute(
            select(ProxyEndpoint)
            .join(ProxyPoolMember, ProxyPoolMember.proxy_id == ProxyEndpoint.id)
            .where(
                ProxyPoolMember.pool_id == pool_id,
                ProxyEndpoint.enabled.is_(True),
                or_(ProxyEndpoint.cooldown_until.is_(None), ProxyEndpoint.cooldown_until <= now),
            )
            .order_by(ProxyEndpoint.last_used_at.asc().nullsfirst(), ProxyEndpoint.id.asc())
            .with_for_update(skip_locked=True)
        )
        .scalars()
        .all()
    )
    if not rows:
        raise ProxyPoolUnavailableError("Nessun proxy sano disponibile nel pool.")
    configs: list[ProxyRuntimeConfig] = []
    target_count = limit or settings.PROXY_MAX_ATTEMPTS
    for row in rows:
        # DNS is checked again at use time. This closes the window between
        # Admin validation and a later DNS rebind to a private destination.
        if not proxy_host_is_allowed(row.host):
            continue
        credentials = decrypt_proxy_credentials(row.credentials_encrypted)
        row.last_used_at = now
        session.add(row)
        configs.append(
            ProxyRuntimeConfig(
                endpoint_id=row.id,
                scheme=row.scheme,
                host=row.host,
                port=row.port,
                username=credentials[0] if credentials else None,
                password=credentials[1] if credentials else None,
            )
        )
        if len(configs) >= target_count:
            break
    if not configs:
        session.rollback()
        raise ProxyPoolUnavailableError("Nessun proxy con destinazione consentita nel pool.")
    session.commit()
    return configs


def apply_proxy_event(session: Session, event: ProxyRuntimeEvent) -> None:
    endpoint = session.get(ProxyEndpoint, event.endpoint_id)
    if endpoint is None:
        return
    now = datetime.now(UTC)
    if event.outcome == "success":
        endpoint.consecutive_failures = 0
        endpoint.cooldown_until = None
        endpoint.last_success_at = now
    else:
        endpoint.consecutive_failures += 1
        endpoint.last_failure_at = now
        steps = (5, 15, 30, 60)
        minutes = steps[min(endpoint.consecutive_failures - 1, len(steps) - 1)]
        endpoint.cooldown_until = now + timedelta(minutes=minutes)
    session.add(endpoint)


def proxy_host_is_allowed(host: str) -> bool:
    allowlist = {
        item.strip().lower()
        for item in settings.PROXY_PRIVATE_HOST_ALLOWLIST.split(",")
        if item.strip()
    }
    if host.lower() in allowlist:
        return True
    try:
        addresses = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    return bool(addresses) and all(ipaddress.ip_address(item[4][0]).is_global for item in addresses)
