from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ReviewAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    OVERRIDE = "override"


class ReviewItem(BaseModel):
    id: str
    session_id: str
    user_id: str | None = None
    query: str
    draft_answer: str
    citations: list[dict]
    confidence_score: float | None = None
    status: str
    reviewer_id: str | None = None
    reviewed_at: datetime | None = None
    reviewer_action: ReviewAction | None = None
    override_answer: str | None = None
    reviewer_notes: str | None = None
    created_at: datetime


class ReviewRejectRequest(BaseModel):
    reason: str = Field(..., min_length=3)


class ReviewOverrideRequest(BaseModel):
    corrected_answer: str = Field(..., min_length=10)
    notes: str | None = None


class ReviewItemList(BaseModel):
    items: list[ReviewItem]
    total: int
    page: int
    page_size: int
    has_next: bool
