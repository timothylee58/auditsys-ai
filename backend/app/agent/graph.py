"""The audit-grade agent as a LangGraph state machine.

    guard_in -> retrieve -> grade --sufficient--> generate -> verify -> guard_out -> END
                   ^           |                     |           |
                   |        thin evidence            |           |
                   +--- rewrite <--(rounds < cap)    +-----------+--> refuse -> END

* **guard_in** screens the question, then resolves which documents the caller
  may read. Nothing is retrieved before this.
* **retrieve / grade / rewrite** loop: retrieve spans, grade them by
  similarity, rewrite the query if evidence is thin, stop at
  ``max_retrieval_rounds``. Still thin -> refuse; never guess.
* **generate** produces atomic claims citing numbered sources (see
  ``cite.claims``); **verify** checks each claim against only its cited spans
  (see ``cite.verify``); unsupported claims are dropped.
* **guard_out** re-asserts that every citation is a retrieved span (hard
  gate), renders the answer and applies the output policy.
* **refuse** is reachable from every stage and always carries a stable
  reason code.

There is deliberately no tool-calling node: retrieved text can never choose
an action. All collaborators arrive through ``AgentDeps`` so each stage is
unit-testable with stubs and the provider can change without touching logic.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any

from loguru import logger

from app.agent.state import (
    MAX_CONTEXT_SPANS,
    REFUSAL_MESSAGES,
    RETRIEVAL_TOP_K,
    AgentState,
)
from app.cite.claims import (
    CitationIntegrityError,
    ClaimParseError,
    SpanIndex,
    assert_citations_retrieved,
    generate_claims,
    render_answer,
)
from app.cite.spans import spans_from_rows
from app.cite.verify import VerifierUnavailable, apply_policy, verify_claims
from app.core.llm import ChatFn
from app.core.settings import settings
from app.guardrails.confidence_gate import confidence_gate, score_audit_confidence
from app.guardrails.input import ScreenResult, neutralize_retrieved_text, screen_question
from app.guardrails.output import enforce_output_policy
from app.guardrails.permissions import PermissionLeak, allowed_document_ids, assert_rows_permitted

REWRITE_SYSTEM_PROMPT = (
    "You rewrite a user's question into one standalone search query for retrieving passages "
    "from audit and financial documents. Be specific; include likely synonyms and the exact "
    "terms such documents use. Output ONLY the query, no explanation."
)


@dataclass
class AgentDeps:
    """Everything the graph needs from the outside world."""

    embed: Callable[[str], Awaitable[list[float]]]
    search: Callable[[list[float], str, list[str]], Awaitable[list[dict[str, Any]]]]
    allowed_ids: Callable[[str], Awaitable[list[str]]]
    screen: Callable[[str], Awaitable[ScreenResult]]
    generator: ChatFn
    rewriter: ChatFn
    verifier: ChatFn


def default_deps() -> AgentDeps:
    """Production wiring. Imports are local so building the graph at startup
    never needs credentials or network."""
    from app.core.database import get_async_supabase
    from app.core.llm import main_chat_fn, verifier_chat_fn
    from app.services.embedding_service import get_embedding

    async def search(embedding: list[float], user_id: str, allowed: list[str]) -> list[dict[str, Any]]:
        client = await get_async_supabase()
        result = await client.rpc(
            "match_document_chunks",
            {
                "query_embedding": embedding,
                "match_count": RETRIEVAL_TOP_K,
                "filter_document_ids": allowed,
                "user_id": user_id,
            },
        ).execute()
        return result.data or []

    return AgentDeps(
        embed=get_embedding,
        search=search,
        allowed_ids=allowed_document_ids,
        screen=screen_question,
        generator=main_chat_fn(max_tokens=1500),
        rewriter=verifier_chat_fn(json_mode=False, max_tokens=120),
        verifier=verifier_chat_fn(max_tokens=1500),
    )


# -- helpers ---------------------------------------------------------------------------------


def _refuse(reason: str, **extra: Any) -> dict[str, Any]:
    return {"status": "refused", "refusal_reason": reason, **extra}


def traced(name: str):
    """Record node latency (and any ``_trace`` info the node returns) in state."""

    def decorator(fn: Callable[[AgentState], Awaitable[dict[str, Any]]]):
        @wraps(fn)
        async def wrapper(state: AgentState) -> dict[str, Any]:
            started = time.perf_counter()
            update = await fn(state)
            info = update.pop("_trace", {})
            event = {"node": name, "ms": round((time.perf_counter() - started) * 1000, 1), **info}
            return {**update, "trace": [*state.get("trace", []), event]}

        return wrapper

    return decorator


def _route_after(state: AgentState, nxt: str) -> str:
    return "refuse" if state.get("refusal_reason") else nxt


# -- graph --------------------------------------------------------------------------------------


def build_graph(deps: AgentDeps):
    """Compile the agent graph. ``deps`` is captured by the node closures."""
    from langgraph.graph import END, StateGraph

    @traced("guard_in")
    async def guard_in(state: AgentState) -> dict[str, Any]:
        screen = await deps.screen(state["question"])
        base = {
            "log_question": screen.log_question,
            "pii_in_question": screen.pii_types,
            "input_reasons": screen.reasons,
            "current_query": state["question"],
            "query_history": [],
            "rounds": 0,
            "spans": [],
            "similarity": {},
            "spans_dropped": 0,
        }
        if not screen.allowed:
            return {**base, **_refuse("blocked_input"), "_trace": {"reasons": screen.reasons}}

        allowed = await deps.allowed_ids(state["user_id"])
        if not allowed:
            return {**base, **_refuse("no_accessible_documents"), "allowed_ids": []}
        return {**base, "allowed_ids": allowed, "_trace": {"allowed_documents": len(allowed)}}

    @traced("retrieve")
    async def retrieve(state: AgentState) -> dict[str, Any]:
        query = state["current_query"]
        try:
            embedding = await deps.embed(query)
            rows = await deps.search(embedding, state["user_id"], state["allowed_ids"])
            assert_rows_permitted(rows, state["allowed_ids"])
        except PermissionLeak:
            logger.critical("permission_leak user_id={} (retrieval returned a foreign document)", state["user_id"])
            return _refuse("permission_violation")
        except Exception as exc:  # noqa: BLE001 - any retrieval failure must refuse, not guess
            logger.error("retrieve_failed error={}", exc)
            return _refuse("retrieval_error")

        new_spans = spans_from_rows(rows)
        rows_by_span = {r["span_id"]: r for r in rows if r.get("span_id")}
        similarity = dict(state.get("similarity", {}))
        by_id = {s.span_id: s for s in state.get("spans", [])}
        for span in new_spans:
            row = rows_by_span[span.span_id]
            sim = float(row.get("similarity") or row.get("score") or 0.0)
            similarity[span.span_id] = max(similarity.get(span.span_id, 0.0), sim)
            by_id[span.span_id] = span
        ordered = sorted(by_id.values(), key=lambda s: similarity[s.span_id], reverse=True)
        dropped = state.get("spans_dropped", 0) + (len(rows) - len(new_spans))
        return {
            "spans": ordered,
            "similarity": similarity,
            "spans_dropped": dropped,
            "rounds": state.get("rounds", 0) + 1,
            "query_history": [*state.get("query_history", []), query],
            "_trace": {"query_chars": len(query), "rows": len(rows), "spans_total": len(ordered)},
        }

    @traced("grade")
    async def grade(state: AgentState) -> dict[str, Any]:
        similarity = state["similarity"]
        relevant = [
            s.span_id for s in state["spans"] if similarity[s.span_id] >= settings.min_span_similarity
        ]
        sufficient = len(relevant) >= settings.min_evidence_spans
        update: dict[str, Any] = {
            "relevant_ids": relevant,
            "evidence_sufficient": sufficient,
            "_trace": {"relevant": len(relevant), "sufficient": sufficient},
        }
        if not sufficient and state["rounds"] >= settings.max_retrieval_rounds:
            update.update(_refuse("insufficient_evidence"))
        return update

    @traced("rewrite")
    async def rewrite(state: AgentState) -> dict[str, Any]:
        history = state["query_history"]
        raw = await deps.rewriter(
            [
                {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Question: {state['question']}\nQueries already tried: {history}",
                },
            ]
        )
        new_query = raw.strip().strip('"').strip()[:300]
        if not new_query or new_query in history:
            # No new angle to try: stop instead of looping on the same search.
            return {**_refuse("insufficient_evidence"), "_trace": {"made_progress": False}}
        return {"current_query": new_query, "_trace": {"made_progress": True}}

    @traced("generate")
    async def generate(state: AgentState) -> dict[str, Any]:
        similarity = state["similarity"]
        relevant = set(state["relevant_ids"])
        top = [s for s in state["spans"] if s.span_id in relevant][:MAX_CONTEXT_SPANS]
        index = SpanIndex.from_spans(top)
        flags = {s.span_id: r for s in top if (r := neutralize_retrieved_text(s.text)[1])}

        try:
            parsed = await generate_claims(
                state["question"],
                index,
                deps.generator,
                transform=lambda text: neutralize_retrieved_text(text)[0],
            )
        except ClaimParseError as exc:
            logger.warning("claims_unparseable error={}", exc)
            return _refuse("malformed_model_output", index=index, injection_flags=flags)

        base = {
            "index": index,
            "injection_flags": flags,
            "parsed": parsed,
            "claims": list(parsed.claims),
            "rejected_claims": list(parsed.rejected),
            "_trace": {
                "context_spans": len(index.spans),
                "claims": len(parsed.claims),
                "rejected": len(parsed.rejected),
                "injection_flagged_spans": len(flags),
                "max_similarity": round(max((similarity[s.span_id] for s in top), default=0.0), 4),
            },
        }
        if parsed.insufficient_evidence:
            return {**base, **_refuse("insufficient_evidence")}
        if not parsed.claims:
            return {**base, **_refuse("no_valid_claims")}
        return base

    @traced("verify")
    async def verify(state: AgentState) -> dict[str, Any]:
        try:
            verdicts = await verify_claims(state["claims"], state["index"], deps.verifier)
        except VerifierUnavailable as exc:
            logger.error("verifier_unavailable error={}", exc)
            return _refuse("verifier_unavailable")
        policy = apply_policy(state["claims"], verdicts)
        update: dict[str, Any] = {
            "verdicts": verdicts,
            "claims": list(policy.kept),
            "partial_ids": policy.partial_ids,
            "dropped_claims": list(policy.dropped),
            "_trace": policy.stats,
        }
        if not policy.kept:
            update.update(_refuse("no_supported_claims"))
        return update

    @traced("guard_out")
    async def guard_out(state: AgentState) -> dict[str, Any]:
        retrieved_ids = frozenset(s.span_id for s in state["spans"])
        try:
            assert_citations_retrieved(state["claims"], retrieved_ids)
            text, citations, views = render_answer(
                state["claims"], state["index"], partial_ids=state.get("partial_ids", frozenset())
            )
        except CitationIntegrityError as exc:
            logger.critical("citation_integrity_violation error={}", exc)
            return _refuse("citation_integrity")

        policy = await enforce_output_policy(text)
        if not policy.passed:
            return {
                **_refuse("output_policy_failed"),
                "validation_passed": False,
                "validation_errors": policy.errors,
                "_trace": {"errors": policy.errors},
            }

        similarity = state["similarity"]
        cited_ids = [c["span_id"] for c in citations]
        stats = apply_policy_stats(state)
        confidence = score_audit_confidence(
            [similarity[sid] for sid in cited_ids],
            supported=stats["claims_supported"],
            partly_supported=stats["claims_partly_supported"],
            attempted=stats["claims_attempted"],
        )
        return {
            "status": "answered",
            "refusal_reason": None,
            "answer": policy.answer,
            "citations": citations,
            "claim_views": views,
            "confidence_score": confidence,
            "validation_passed": True,
            "validation_errors": [],
            "pii_detected": policy.pii_detected,
            "stats": stats,
            "context": {"chunks": [{"content": state["index"].by_id(sid).text} for sid in cited_ids]},
            "_trace": {"confidence": confidence, "pii": policy.pii_detected},
        }

    @traced("refuse")
    async def refuse(state: AgentState) -> dict[str, Any]:
        reason = state.get("refusal_reason") or "insufficient_evidence"
        logger.info("agent_refused reason={}", reason)
        return {
            "status": "refused",
            "refusal_reason": reason,
            "answer": REFUSAL_MESSAGES.get(reason, REFUSAL_MESSAGES["insufficient_evidence"]),
            "citations": [],
            "claim_views": [],
            "confidence_score": 0.0,
            "stats": apply_policy_stats(state),
            "context": {"chunks": []},
            "_trace": {"reason": reason},
        }

    def after_grade(state: AgentState) -> str:
        if state.get("refusal_reason"):
            return "refuse"
        return "generate" if state["evidence_sufficient"] else "rewrite"

    graph = StateGraph(AgentState)
    for name, node in [
        ("guard_in", guard_in),
        ("retrieve", retrieve),
        ("grade", grade),
        ("rewrite", rewrite),
        ("generate", generate),
        ("verify", verify),
        ("guard_out", guard_out),
        ("refuse", refuse),
    ]:
        graph.add_node(name, node)

    graph.set_entry_point("guard_in")
    graph.add_conditional_edges("guard_in", lambda s: _route_after(s, "retrieve"), ["retrieve", "refuse"])
    graph.add_conditional_edges("retrieve", lambda s: _route_after(s, "grade"), ["grade", "refuse"])
    graph.add_conditional_edges("grade", after_grade, ["generate", "rewrite", "refuse"])
    graph.add_conditional_edges("rewrite", lambda s: _route_after(s, "retrieve"), ["retrieve", "refuse"])
    graph.add_conditional_edges("generate", lambda s: _route_after(s, "verify"), ["verify", "refuse"])
    graph.add_conditional_edges("verify", lambda s: _route_after(s, "guard_out"), ["guard_out", "refuse"])
    graph.add_conditional_edges("guard_out", lambda s: _route_after(s, END), [END, "refuse"])
    graph.add_edge("refuse", END)
    return graph.compile()


def apply_policy_stats(state: AgentState) -> dict[str, int]:
    """Claim counts for audit/metrics, including claims rejected before verification."""
    kept = state.get("claims") or []
    partial = len(state.get("partial_ids") or ())
    dropped = len(state.get("dropped_claims") or [])
    rejected = len(state.get("rejected_claims") or [])
    verified = bool(state.get("verdicts"))
    supported = len(kept) - partial if verified else 0
    return {
        "claims_attempted": (len(kept) + dropped + rejected) if verified else (len(kept) + rejected),
        "claims_rejected_citation": rejected,
        "claims_supported": supported,
        "claims_partly_supported": partial,
        "claims_unsupported": dropped,
        "rounds": state.get("rounds", 0),
        "spans_retrieved": len(state.get("spans") or []),
        "spans_dropped": state.get("spans_dropped", 0),
    }


# -- entry points ---------------------------------------------------------------------------------

_graph = None


def get_audit_graph():
    """Singleton compiled graph with production wiring."""
    global _graph
    if _graph is None:
        _graph = build_graph(default_deps())
    return _graph


async def run_audit_agent(question: str, *, user_id: str, graph=None) -> AgentState:
    """Run the audit-grade pipeline for one question, scoped to ``user_id``."""
    graph = graph or get_audit_graph()
    result: AgentState = await graph.ainvoke({"question": question, "user_id": user_id})
    result["passes_confidence_gate"] = (
        result.get("status") == "answered"
        and confidence_gate(result.get("confidence_score", 0.0), settings.confidence_threshold)
    )
    return result
