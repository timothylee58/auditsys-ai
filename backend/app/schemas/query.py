from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=5, max_length=2000)
    session_id: str | None = None  # generated if not provided


class QueryResponse(BaseModel):
    answer: str
    citations: list[dict]
    confidence_score: float
    trace_id: str
    status: str
    session_id: str
    review_item_id: str | None = None


class QueryStatusResponse(BaseModel):
    status: str  # "answered" | "pending_review" | "rejected" | "not_found"
    # review_service.get_query_status() omits these keys entirely for the
    # pending_review/not_found cases — defaults are required so that
    # QueryStatusResponse(**status_payload) doesn't raise a validation
    # error (and 500) on the first poll after a query is routed to review.
    answer: str | None = None
    review_note: str | None = None
