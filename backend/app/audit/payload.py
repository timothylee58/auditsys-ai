"""Build the audit-chain payload for one answered or refused question.

The payload is the full chain of custody for an answer: the question, which
spans were retrieved, the claims, the verifier's verdicts, the final answer,
and the model and prompt versions that produced it.

Privacy rules applied here, before anything is hashed or stored:

* the question is the PII-redacted copy; a SHA-256 of the original lets
  someone who holds the original prove it matches without it being stored;
* retrieved spans are logged as references (ids, page, character range,
  content hash) — never their text; the document store is the source of
  truth and the hash proves the passage is unchanged;
* claim text, verdict reasons, rewritten queries and the final answer are
  passed through PII redaction because they are derived from documents.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from app.agent.state import (
    GENERATION_PROMPT_VERSION,
    PIPELINE_VERSION,
    REWRITE_PROMPT_VERSION,
    VERIFIER_PROMPT_VERSION,
    AgentState,
)
from app.core.settings import settings
from app.guardrails.pii_detector import scan_pii

PAYLOAD_VERSION = 1


async def redact_for_log(text: str) -> str:
    pii = await scan_pii(text)
    return pii.anonymised_text if pii.has_pii and pii.anonymised_text else text


async def build_chain_payload(
    result: AgentState,
    *,
    question: str,
    session_id: str,
    trace_id: str,
    user_id: str,
) -> dict[str, Any]:
    similarity = result.get("similarity", {})
    spans = result.get("spans", [])
    verdicts = {v.claim_id: v for v in result.get("verdicts", [])}
    claims = list(result.get("claims", [])) + [c for c, _ in result.get("dropped_claims", [])]
    claims.sort(key=lambda c: int(c.claim_id[1:]) if c.claim_id[1:].isdigit() else 0)
    kept_ids = {c.claim_id for c in result.get("claims", [])}

    claim_entries = []
    for claim in claims:
        verdict = verdicts.get(claim.claim_id)
        claim_entries.append(
            {
                "claim_id": claim.claim_id,
                "text": await redact_for_log(claim.text),
                "span_ids": list(claim.span_ids),
                "verdict": verdict.verdict.value if verdict else None,
                "method": verdict.method.value if verdict else None,
                "reason": await redact_for_log(verdict.reason) if verdict and verdict.reason else "",
                "shown": claim.claim_id in kept_ids,
            }
        )

    return {
        "payload_version": PAYLOAD_VERSION,
        "recorded_at": datetime.now(UTC).isoformat(),
        "session_id": session_id,
        "trace_id": trace_id,
        "user_id": user_id,
        "question": result.get("log_question") or await redact_for_log(question),
        "question_sha256": hashlib.sha256(question.encode("utf-8")).hexdigest(),
        "guard_in": {
            "reasons": result.get("input_reasons", []),
            "pii_in_question": result.get("pii_in_question", []),
            "allowed_documents": len(result.get("allowed_ids", [])),
        },
        "retrieval": {
            "rounds": result.get("rounds", 0),
            "queries": [await redact_for_log(q) for q in result.get("query_history", [])],
            "spans_dropped": result.get("spans_dropped", 0),
            "spans": [
                {
                    "span_id": s.span_id,
                    "document_id": s.ref.document_id,
                    "version": s.ref.version,
                    "page": s.ref.page,
                    "char_start": s.ref.char_start,
                    "char_end": s.ref.char_end,
                    "content_hash": s.ref.content_hash,
                    "similarity": round(similarity.get(s.span_id, 0.0), 4),
                }
                for s in spans
            ],
            "injection_flags": result.get("injection_flags", {}),
        },
        "claims": claim_entries,
        "rejected_claims": [
            {"reason": r.reason, "cited": list(r.cited)} for r in result.get("rejected_claims", [])
        ],
        "final_answer": await redact_for_log(result.get("answer", "")),
        "citations": [c["span_id"] for c in result.get("citations", [])],
        "outcome": {
            "status": result.get("status"),
            "refusal_reason": result.get("refusal_reason"),
            "confidence_score": result.get("confidence_score", 0.0),
            "pii_in_answer": result.get("pii_detected", False),
            "validation_errors": result.get("validation_errors", []),
            "stats": result.get("stats", {}),
        },
        "versions": {
            "pipeline": PIPELINE_VERSION,
            "generation_prompt": GENERATION_PROMPT_VERSION,
            "verifier_prompt": VERIFIER_PROMPT_VERSION,
            "rewrite_prompt": REWRITE_PROMPT_VERSION,
            "generator_model": settings.azure_openai_deployment,
            "verifier_model": settings.azure_openai_verifier_deployment or settings.azure_openai_deployment,
        },
        "trace": [{k: v for k, v in t.items() if k in ("node", "ms")} for t in result.get("trace", [])],
    }
