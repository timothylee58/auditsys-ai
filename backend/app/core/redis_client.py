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


def _cache_key(query: str) -> str:
    query_hash = hashlib.sha256(query.strip().lower().encode()).hexdigest()
    return f"{CACHE_PREFIX}{query_hash}"


async def get_cached_answer(query_hash: str) -> dict | None:
    """Look up a previously-cached answer by raw query text or its hash key."""
    redis = get_redis()
    key = query_hash if query_hash.startswith(CACHE_PREFIX) else _cache_key(query_hash)
    cached = await redis.get(key)
    return json.loads(cached) if cached else None


async def set_cached_answer(query_hash: str, answer: dict) -> None:
    """Cache an answer payload for CACHE_TTL_SECONDS, keyed by query text or hash key."""
    redis = get_redis()
    key = query_hash if query_hash.startswith(CACHE_PREFIX) else _cache_key(query_hash)
    await redis.setex(key, CACHE_TTL_SECONDS, json.dumps(answer))
