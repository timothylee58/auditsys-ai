"""State and constants for the audit-grade agent graph."""

from __future__ import annotations

from typing import Any, TypedDict

from app.cite.claims import Claim, ParsedClaims, RejectedClaim, SpanIndex
from app.cite.spans import Span
from app.cite.verify import ClaimVerdict

PIPELINE_VERSION = "audit-grade-v1"
GENERATION_PROMPT_VERSION = "claims-gen-v1"
VERIFIER_PROMPT_VERSION = "claims-verify-v1"
REWRITE_PROMPT_VERSION = "query-rewrite-v1"

# Spans handed to the generator per question (best by similarity).
MAX_CONTEXT_SPANS = 8
# Spans requested from the vector store per retrieval round.
RETRIEVAL_TOP_K = 8

# Stable refusal reasons: used in audit entries, metrics and alerts.
REFUSAL_MESSAGES: dict[str, str] = {
    "blocked_input": "This question was blocked by the input safety screen.",
    "no_accessible_documents": "You have no indexed documents to search yet.",
    "insufficient_evidence": (
        "The documents you can access do not contain enough relevant evidence to answer this reliably."
    ),
    "no_valid_claims": "No answer could be produced in which every statement cites a retrieved passage.",
    "no_supported_claims": "None of the drafted statements could be verified against their cited passages.",
    "malformed_model_output": "The answer could not be produced in a verifiable format. Please try again.",
    "verifier_unavailable": "Answers cannot be verified right now, so none is being shown. Please try again later.",
    "retrieval_error": "The documents could not be searched right now. Please try again later.",
    "permission_violation": "The request was stopped by an access-control safety check.",
    "citation_integrity": "The answer was stopped by a citation-integrity safety check.",
    "output_policy_failed": "The drafted answer was withheld by the output policy.",
}


class AgentState(TypedDict, total=False):
    # input
    question: str
    user_id: str

    # guard in
    log_question: str  # PII-redacted copy, safe to log
    pii_in_question: list[str]
    input_reasons: list[str]
    allowed_ids: list[str]

    # agentic retrieval
    current_query: str
    query_history: list[str]
    rounds: int
    spans: list[Span]  # all retrieved, intact spans (deduplicated)
    similarity: dict[str, float]  # span_id -> best similarity seen
    spans_dropped: int  # rows lacking span metadata or failing the hash check
    evidence_sufficient: bool
    relevant_ids: list[str]

    # cite + verify
    index: SpanIndex
    injection_flags: dict[str, list[str]]  # span_id -> neutraliser reasons
    parsed: ParsedClaims
    claims: list[Claim]
    rejected_claims: list[RejectedClaim]
    verdicts: list[ClaimVerdict]
    dropped_claims: list[tuple[Claim, ClaimVerdict]]
    partial_ids: frozenset[str]

    # output
    status: str  # "answered" | "refused"
    refusal_reason: str | None
    answer: str
    citations: list[dict[str, Any]]
    claim_views: list[dict[str, Any]]
    confidence_score: float
    validation_passed: bool
    validation_errors: list[str]
    pii_detected: bool
    passes_confidence_gate: bool
    context: dict[str, Any]
    stats: dict[str, int]

    # per-node trace: [{"node", "ms", ...}]
    trace: list[dict[str, Any]]
