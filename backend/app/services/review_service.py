"""
AuditSys AI -- Feature 5: Human-in-the-Loop Review Service
==========================================================
When agent confidence < threshold, answers go to review_queue.
Human reviewers approve/reject/override before answer is released.

API behaviour:
  - POST /query -> 202 Accepted + {review_item_id} when routed to HITL
  - GET  /review         -> list pending items for reviewer
  - POST /review/{id}/approve  -> releases answer to user
  - POST /review/{id}/reject   -> discards answer, user notified
  - POST /review/{id}/override -> reviewer writes corrected answer

All review actions are logged to audit_log (separate entry per action).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.database import get_supabase
from app.schemas.review import (
    ReviewAction,
    ReviewItem,
    ReviewItemList,
    ReviewOverrideRequest,
)


# -- Queue management --------------------------------------------------------------

async def get_pending_reviews(
    reviewer_user_id: str,
    page: int = 1,
    page_size: int = 20,
) -> ReviewItemList:
    """
    List pending review items for a reviewer.
    In production: filter by reviewer's assigned subsidiaries.
    """
    supabase = get_supabase()
    offset = (page - 1) * page_size

    response = await (
        supabase.table("review_queue")
        .select("*", count="exact")
        .eq("status", "pending")
        .order("created_at", desc=False)   # oldest first -- FIFO queue
        .range(offset, offset + page_size - 1)
        .execute()
    )

    items = [ReviewItem(**row) for row in (response.data or [])]
    total = response.count or 0

    return ReviewItemList(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=offset + page_size < total,
    )


async def get_review_item(
    item_id: str,
    reviewer_user_id: str,
) -> ReviewItem | None:
    """Fetch a single review item."""
    supabase = get_supabase()
    response = await (
        supabase.table("review_queue")
        .select("*")
        .eq("id", item_id)
        .single()
        .execute()
    )
    if not response.data:
        return None
    return ReviewItem(**response.data)


# -- Review actions -----------------------------------------------------------------

async def approve_review_item(
    item_id: str,
    reviewer_user_id: str,
) -> ReviewItem:
    """
    Approve answer for release to user.
    Updates review_queue status -> 'approved'.
    The polling endpoint (GET /query/status/{session_id}) picks this up.
    """
    return await _update_review_status(
        item_id=item_id,
        reviewer_user_id=reviewer_user_id,
        new_status="approved",
        action=ReviewAction.APPROVE,
    )


async def reject_review_item(
    item_id: str,
    reviewer_user_id: str,
    rejection_reason: str,
) -> ReviewItem:
    """
    Reject answer -- user will receive a 'cannot answer' response.
    Logs rejection reason for audit trail.
    """
    return await _update_review_status(
        item_id=item_id,
        reviewer_user_id=reviewer_user_id,
        new_status="rejected",
        action=ReviewAction.REJECT,
        reviewer_notes=rejection_reason,
    )


async def override_review_item(
    item_id: str,
    reviewer_user_id: str,
    request: ReviewOverrideRequest,
) -> ReviewItem:
    """
    Reviewer writes a corrected answer.
    Corrected answer + original draft both stored for audit.
    """
    supabase = get_supabase()
    now = datetime.now(timezone.utc).isoformat()

    response = await (
        supabase.table("review_queue")
        .update({
            "status": "overridden",
            "reviewer_id": reviewer_user_id,
            "reviewed_at": now,
            "reviewer_action": ReviewAction.OVERRIDE,
            "override_answer": request.corrected_answer,
            "reviewer_notes": request.notes,
        })
        .eq("id", item_id)
        .eq("status", "pending")   # can only override pending items
        .execute()
    )

    if not response.data:
        raise ValueError(f"Review item {item_id} not found or already reviewed")

    # Write audit entry for the override action
    await _log_review_action(
        item_id=item_id,
        reviewer_user_id=reviewer_user_id,
        action=ReviewAction.OVERRIDE,
        notes=request.notes,
        corrected_answer=request.corrected_answer,
    )

    return ReviewItem(**response.data[0])


# -- Status polling (for async HITL flow) ------------------------------------------

async def get_query_status(
    session_id: str,
    user_id: str,
) -> dict[str, Any]:
    """
    Called by frontend polling GET /query/status/{session_id}.
    Returns current status + answer if approved/overridden.
    """
    supabase = get_supabase()

    response = await (
        supabase.table("review_queue")
        .select("status,draft_answer,override_answer,reviewer_notes")
        .eq("session_id", session_id)
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not response.data:
        return {"status": "not_found"}

    item = response.data[0]
    status = item["status"]

    if status == "approved":
        return {
            "status": "answered",
            "answer": item["draft_answer"],
            "review_note": "Answer verified by compliance reviewer.",
        }
    elif status == "overridden":
        return {
            "status": "answered",
            "answer": item["override_answer"],
            "review_note": "Answer provided by compliance reviewer.",
        }
    elif status == "rejected":
        return {
            "status": "rejected",
            "answer": None,
            "review_note": item.get("reviewer_notes", "Answer could not be verified."),
        }
    else:
        return {"status": "pending_review"}


# -- Internal helpers ---------------------------------------------------------------

async def _update_review_status(
    item_id: str,
    reviewer_user_id: str,
    new_status: str,
    action: ReviewAction,
    reviewer_notes: str | None = None,
) -> ReviewItem:
    supabase = get_supabase()
    now = datetime.now(timezone.utc).isoformat()

    response = await (
        supabase.table("review_queue")
        .update({
            "status": new_status,
            "reviewer_id": reviewer_user_id,
            "reviewed_at": now,
            "reviewer_action": action,
            "reviewer_notes": reviewer_notes,
        })
        .eq("id", item_id)
        .eq("status", "pending")
        .execute()
    )

    if not response.data:
        raise ValueError(f"Review item {item_id} not found or already reviewed")

    await _log_review_action(
        item_id=item_id,
        reviewer_user_id=reviewer_user_id,
        action=action,
        notes=reviewer_notes,
    )

    return ReviewItem(**response.data[0])


async def _log_review_action(
    item_id: str,
    reviewer_user_id: str,
    action: ReviewAction,
    notes: str | None = None,
    corrected_answer: str | None = None,
) -> None:
    """Write a separate audit log entry for each review action."""
    from app.services.audit_service import write_audit_entry

    await write_audit_entry(
        session_id=str(uuid.uuid4()),
        user_id=reviewer_user_id,
        query=f"[REVIEW ACTION] item_id={item_id}",
        answer=corrected_answer,
        citations=[],
        confidence_score=1.0,     # reviewer-provided answers have full confidence
        prompt_version="human-review",
        model_name="human",
        trace_id=str(uuid.uuid4()),
        status=f"review_{action}",
        review_item_id=item_id,
    )
