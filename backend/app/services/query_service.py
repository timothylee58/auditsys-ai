import uuid
from dataclasses import dataclass

from loguru import logger

from app.agents.rag_agent import PROMPT_VERSION, run_agent
from app.core.redis_client import get_cached_answer, set_cached_answer
from app.core.settings import settings
from app.services import audit_service, review_service


@dataclass
class QueryResult:
    answer: str
    confidence: float
    sources: list[dict]
    flagged_for_review: bool
    session_id: str = ""
    trace_id: str = ""
    status: str = "answered"
    review_item_id: str | None = None


async def run_query(
    question: str,
    *,
    session_id: str | None = None,
    user_id: str,
) -> QueryResult:
    """Run a grounded query for an authenticated user.

    ``user_id`` scopes the answer cache, the retrieval search, the review
    queue item, and the audit trail. It is mandatory: identity comes from
    the verified JWT in the route, never from client-supplied headers.
    """
    session_id = session_id or str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    logger.info("query received session_id={} question_len={}", session_id, len(question))

    audit_grade = settings.audit_grade_pipeline
    # The audit-grade pipeline never serves cached answers: every answer must
    # be freshly verified against the current documents and chain-logged.
    cached = None if audit_grade else await _get_cached(question, user_id)
    audit_state: dict | None = None
    if cached is not None:
        logger.info("query_cache_hit session_id={}", session_id)
        answer, citations, confidence = cached["answer"], cached["citations"], cached["confidence"]
        validation_passed = cached.get("validation_passed", True)
        validation_errors = cached.get("validation_errors", [])
        pii_detected = cached.get("pii_detected", False)
        passes_gate = True
    else:
        if audit_grade:
            from app.agent.graph import run_audit_agent

            result = await run_audit_agent(question, user_id=user_id)
            audit_state = result
        else:
            result = await run_agent(question, user_id=user_id)
        answer = result.get("answer", "")
        citations = result.get("citations", [])
        confidence = float(result.get("confidence_score", 0.0))
        validation_passed = result.get("validation_passed", True)
        validation_errors = result.get("validation_errors", [])
        pii_detected = result.get("pii_detected", False)
        passes_gate = result.get("passes_confidence_gate", confidence >= settings.confidence_threshold)

    review_item_id: str | None = None
    status = "answered"

    refused = audit_state is not None and audit_state.get("status") == "refused"

    if refused:
        # A refusal is a deliberate, final outcome, not a draft needing review.
        status = "refused"
        citations = []
    elif not passes_gate:
        logger.warning("low confidence query flagged session_id={} confidence={:.2f}", session_id, confidence)
        review_item = await review_service.create_review_item(
            session_id=session_id,
            user_id=user_id,
            query=question,
            draft_answer=answer,
            citations=citations,
            confidence_score=confidence,
        )
        review_item_id = review_item.get("id")
        status = "pending_review"
    elif cached is None and not audit_grade:
        await _set_cached(
            question,
            user_id=user_id,
            answer=answer,
            citations=citations,
            confidence=confidence,
            validation_passed=validation_passed,
            validation_errors=validation_errors,
            pii_detected=pii_detected,
        )

    await audit_service.record_query(
        session_id=session_id,
        user_id=user_id,
        query=question,
        answer=answer if status == "answered" else None,
        citations=citations,
        confidence_score=confidence,
        prompt_version=PROMPT_VERSION,
        model_name=settings.azure_openai_deployment or "unknown",
        trace_id=trace_id,
        status=status,
        review_item_id=review_item_id,
        pii_detected=pii_detected,
        validation_passed=validation_passed,
        validation_errors=validation_errors,
    )

    if audit_state is not None:
        # Fail closed: an answer that cannot be written to the tamper-evident
        # log must not be returned, so errors here propagate to the caller.
        from app.audit.chain import append_entry
        from app.audit.payload import build_chain_payload

        payload = await build_chain_payload(
            audit_state, question=question, session_id=session_id, trace_id=trace_id, user_id=user_id
        )
        await append_entry(payload, user_id=user_id)

    return QueryResult(
        answer=answer,
        confidence=confidence,
        sources=citations,
        flagged_for_review=not passes_gate and not refused,
        session_id=session_id,
        trace_id=trace_id,
        status=status,
        review_item_id=review_item_id,
    )


async def _get_cached(question: str, user_id: str) -> dict | None:
    try:
        return await get_cached_answer(question, user_id)
    except Exception as exc:  # noqa: BLE001 - cache is best-effort, never blocks a query
        logger.debug("query_cache_read_failed error={}", exc)
        return None


async def _set_cached(
    question: str,
    *,
    user_id: str,
    answer: str,
    citations: list[dict],
    confidence: float,
    validation_passed: bool,
    validation_errors: list[str],
    pii_detected: bool,
) -> None:
    try:
        await set_cached_answer(
            question,
            user_id,
            {
                "answer": answer,
                "citations": citations,
                "confidence": confidence,
                "validation_passed": validation_passed,
                "validation_errors": validation_errors,
                "pii_detected": pii_detected,
            },
        )
    except Exception as exc:  # noqa: BLE001 - cache is best-effort, never blocks a query
        logger.debug("query_cache_write_failed error={}", exc)
