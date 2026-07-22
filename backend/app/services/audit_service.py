"""Append-only audit log service.

All query interactions are logged for compliance. Entries are immutable
once written (no UPDATE/DELETE at the application level).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from loguru import logger

from app.core.database import get_supabase
from app.schemas.audit import AuditLogEntry, AuditLogFilter, AuditLogPage


async def create_audit_entry(
    *,
    session_id: str,
    user_id: str,
    query: str,
    answer: str | None,
    citations: list[dict],
    confidence_score: float,
    prompt_version: str,
    model_name: str,
    trace_id: str,
    status: str,
    review_item_id: str | None = None,
    pii_detected: bool = False,
    validation_passed: bool = True,
    validation_errors: list[str] | None = None,
) -> AuditLogEntry:
    """Insert a new audit log entry (append-only).

    Args:
        All fields required for a complete audit trail of a query interaction.

    Returns:
        The created AuditLogEntry with generated id and timestamp.
    """
    entry_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    record = {
        "id": entry_id,
        "session_id": session_id,
        "user_id": user_id,
        "query": query,
        "answer": answer,
        "citations": citations,
        "confidence_score": confidence_score,
        "prompt_version": prompt_version,
        "model_name": model_name,
        "trace_id": trace_id,
        "status": status,
        "review_item_id": review_item_id,
        "pii_detected": pii_detected,
        "validation_passed": validation_passed,
        "validation_errors": validation_errors or [],
        "created_at": now.isoformat(),
    }

    try:
        supabase = get_supabase()
        supabase.table("audit_log").insert(record).execute()
        logger.info("audit_entry_created id={} session_id={} status={}", entry_id, session_id, status)
    except Exception as exc:
        logger.error("audit_entry_insert_failed id={} error={}", entry_id, str(exc))
        raise

    return AuditLogEntry(
        id=entry_id,
        session_id=session_id,
        user_id=user_id,
        query=query,
        answer=answer,
        citations=citations,
        confidence_score=confidence_score,
        prompt_version=prompt_version,
        model_name=model_name,
        trace_id=trace_id,
        status=status,
        review_item_id=review_item_id,
        pii_detected=pii_detected,
        validation_passed=validation_passed,
        validation_errors=validation_errors or [],
        created_at=now,
    )


async def get_audit_log(
    filters: AuditLogFilter,
    page: int = 1,
    page_size: int = 20,
) -> AuditLogPage:
    """Retrieve paginated audit log entries with optional filters.

    Args:
        filters: AuditLogFilter with optional status, date range, confidence range, pii_only.
        page: Page number (1-indexed).
        page_size: Number of entries per page.

    Returns:
        AuditLogPage with entries, total count, and pagination info.
    """
    supabase = get_supabase()
    query = supabase.table("audit_log").select("*", count="exact")

    # Apply filters
    if filters.status:
        query = query.eq("status", filters.status)
    if filters.date_from:
        query = query.gte("created_at", filters.date_from.isoformat())
    if filters.date_to:
        query = query.lte("created_at", filters.date_to.isoformat())
    if filters.min_confidence is not None:
        query = query.gte("confidence_score", filters.min_confidence)
    if filters.max_confidence is not None:
        query = query.lte("confidence_score", filters.max_confidence)
    if filters.pii_only:
        query = query.eq("pii_detected", True)

    # Pagination
    offset = (page - 1) * page_size
    query = query.order("created_at", desc=True).range(offset, offset + page_size - 1)

    result = query.execute()
    total = result.count if result.count is not None else 0
    entries = [AuditLogEntry(**row) for row in (result.data or [])]

    return AuditLogPage(
        entries=entries,
        total=total,
        page=page,
        page_size=page_size,
        has_next=(offset + page_size) < total,
    )


async def get_audit_entry(entry_id: str) -> AuditLogEntry | None:
    """Retrieve a single audit log entry by ID.

    Returns:
        AuditLogEntry if found, None otherwise.
    """
    supabase = get_supabase()
    result = supabase.table("audit_log").select("*").eq("id", entry_id).execute()
    if result.data:
        return AuditLogEntry(**result.data[0])
    return None
