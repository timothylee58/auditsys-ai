"""Rate limiter tests: fixed-window counting, 429 enforcement, fail-open."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.rate_limit import enforce_rate_limit


class FakeRedis:
    """Minimal async Redis double with real counter semantics."""

    def __init__(self, *, should_fail: bool = False):
        self.counters: dict[str, int] = {}
        self.expiries: dict[str, int] = {}
        self.should_fail = should_fail

    async def incr(self, key: str) -> int:
        if self.should_fail:
            raise RuntimeError("redis unavailable")
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def expire(self, key: str, seconds: int) -> None:
        self.expiries[key] = seconds


def _request(host: str | None = None) -> SimpleNamespace:
    """Stub Starlette request: only headers and client are consulted."""
    client = SimpleNamespace(host=host) if host else None
    return SimpleNamespace(headers={}, client=client)


@pytest.mark.asyncio
async def test_under_limit_passes(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr("app.core.rate_limit.get_redis", lambda: fake)

    request = _request()
    await enforce_rate_limit(request, "user-1", "query", limit=3)
    await enforce_rate_limit(request, "user-1", "query", limit=3)
    assert fake.counters  # counters were actually used


@pytest.mark.asyncio
async def test_over_limit_raises_429(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr("app.core.rate_limit.get_redis", lambda: fake)

    request = _request()
    for _ in range(2):
        await enforce_rate_limit(request, "user-1", "query", limit=2)

    with pytest.raises(HTTPException) as exc_info:
        await enforce_rate_limit(request, "user-1", "query", limit=2)
    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_different_users_counted_separately(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr("app.core.rate_limit.get_redis", lambda: fake)

    request = _request()
    await enforce_rate_limit(request, "user-1", "query", limit=1)
    # user-2 has their own bucket — not limited by user-1's usage.
    await enforce_rate_limit(request, "user-2", "query", limit=1)
    assert len(fake.counters) == 2


@pytest.mark.asyncio
async def test_fails_open_when_redis_unavailable(monkeypatch):
    """Redis outage must not take the API down — the limiter is best-effort."""
    fake = FakeRedis(should_fail=True)
    monkeypatch.setattr("app.core.rate_limit.get_redis", lambda: fake)

    # Should NOT raise, even though every incr fails.
    await enforce_rate_limit(_request(), "user-1", "query", limit=1)


@pytest.mark.asyncio
async def test_falls_back_to_client_ip(monkeypatch):
    """Anonymous callers (no user id) are keyed by IP, not shared globally."""
    fake = FakeRedis()
    monkeypatch.setattr("app.core.rate_limit.get_redis", lambda: fake)

    await enforce_rate_limit(_request(host="203.0.113.7"), None, "query", limit=1)
    assert any("203.0.113.7" in key for key in fake.counters)
