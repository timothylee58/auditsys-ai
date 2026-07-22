"""Redis async client with semantic cache support.

Supports TLS connections for Azure Cache for Redis (rediss:// scheme).
Provides semantic caching helpers for query answers with 1-hour TTL.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache

import redis.asyncio as aioredis
from loguru import logger

from app.config import settings

# Cache key prefix
_CACHE_PREFIX = "auditsys:cache"
_CACHE_TTL_SECONDS = 3600  # 1 hour


@lru_cache
def get_redis() -> aioredis.Redis:
    """Return a cached async Redis client singleton.

    Supports both plain Redis (redis://) and TLS (rediss://) for
    Azure Cache for Redis.
    """
    url = settings.redis_url
    use_tls = url.startswith("rediss://")

    client = aioredis.from_url(
        url,
        decode_responses=True,
        ssl=use_tls,
        ssl_cert_reqs="required" if use_tls else None,
    )
    logger.info(
        "redis_client_initialized tls={} url={}",
        use_tls,
        url[:30] + "..." if len(url) > 30 else url,
    )
    return client


def _make_cache_key(query_text: str) -> str:
    """Generate a deterministic cache key from query text."""
    query_hash = hashlib.sha256(query_text.strip().lower().encode()).hexdigest()[:32]
    return f"{_CACHE_PREFIX}:{query_hash}"


async def get_cached_answer(query_text: str) -> dict | None:
    """Retrieve a cached answer for the given query.

    Args:
        query_text: The user's original question.

    Returns:
        Cached response dict if found, None otherwise.
    """
    try:
        client = get_redis()
        key = _make_cache_key(query_text)
        raw = await client.get(key)
        if raw:
            logger.debug("cache_hit key={}", key)
            return json.loads(raw)
    except Exception as exc:
        logger.warning("cache_get_failed error={}", str(exc))
    return None


async def set_cached_answer(query_text: str, response_data: dict) -> None:
    """Cache an answer with the configured TTL.

    Args:
        query_text: The user's original question (used to derive key).
        response_data: The full response dict to cache.
    """
    try:
        client = get_redis()
        key = _make_cache_key(query_text)
        await client.setex(key, _CACHE_TTL_SECONDS, json.dumps(response_data))
        logger.debug("cache_set key={} ttl={}", key, _CACHE_TTL_SECONDS)
    except Exception as exc:
        logger.warning("cache_set_failed error={}", str(exc))


async def invalidate_cache(query_text: str) -> None:
    """Remove a specific cached answer."""
    try:
        client = get_redis()
        key = _make_cache_key(query_text)
        await client.delete(key)
        logger.debug("cache_invalidated key={}", key)
    except Exception as exc:
        logger.warning("cache_invalidate_failed error={}", str(exc))
