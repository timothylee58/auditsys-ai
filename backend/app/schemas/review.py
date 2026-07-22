"""Review queue schemas."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ReviewAction(str, Enum):
    """Possible reviewer actions."""

    APPROVE = "approve"
    REJECT = "reject"
    OVERRIDE = "override"


class ReviewItem(BaseModel):
    """Single item in the compliance review queue."""

    id: str
    session_id: str
    user_id: str
    query: str
    draft_answer: str
    citations: list[dict] = Field(default_factory=list)
    confidence_score: float
    status: str = Field(..., description="pending | approved | rejected | overridden")
    reviewer_id: str | None = None
    reviewed_at: datetime | None = None
    reviewer_action: ReviewAction | None = None
    override_answer: str | None = None
    reviewer_notes: str | None = None
    created_at: datetime


class ReviewRejectRequest(BaseModel):
    """Request body for rejecting a review item."""

    reason: str = Field(..., min_length=5, description="Reason for rejection")


class ReviewOverrideRequest(BaseModel):
    """Request body for overriding a review item."""

    corrected_answer: str = Field(..., min_length=10, description="Corrected answer text")
    notes: str | None = Field(default=None, description="Reviewer notes")


class ReviewItemList(BaseModel):
    """Paginated review queue response."""

    items: list[ReviewItem]
    total: int
    page: int
    page_size: int
    has_next: bool
