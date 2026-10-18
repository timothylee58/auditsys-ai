"""Tenant isolation tests.

The two cross-tenant leak paths found in the audit:
  1. Answer cache keyed only by question text -> user B could receive
     user A's cached answer.
  2. Vector search RPC called without user_id -> matched chunks from
     every tenant's documents.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.rag_agent import retrieve_context
from app.core.redis_client import _cache_key, get_cached_answer, set_cached_answer


class TestCacheKeyScoping:
    def test_different_users_get_different_keys(self):
        key_a = _cache_key("What is the policy?", "user-a")
        key_b = _cache_key("What is the policy?", "user-b")
        assert key_a != key_b
        assert "user-a" in key_a
        assert "user-b" in key_b

    def test_same_user_same_question_is_stable(self):
        assert _cache_key("question", "user-a") == _cache_key("question", "user-a")

    def test_scope_includes_user_id_not_just_hash(self):
        key = _cache_key("question", "tenant-42")
        assert "tenant-42" in key


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}
        self.get_keys: list[str] = []

    async def get(self, key: str):
        self.get_keys.append(key)
        return self.store.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = value


@pytest.mark.asyncio
async def test_cached_answer_roundtrip_is_user_scoped(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr("app.core.redis_client.get_redis", lambda: fake)

    await set_cached_answer("policy question", "user-a", {"answer": "A's answer"})
    await set_cached_answer("policy question", "user-b", {"answer": "B's answer"})

    assert await get_cached_answer("policy question", "user-a") == {"answer": "A's answer"}
    assert await get_cached_answer("policy question", "user-b") == {"answer": "B's answer"}
    # ... and every read hit a key that embeds the caller's scope
    assert all("user-a" in k or "user-b" in k for k in fake.get_keys)


@pytest.mark.asyncio
async def test_retrieval_refuses_without_user_id():
    """No user in state -> no RPC call at all, empty context."""
    with patch("app.agents.rag_agent.get_supabase") as mock_get:
        state = await retrieve_context({"question": "What is the policy?"})

    assert state["context"]["chunks"] == []
    mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_retrieval_passes_user_id_to_rpc():
    """The RPC must receive the caller's user_id so Postgres scopes the match."""
    supabase = MagicMock()
    supabase.rpc.return_value.execute.return_value.data = [
        {"document_id": "doc-1", "content": "chunk text", "page_number": 3, "similarity": 0.9}
    ]

    with (
        patch("app.agents.rag_agent.get_supabase", return_value=supabase),
        patch("app.agents.rag_agent.get_embedding", new=AsyncMock(return_value=[0.1] * 8)),
    ):
        state = await retrieve_context(
            {"question": "What is the policy?", "user_id": "user-abc"}
        )

    assert len(state["context"]["chunks"]) == 1
    supabase.rpc.assert_called_once()
    rpc_name, rpc_params = supabase.rpc.call_args[0]
    assert rpc_name == "match_document_chunks"
    assert rpc_params["user_id"] == "user-abc"


@pytest.mark.asyncio
async def test_retrieval_failure_degrades_to_empty():
    supabase = MagicMock()
    supabase.rpc.return_value.execute.side_effect = RuntimeError("db down")

    with patch("app.agents.rag_agent.get_supabase", return_value=supabase):
        state = await retrieve_context(
            {"question": "What is the policy?", "user_id": "user-abc"}
        )

    assert state["context"]["chunks"] == []
