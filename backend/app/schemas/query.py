"""Query request/response schemas."""

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Incoming query from the user."""

    question: str = Field(..., min_length=5, max_length=2000, description="User question")
    session_id: str | None = Field(
        default=None,
        description="Session ID for conversation continuity (generated if not provided)",
    )


class QueryResponse(BaseModel):
    """Response when query is answered directly (200)."""

    answer: str = Field(..., description="Generated answer")
    citations: list[dict] = Field(default_factory=list, description="Source citations")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Model confidence")
    trace_id: str = Field(..., description="Langfuse trace ID for observability")
    status: str = Field(..., description="answered | pending_review | rejected")


class QueryPendingResponse(BaseModel):
    """Response when query is routed to HITL review (202)."""

    review_item_id: str = Field(..., description="ID of the review queue item")
    message: str = Field(
        default="Answer pending compliance review",
        description="Human-readable status message",
    )
    session_id: str = Field(..., description="Session ID for polling")


class QueryStatusResponse(BaseModel):
    """Status response for polling endpoint."""

    status: str = Field(..., description="answered | pending_review | rejected")
    answer: str | None = Field(default=None, description="Final answer (if approved)")
    review_note: str | None = Field(
        default=None, description="Reviewer note (if rejected or overridden)"
    )
