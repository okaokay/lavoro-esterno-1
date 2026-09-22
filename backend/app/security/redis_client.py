"""Client Redis condiviso per blacklist dei JWT e rate limiting/lockout.

Riusa lo stesso `REDIS_URL` già configurato per il broker/backend Celery
(vedi docker-compose.yml: il servizio `redis` è già presente e raggiungibile
da `api`): non serve nuova infrastruttura. Tutte le chiavi usate qui hanno il
prefisso `auth:` per restare logicamente separate dalle chiavi broker di
Celery sullo stesso database Redis.
"""

from __future__ import annotations

from functools import lru_cache

import redis.asyncio as redis

from app.config import settings

_KEY_PREFIX = "auth:"


@lru_cache
def get_redis() -> redis.Redis:
    """Client Redis async cacheato (una sola connection pool per processo)."""
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def _key(*parts: str) -> str:
    return _KEY_PREFIX + ":".join(parts)


async def blacklist_jti(jti: str, ttl_seconds: int) -> None:
    """Mette in blacklist un token specifico (logout) per il tempo residuo
    alla sua scadenza naturale: dopo quel tempo il JWT sarebbe comunque
    invalido per `exp`, quindi non serve tenerlo in blacklist più a lungo."""
    if ttl_seconds <= 0:
        return
    client = get_redis()
    await client.setex(_key("blacklist", jti), ttl_seconds, "1")


async def is_jti_blacklisted(jti: str) -> bool:
    client = get_redis()
    return bool(await client.exists(_key("blacklist", jti)))


async def register_failed_attempt(key: str, max_attempts: int, lockout_seconds: int) -> int | None:
    """Incrementa il contatore di tentativi falliti per `key` (email o user
    id). Alla prima registrazione imposta una scadenza pari alla finestra di
    lockout, così il contatore si azzera da solo passato quel tempo anche
    senza un login riuscito. Ritorna i secondi di lockout rimanenti se la
    soglia `max_attempts` è stata superata, altrimenti `None`."""
    client = get_redis()
    redis_key = _key("attempts", key)
    count = await client.incr(redis_key)
    if count == 1:
        await client.expire(redis_key, lockout_seconds)

    if count >= max_attempts:
        lock_key = _key("lockout", key)
        await client.setex(lock_key, lockout_seconds, "1")
        ttl = await client.ttl(lock_key)
        return ttl if ttl and ttl > 0 else lockout_seconds
    return None


async def is_locked_out(key: str) -> int | None:
    """Ritorna i secondi di lockout rimanenti per `key`, o `None` se non è
    (più) bloccata."""
    client = get_redis()
    ttl = await client.ttl(_key("lockout", key))
    return ttl if ttl and ttl > 0 else None


async def clear_attempts(key: str) -> None:
    """Azzera contatore tentativi e lockout per `key` (chiamato su login
    riuscito)."""
    client = get_redis()
    await client.delete(_key("attempts", key), _key("lockout", key))
