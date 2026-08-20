from datetime import datetime

from pydantic import BaseModel


class AuditLogEntry(BaseModel):
    id: str
    session_id: str
    user_id: str | None = None
    query: str
    answer: str | None = None
    citations: list[dict]
    confidence_score: float | None = None
    prompt_version: str | None = None
    model_name: str | None = None
    trace_id: str | None = None
    status: str
    review_item_id: str | None = None
    pii_detected: bool
    validation_passed: bool
    validation_errors: list[str]
    created_at: datetime


class AuditLogFilter(BaseModel):
    status: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    min_confidence: float | None = None
    max_confidence: float | None = None
    pii_only: bool = False


class AuditLogPage(BaseModel):
    entries: list[AuditLogEntry]
    total: int
    page: int
    page_size: int
    has_next: bool
