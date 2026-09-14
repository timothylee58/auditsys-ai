"""
AuditSys AI — Confidence Gate
==============================
Scores answer quality based on retrieval evidence.
Used by rag_agent.py's synthesise_answer node to compute confidence_score,
and by run_agent to decide HITL routing against CONFIDENCE_THRESHOLD.

Score components (weighted average):
  1. Retrieval similarity  (40%) — mean cosine similarity of top chunks
  2. Citation coverage     (40%) — % of citations that are valid + grounded
  3. Answer completeness   (20%) — penalises "I cannot answer" non-answers

Score < CONFIDENCE_THRESHOLD (default 0.75) → routes to HITL queue.
"""

from __future__ import annotations

import re
from typing import Any

NON_ANSWER_PATTERNS = [
    r"i cannot answer",
    r"not enough information",
    r"no information available",
    r"documents don.t contain",
    r"i don.t have",
]


async def score_confidence(
    answer: str,
    retrieved_chunks: list[dict[str, Any]],
    citations: list[dict[str, Any]],
) -> float:
    """
    Compute 0.0–1.0 confidence score for the generated answer.

    Args:
        answer:           cleaned LLM answer (no citations block)
        retrieved_chunks: [{text, source, page, score}] from pgvector
        citations:        [{source, page, relevance_score}] parsed from answer
    """
    retrieval_score = _score_retrieval(retrieved_chunks)
    citation_score = _score_citations(citations, retrieved_chunks)
    completeness_score = _score_completeness(answer)

    # Weighted average
    final = (
        0.40 * retrieval_score
        + 0.40 * citation_score
        + 0.20 * completeness_score
    )

    return round(min(max(final, 0.0), 1.0), 4)


def _score_retrieval(chunks: list[dict[str, Any]]) -> float:
    """Mean cosine similarity of retrieved chunks. 0 if no chunks."""
    if not chunks:
        return 0.0
    scores = [float(c.get("score", 0.0)) for c in chunks]
    return sum(scores) / len(scores)


def _score_citations(
    citations: list[dict[str, Any]],
    retrieved_chunks: list[dict[str, Any]],
) -> float:
    """
    Citation coverage: what fraction of citations can be traced
    back to an actually retrieved chunk?
    """
    if not citations:
        return 0.0

    valid_sources = {c.get("source") for c in retrieved_chunks}
    valid_count = sum(
        1 for c in citations if c.get("source") in valid_sources
    )
    return valid_count / len(citations)


def _score_completeness(answer: str) -> float:
    """
    Penalise non-answers (hallucination hedge phrases).
    Returns 0.2 if answer is a refusal, 1.0 if substantive.
    """
    lower = answer.lower()
    for pattern in NON_ANSWER_PATTERNS:
        if re.search(pattern, lower):
            return 0.2
    # Minimum length heuristic — very short answers are likely incomplete
    if len(answer.strip()) < 50:
        return 0.4
    return 1.0


def confidence_gate(score: float, threshold: float) -> bool:
    """Return True if score meets threshold (answer can be shown), False if HITL needed."""
    return score >= threshold
