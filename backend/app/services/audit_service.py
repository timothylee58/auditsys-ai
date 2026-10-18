"""
AuditSys AI -- Feature 4: Audit Log Service
===========================================
Append-only audit log. Enforced at two levels:

  1. Supabase RLS policy (DB level):
       CREATE POLICY "audit_log_insert_only"
       ON audit_log FOR INSERT
       TO authenticated
       WITH CHECK (auth.uid() = user_id);

       -- No UPDATE or DELETE policy = blocked by default

  2. Application level (this service):
       Only .insert() calls -- never .update() or .delete()

Every query through AuditSys generates exactly one audit log entry,
regardless of whether it was answered, routed to HITL, or errored.

Schema mirrors AgentState so entries are fully reproducible.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.database import get_async_supabase
from app.schemas.audit import AuditLogEntry, AuditLogFilter, AuditLogPage

# -- Write (append-only) -----------------------------------------------------------

async def write_audit_entry(
    session_id: str,
    user_id: str,
    query: str,
    answer: str | None,
    citations: list[dict[str, Any]],
    confidence_score: float,
    prompt_version: str,
    model_name: str,
    trace_id: str,
    status: str,
    review_item_id: str | None = None,
    pii_detected: bool = False,
    validation_passed: bool = True,
    validation_errors: list[str] | None = None,
) -> str:
    """
    Write one audit log entry. Returns the entry ID.
    This is the ONLY write operation this service exposes.
    """
    supabase = await get_async_supabase()
    entry_id = str(uuid.uuid4())

    await supabase.table("audit_log").insert({
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
        "created_at": datetime.now(UTC).isoformat(),
    }).execute()

    return entry_id


# -- Read (paginated) --------------------------------------------------------------

async def get_audit_log(
    user_id: str,
    filters: AuditLogFilter,
    page: int = 1,
    page_size: int = 50,
) -> AuditLogPage:
    """
    Paginated read of audit log entries for a user.
    Supports filtering by date range, status, and confidence threshold.
    """
    supabase = await get_async_supabase()
    offset = (page - 1) * page_size

    query = (
        supabase.table("audit_log")
        .select("*", count="exact")
        .eq("user_id", user_id)
    )

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

    query = query.order("created_at", desc=True).range(offset, offset + page_size - 1)

    response = await query.execute()

    entries = [AuditLogEntry(**row) for row in (response.data or [])]
    total = response.count or 0

    return AuditLogPage(
        entries=entries,
        total=total,
        page=page,
        page_size=page_size,
        has_next=offset + page_size < total,
    )


async def get_audit_entry(entry_id: str, user_id: str) -> AuditLogEntry | None:
    """Fetch a single audit entry. RLS ensures user can only see own entries."""
    supabase = await get_async_supabase()
    response = await (
        supabase.table("audit_log")
        .select("*")
        .eq("id", entry_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    if not response.data:
        return None
    return AuditLogEntry(**response.data)




# -- Backward compatibility with query_service.py ---------------------------------


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
    """Legacy wrapper for query_service.py compatibility."""
    entry_id = await write_audit_entry(
        session_id=session_id,
        user_id=user_id or "",
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
        validation_errors=validation_errors,
    )
    return {"id": entry_id}


# -- Immutability enforcement ------------------------------------------------------
# The canonical schema lives in backend/scripts/migrations.sql (mirrored into
# supabase/migrations/). audit_log is protected by:
#   1. RLS: service role may only INSERT/SELECT — no UPDATE/DELETE policy.
#   2. A BEFORE UPDATE/DELETE trigger raising an exception, which also covers
#      the service role (RLS is bypassed by service_role; the trigger is not).
# The application layer only ever calls .insert() on this table.
