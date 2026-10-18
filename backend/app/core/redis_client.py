import hashlib
import json
from functools import lru_cache

import redis.asyncio as aioredis

from app.core.settings import settings

CACHE_PREFIX = "auditsys:cache:"
CACHE_TTL_SECONDS = 3600  # 1 hour


@lru_cache
def get_redis() -> aioredis.Redis:
    # redis-py infers TLS from the scheme: rediss:// (Azure Cache for Redis
    # in production) negotiates TLS automatically; redis:// (local dev)
    # does not. No branching needed here.
    return aioredis.from_url(settings.redis_url, decode_responses=True)


def _cache_key(query: str, user_id: str | None = None) -> str:
    """Build the cache key for a question.

    The key is always scoped to the caller: answers may differ per tenant
    (documents are user-scoped), so sharing an entry across users would
    leak one tenant's data into another's session.
    """
    query_hash = hashlib.sha256(query.strip().lower().encode()).hexdigest()
    scope = user_id or "anonymous"
    return f"{CACHE_PREFIX}{scope}:{query_hash}"


async def get_cached_answer(query: str, user_id: str | None = None) -> dict | None:
    """Look up a previously-cached answer for this question AND caller."""
    redis = get_redis()
    key = _cache_key(query, user_id)
    cached = await redis.get(key)
    return json.loads(cached) if cached else None


async def set_cached_answer(query: str, user_id: str | None, answer: dict) -> None:
    """Cache an answer payload for CACHE_TTL_SECONDS, scoped to the caller."""
    redis = get_redis()
    key = _cache_key(query, user_id)
    await redis.setex(key, CACHE_TTL_SECONDS, json.dumps(answer))
