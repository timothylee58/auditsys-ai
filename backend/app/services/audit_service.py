"""Append-only audit log service.

Every query, its answer, citations, confidence, and validation outcome is
recorded here. Rows are insert-only (see RLS policies in
scripts/migrations.sql) so the audit trail cannot be tampered with after
the fact.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger

from app.core.database import get_supabase

TABLE = "audit_log"


async def record_query(
    *,
    session_id: str,
    user_id: str | None,
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
) -> dict[str, Any]:
    """Insert one append-only audit log entry and return the stored row."""
    row = {
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
    }
    client = get_supabase()
    result = client.table(TABLE).insert(row).execute()
    logger.info("audit_log_recorded session_id={} status={}", session_id, status)
    return result.data[0] if result.data else row


async def get_audit_log(
    *,
    page: int = 1,
    page_size: int = 25,
    status: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    min_confidence: float | None = None,
    max_confidence: float | None = None,
    pii_only: bool = False,
) -> dict[str, Any]:
    """Return a paginated, filtered slice of the audit log, newest first."""
    client = get_supabase()
    query = client.table(TABLE).select("*", count="exact")

    if status:
        query = query.eq("status", status)
    if date_from:
        query = query.gte("created_at", date_from.isoformat())
    if date_to:
        query = query.lte("created_at", date_to.isoformat())
    if min_confidence is not None:
        query = query.gte("confidence_score", min_confidence)
    if max_confidence is not None:
        query = query.lte("confidence_score", max_confidence)
    if pii_only:
        query = query.eq("pii_detected", True)

    start = (page - 1) * page_size
    end = start + page_size - 1
    query = query.order("created_at", desc=True).range(start, end)

    result = query.execute()
    total = result.count or 0
    return {
        "entries": result.data or [],
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": start + page_size < total,
    }


async def get_audit_entry(entry_id: str) -> dict[str, Any] | None:
    client = get_supabase()
    result = client.table(TABLE).select("*").eq("id", entry_id).limit(1).execute()
    return result.data[0] if result.data else None
