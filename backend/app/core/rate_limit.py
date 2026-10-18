"""Redis-backed fixed-window rate limiting.

Applied to expensive or abuse-prone endpoints (POST /query burns Azure
OpenAI tokens; POST /documents/upload burns embedding tokens and storage).

Design notes:
  - Counters are keyed per user id (falling back to client IP) inside a
    fixed window, stored in Redis so limits hold across workers.
  - Fail-open on Redis unavailability: the limiter is a guardrail, not a
    hard dependency — losing it must not take the API down. Pair it with
    infrastructure-level limits (Azure Container Apps, WAF) in production.
"""

from __future__ import annotations

import time

from fastapi import Depends, HTTPException, Request, status

from app.core.auth import CurrentUser, get_current_user
from app.core.redis_client import get_redis

_COUNTER_PREFIX = "auditsys:ratelimit:"


def client_ip(request: Request) -> str:
    """Best-effort client IP; prefers the first X-Forwarded-For hop set by
    the ingress/proxy in front of the API."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def enforce_rate_limit(
    request: Request,
    user_id: str | None,
    bucket: str,
    limit: int,
    window_seconds: int = 60,
) -> None:
    """Increment the counter for (bucket, identity, window) and raise 429
    when it exceeds ``limit``."""
    identity = user_id or client_ip(request)
    window = int(time.time() // window_seconds)
    key = f"{_COUNTER_PREFIX}{bucket}:{identity}:{window}"

    try:
        redis = get_redis()
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, window_seconds + 1)
    except Exception:  # noqa: BLE001 - fail open when Redis is unavailable
        return

    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded — slow down and retry shortly",
        )


def rate_limited(bucket: str, limit: int, window_seconds: int = 60):
    """FastAPI dependency factory: authenticate, then rate-limit the caller.

    Usage: ``user: CurrentUser = Depends(rate_limited("query", 30))``
    """

    async def dependency(
        request: Request,
        user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        await enforce_rate_limit(request, user.user_id, bucket, limit, window_seconds)
        return user

    return dependency
