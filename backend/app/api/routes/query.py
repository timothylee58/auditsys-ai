"""Query routes — primary Q&A interface.

Endpoints:
- POST /query — Submit a question, get answer or 202 (pending review)
- GET /query/status/{session_id} — Poll for HITL result
- GET /query/stream/{session_id} — SSE streaming for real-time status
"""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger

from app.config import settings
from app.core.langfuse_client import get_tracer
from app.core.redis_client import get_cached_answer, set_cached_answer
from app.guardrails.confidence_gate import confidence_gate
from app.guardrails.output_validator import validate_output
from app.guardrails.pii_detector import redact_pii
from app.schemas.query import (
    QueryPendingResponse,
    QueryRequest,
    QueryResponse,
    QueryStatusResponse,
)
from app.services.audit_service import create_audit_entry
from app.services.review_service import create_review_item, get_query_status

router = APIRouter(prefix="/query", tags=["query"])

_PROMPT_VERSION = "v1.0.0"
_MODEL_NAME = "gpt-4o"


@router.post("", response_model=None)
async def submit_query(body: QueryRequest) -> QueryResponse | JSONResponse:
    """Submit a question for AI-grounded answer generation.

    The question is processed through the RAG pipeline:
    1. PII redaction (if Presidio enabled)
    2. Semantic cache check
    3. LangGraph agent execution (retrieve → synthesize → validate)
    4. Confidence gate check
    5. If confidence >= threshold: return answer (200)
    6. If confidence < threshold: route to HITL review queue (202)

    Returns:
        200: QueryResponse with answer, citations, confidence, trace_id
        202: QueryPendingResponse with review_item_id and session_id
    """
    session_id = body.session_id or str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    user_id = "anonymous"  # TODO: extract from auth token

    logger.info(
        "query_received session_id={} question_len={}",
        session_id,
        len(body.question),
    )

    # PII check on input
    safe_question = redact_pii(body.question) if settings.presidio_enabled else body.question
    pii_detected = safe_question != body.question

    # Check semantic cache
    cached = await get_cached_answer(safe_question)
    if cached:
        logger.info("query_cache_hit session_id={}", session_id)
        return QueryResponse(**cached)

    # Initialize Langfuse trace
    tracer = get_tracer()
    trace = tracer.trace(
        name="query",
        session_id=session_id,
        input={"question": safe_question},
        metadata={"prompt_version": _PROMPT_VERSION},
    )

    # Run RAG agent
    try:
        from app.agents.rag_agent import build_graph

        graph = build_graph()
        from langchain_core.messages import HumanMessage

        agent_state = await graph.ainvoke(
            {
                "messages": [HumanMessage(content=safe_question)],
                "context": {},
                "metadata": {"session_id": session_id, "trace_id": trace_id},
                "error": None,
            }
        )

        # Extract answer from agent state
        answer = agent_state.get("metadata", {}).get("answer", "")
        citations = agent_state.get("context", {}).get("citations", [])
        confidence_score = agent_state.get("metadata", {}).get("confidence", 0.55)

    except Exception as exc:
        logger.error("agent_execution_failed session_id={} error={}", session_id, str(exc))
        # Fallback to a safe response
        answer = (
            f"Based on the indexed audit documents, no direct policy reference was found "
            f"matching your query. Please upload relevant documents to enable grounded answers."
        )
        citations = []
        confidence_score = 0.3

    # Output validation
    validated_answer = validate_output(answer)
    validation_passed = validated_answer == answer
    validation_errors = [] if validation_passed else ["output_sanitized"]

    # Confidence gate
    passes_confidence = confidence_gate(confidence_score, settings.confidence_threshold)

    if passes_confidence:
        # Direct answer path
        status = "answered"
        response_data = QueryResponse(
            answer=validated_answer,
            citations=citations,
            confidence_score=confidence_score,
            trace_id=trace_id,
            status=status,
        )

        # Cache the answer
        await set_cached_answer(safe_question, response_data.model_dump())

        # Audit log
        await create_audit_entry(
            session_id=session_id,
            user_id=user_id,
            query=body.question,
            answer=validated_answer,
            citations=citations,
            confidence_score=confidence_score,
            prompt_version=_PROMPT_VERSION,
            model_name=_MODEL_NAME,
            trace_id=trace_id,
            status=status,
            pii_detected=pii_detected,
            validation_passed=validation_passed,
            validation_errors=validation_errors,
        )

        return response_data
    else:
        # HITL review path
        review_item = await create_review_item(
            session_id=session_id,
            user_id=user_id,
            query=body.question,
            draft_answer=validated_answer,
            citations=citations,
            confidence_score=confidence_score,
        )

        # Audit log
        await create_audit_entry(
            session_id=session_id,
            user_id=user_id,
            query=body.question,
            answer=None,
            citations=citations,
            confidence_score=confidence_score,
            prompt_version=_PROMPT_VERSION,
            model_name=_MODEL_NAME,
            trace_id=trace_id,
            status="pending_review",
            review_item_id=review_item.id,
            pii_detected=pii_detected,
            validation_passed=validation_passed,
            validation_errors=validation_errors,
        )

        logger.info(
            "query_routed_to_review session_id={} confidence={:.2f}",
            session_id,
            confidence_score,
        )

        pending_response = QueryPendingResponse(
            review_item_id=review_item.id,
            message="Answer pending compliance review",
            session_id=session_id,
        )

        return JSONResponse(status_code=202, content=pending_response.model_dump())


@router.get("/status/{session_id}", response_model=QueryStatusResponse)
async def query_status(session_id: str) -> QueryStatusResponse:
    """Poll for the status of a query that was routed to HITL review.

    Returns the current status: pending_review, answered, or rejected.
    Once answered (approved or overridden), the answer field is populated.
    """
    result = await get_query_status(session_id)

    if result["status"] == "not_found":
        raise HTTPException(
            status_code=404,
            detail={
                "type": "https://auditsys.ai/errors/session-not-found",
                "title": "Session Not Found",
                "status": 404,
                "detail": f"No query found for session '{session_id}'.",
            },
        )

    return QueryStatusResponse(
        status=result["status"],
        answer=result["answer"],
        review_note=result["review_note"],
    )


@router.get("/stream/{session_id}")
async def query_stream(session_id: str) -> StreamingResponse:
    """SSE streaming endpoint for real-time status updates.

    Pushes status updates to the client every 2 seconds until
    the query is resolved (answered or rejected).
    """

    async def event_generator():
        max_attempts = 150  # 5 minutes at 2s intervals
        for _ in range(max_attempts):
            result = await get_query_status(session_id)
            status = result["status"]

            yield f"data: {_sse_json(result)}\n\n"

            if status in ("answered", "rejected", "not_found"):
                break

            await asyncio.sleep(2)

        yield "data: {\"event\": \"done\"}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse_json(data: dict) -> str:
    """Serialize dict to JSON for SSE."""
    import json

    return json.dumps(data)
