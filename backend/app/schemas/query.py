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
    status: str  # "answered" | "pending_review" | "rejected"
    answer: str | None
    review_note: str | None
