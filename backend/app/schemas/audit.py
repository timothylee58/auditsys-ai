"""Audit log schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class AuditLogEntry(BaseModel):
    """Single entry in the append-only audit log."""

    id: str
    session_id: str
    user_id: str
    query: str
    answer: str | None = None
    citations: list[dict] = Field(default_factory=list)
    confidence_score: float
    prompt_version: str
    model_name: str
    trace_id: str
    status: str
    review_item_id: str | None = None
    pii_detected: bool = False
    validation_passed: bool = True
    validation_errors: list[str] = Field(default_factory=list)
    created_at: datetime


class AuditLogFilter(BaseModel):
    """Filter parameters for audit log queries."""

    status: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    min_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    max_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    pii_only: bool = False


class AuditLogPage(BaseModel):
    """Paginated audit log response."""

    entries: list[AuditLogEntry]
    total: int
    page: int
    page_size: int
    has_next: bool
