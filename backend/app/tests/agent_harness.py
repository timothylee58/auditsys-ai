"""Shared stubs for driving the audit-grade agent graph in tests."""

from __future__ import annotations

import json

from app.agent.graph import AgentDeps, build_graph, run_audit_agent
from app.cite.spans import content_hash, span_id_for
from app.guardrails.input import ScreenResult

DOC = "44444444-4444-4444-4444-444444444444"
OTHER_DOC = "55555555-5555-5555-5555-555555555555"

REVENUE = "Total revenue for fiscal 2024 was $1,204.5 million, an increase of 8.5% over the prior year."
OPINION = "The auditor issued an unqualified opinion on the financial statements for the year."
APPROVAL = "Payments above $50,000 require dual approval by two authorised signatories."


def row(i: int, text: str, sim: float = 0.62, doc: str = DOC, **over) -> dict:
    h = content_hash(text)
    base = {
        "span_id": span_id_for(doc, 1, i, h),
        "document_id": doc,
        "version": 1,
        "page_number": i + 1,
        "char_start": 0,
        "char_end": len(text),
        "content_hash": h,
        "content": text,
        "similarity": sim,
    }
    base.update(over)
    return base


def claims_json(*claims, insufficient=False) -> str:
    return json.dumps(
        {"insufficient_evidence": insufficient, "claims": [{"text": t, "sources": s} for t, s in claims]}
    )


def verdicts_json(*items) -> str:
    return json.dumps({"verdicts": [{"claim_id": c, "verdict": v, "reason": "ok"} for c, v in items]})


class Harness:
    """Builds AgentDeps from simple scripted behaviours and records calls."""

    def __init__(self, *, search_results, generator=None, verifier=None, rewriter=None, allowed=None, screen=None):
        self.search_results = list(search_results)
        self.embed_calls: list[str] = []
        self.search_calls = 0
        self.generator_prompts: list[str] = []
        self.generator_calls = 0
        self.verifier_calls = 0
        self.rewriter_calls = 0
        self._generator = generator or (lambda: claims_json())
        self._verifier = verifier or (lambda: verdicts_json())
        self._rewriter = rewriter or (lambda n: f"rewritten query {n}")
        self._allowed = [DOC] if allowed is None else allowed
        self._screen = screen

    def deps(self) -> AgentDeps:
        async def embed(q):
            self.embed_calls.append(q)
            return [0.1, 0.2]

        async def search(_emb, _uid, _allowed):
            self.search_calls += 1
            result = self.search_results.pop(0) if len(self.search_results) > 1 else self.search_results[0]
            if isinstance(result, Exception):
                raise result
            return result

        async def allowed(_uid):
            return self._allowed

        async def screen(q):
            if self._screen:
                return self._screen
            return ScreenResult(allowed=True, log_question=q)

        async def generator(messages):
            self.generator_calls += 1
            self.generator_prompts.append(messages[-1]["content"])
            out = self._generator()
            if isinstance(out, Exception):
                raise out
            return out

        async def rewriter(_messages):
            self.rewriter_calls += 1
            return self._rewriter(self.rewriter_calls)

        async def verifier(_messages):
            self.verifier_calls += 1
            out = self._verifier()
            if isinstance(out, Exception):
                raise out
            return out

        return AgentDeps(embed, search, allowed, screen, generator, rewriter, verifier)

    async def run(self, question="What was revenue in fiscal 2024?", user_id="user-1"):
        graph = build_graph(self.deps())
        return await run_audit_agent(question, user_id=user_id, graph=graph)
