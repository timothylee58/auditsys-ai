from fastapi import APIRouter, Depends, Response, status

from app.core.auth import CurrentUser, get_current_user
from app.core.rate_limit import rate_limited
from app.core.settings import settings
from app.schemas.query import QueryRequest, QueryResponse, QueryStatusResponse
from app.services import review_service
from app.services.query_service import QueryResult, run_query

router = APIRouter(prefix="/query", tags=["query"])


@router.post("", response_model=QueryResponse)
async def query_documents(
    body: QueryRequest,
    response: Response,
    user: CurrentUser = Depends(rate_limited("query", settings.query_rate_limit_per_minute)),
) -> QueryResponse:
    """Run a grounded RAG query.

    Returns 200 with an answer when confidence clears the gate, or 202 when
    the draft answer has been routed to the human review queue. Rate-limited
    per user because every call burns Azure OpenAI tokens.
    """
    result: QueryResult = await run_query(
        body.question, session_id=body.session_id, user_id=user.user_id
    )
    if result.status == "pending_review":
        response.status_code = status.HTTP_202_ACCEPTED
    return QueryResponse(
        answer=result.answer,
        citations=result.sources,
        confidence_score=result.confidence,
        trace_id=result.trace_id,
        status=result.status,
        session_id=result.session_id,
        review_item_id=result.review_item_id,
    )


@router.get("/status/{session_id}", response_model=QueryStatusResponse)
async def query_status(
    session_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> QueryStatusResponse:
    """Poll for the outcome of a query that was routed to human review.

    Scoped to the authenticated caller — you can only poll your own sessions.
    """
    status_payload = await review_service.get_query_status(session_id, user.user_id)
    return QueryStatusResponse(**status_payload)
