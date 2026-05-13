"""
Redis-backed query-result cache.

When Redis is unreachable (not installed, not running, or wrong URL) the cache
silently no-ops — every call is a miss and nothing is stored.  The RAG service
continues to function correctly without it.

Cache key = SHA-256( JSON(query + filters + top_k) )
TTL        = configurable (default 3 600 s = 1 hour)
"""

import hashlib
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_client = None
_available: Optional[bool] = None   # None = not yet probed


def _get_client(redis_url: str):
    global _client, _available
    if _available is not None:
        return _client
    try:
        import redis.asyncio as aioredis  # type: ignore
        _client = aioredis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
        )
        _available = True
        logger.info(f"Redis cache connected: {redis_url}")
    except ImportError:
        _available = False
        logger.warning(
            "redis package not installed — query caching disabled. "
            "Install with: pip install redis"
        )
    except Exception as e:
        _available = False
        logger.warning(f"Redis unavailable — caching disabled: {e}")
    return _client


def _cache_key(query: str, filters: dict, top_k: int) -> str:
    payload = json.dumps({"q": query, "f": filters, "k": top_k}, sort_keys=True)
    return "scrag:" + hashlib.sha256(payload.encode()).hexdigest()


async def get_cached(
    redis_url: str, query: str, filters: dict, top_k: int
) -> Optional[dict]:
    """Return a previously cached result dict, or None on miss / unavailability."""
    client = _get_client(redis_url)
    if not client:
        return None
    try:
        value = await client.get(_cache_key(query, filters, top_k))
        if value:
            logger.debug("Cache HIT")
            return json.loads(value)
    except Exception as e:
        logger.warning(f"Cache read error: {e}")
    return None


async def set_cached(
    redis_url: str,
    query: str,
    filters: dict,
    top_k: int,
    result: dict,
    ttl: int,
) -> None:
    """Store a result dict in cache with the given TTL (seconds)."""
    client = _get_client(redis_url)
    if not client:
        return
    try:
        await client.setex(
            _cache_key(query, filters, top_k),
            ttl,
            json.dumps(result),
        )
        logger.debug("Cache SET")
    except Exception as e:
        logger.warning(f"Cache write error: {e}")


async def invalidate_all(redis_url: str) -> int:
    """Delete all cache keys for this service. Returns number of keys deleted."""
    client = _get_client(redis_url)
    if not client:
        return 0
    try:
        keys = await client.keys("scrag:*")
        if keys:
            return await client.delete(*keys)
        return 0
    except Exception as e:
        logger.warning(f"Cache invalidation error: {e}")
        return 0
