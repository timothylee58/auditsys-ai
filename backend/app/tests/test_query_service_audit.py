"""query_service with AUDIT_GRADE_PIPELINE on: no cache, refusals, chain write."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services import query_service


def state(status="answered", confidence=0.9, gate=True):
    return {
        "status": status,
        "answer": "Revenue was $1,204.5 million [1]." if status == "answered" else "I can't answer that.",
        "citations": [{"span_id": "s1"}] if status == "answered" else [],
        "confidence_score": confidence,
        "passes_confidence_gate": gate,
    }


def patches(result, *, flag=True):
    return [
        patch.object(query_service.settings, "audit_grade_pipeline", flag),
        patch("app.agent.graph.run_audit_agent", new=AsyncMock(return_value=result)),
        patch.object(query_service, "_get_cached", new=AsyncMock(return_value={"answer": "stale"})),
        patch.object(query_service, "_set_cached", new=AsyncMock()),
        patch.object(query_service.audit_service, "record_query", new=AsyncMock()),
        patch.object(query_service.review_service, "create_review_item", new=AsyncMock(return_value={"id": "r1"})),
        patch("app.audit.payload.build_chain_payload", new=AsyncMock(return_value={"p": 1})),
        patch("app.audit.chain.append_entry", new=AsyncMock()),
    ]


def run_with(result, **kw):
    from contextlib import ExitStack

    stack = ExitStack()
    mocks = [stack.enter_context(p) for p in patches(result, **kw)]
    return stack, mocks


@pytest.mark.asyncio
async def test_flag_on_ignores_cache_and_appends_to_chain():
    stack, m = run_with(state())
    with stack:
        out = await query_service.run_query("q?", user_id="u")
    assert out.answer.startswith("Revenue") and out.status == "answered"
    m[2].assert_not_awaited()  # cache read
    m[3].assert_not_awaited()  # cache write
    m[7].assert_awaited_once()  # chain append


@pytest.mark.asyncio
async def test_refusal_is_final_not_a_review_item():
    stack, m = run_with(state("refused", 0.0, False))
    with stack:
        out = await query_service.run_query("q?", user_id="u")
    assert out.status == "refused" and out.sources == [] and not out.flagged_for_review
    m[5].assert_not_awaited()  # no review item
    m[7].assert_awaited_once()  # refusal is still logged


@pytest.mark.asyncio
async def test_chain_write_failure_fails_the_request():
    stack, m = run_with(state())
    with stack:
        m[7].side_effect = RuntimeError("chain down")
        with pytest.raises(RuntimeError, match="chain down"):
            await query_service.run_query("q?", user_id="u")


@pytest.mark.asyncio
async def test_flag_off_keeps_legacy_path_and_skips_chain():
    legacy = {"answer": "a", "citations": [], "confidence_score": 0.9, "passes_confidence_gate": True}
    stack, m = run_with(state(), flag=False)
    with stack, patch.object(query_service, "run_agent", new=AsyncMock(return_value=legacy)):
        m[2].return_value = None
        out = await query_service.run_query("q?", user_id="u")
    assert out.answer == "a"
    m[7].assert_not_awaited()
