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
    user_id: str | None = None,
) -> QueryResult:
    session_id = session_id or str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    logger.info("query received session_id={} question_len={}", session_id, len(question))

    cached = await _get_cached(question)
    if cached is not None:
        logger.info("query_cache_hit session_id={}", session_id)
        answer, citations, confidence = cached["answer"], cached["citations"], cached["confidence"]
        validation_passed = cached.get("validation_passed", True)
        validation_errors = cached.get("validation_errors", [])
        pii_detected = cached.get("pii_detected", False)
        passes_gate = True
    else:
        result = await run_agent(question)
        answer = result.get("answer", "")
        citations = result.get("citations", [])
        confidence = float(result.get("confidence_score", 0.0))
        validation_passed = result.get("validation_passed", True)
        validation_errors = result.get("validation_errors", [])
        pii_detected = result.get("pii_detected", False)
        passes_gate = result.get("passes_confidence_gate", confidence >= settings.confidence_threshold)

    review_item_id: str | None = None
    status = "answered"

    if not passes_gate:
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
    elif cached is None:
        await _set_cached(
            question,
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

    return QueryResult(
        answer=answer,
        confidence=confidence,
        sources=citations,
        flagged_for_review=not passes_gate,
        session_id=session_id,
        trace_id=trace_id,
        status=status,
        review_item_id=review_item_id,
    )


async def _get_cached(question: str) -> dict | None:
    try:
        return await get_cached_answer(question)
    except Exception as exc:  # noqa: BLE001 - cache is best-effort, never blocks a query
        logger.debug("query_cache_read_failed error={}", exc)
        return None


async def _set_cached(
    question: str,
    *,
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
