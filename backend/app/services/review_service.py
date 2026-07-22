"""Human-in-the-loop (HITL) review queue service.

Manages items flagged for compliance review when confidence is below threshold
or guardrails detect potential issues.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from loguru import logger

from app.core.database import get_supabase
from app.schemas.review import ReviewAction, ReviewItem, ReviewItemList


async def create_review_item(
    *,
    session_id: str,
    user_id: str,
    query: str,
    draft_answer: str,
    citations: list[dict],
    confidence_score: float,
) -> ReviewItem:
    """Queue an answer for compliance review.

    Args:
        session_id: Conversation session ID.
        user_id: User who submitted the query.
        query: The original question.
        draft_answer: The AI-generated answer to review.
        citations: Source citations for the draft answer.
        confidence_score: Model confidence that triggered the review.

    Returns:
        The created ReviewItem with generated id and timestamp.
    """
    item_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    record = {
        "id": item_id,
        "session_id": session_id,
        "user_id": user_id,
        "query": query,
        "draft_answer": draft_answer,
        "citations": citations,
        "confidence_score": confidence_score,
        "status": "pending",
        "created_at": now.isoformat(),
    }

    try:
        supabase = get_supabase()
        supabase.table("review_queue").insert(record).execute()
        logger.info(
            "review_item_created id={} session_id={} confidence={:.2f}",
            item_id,
            session_id,
            confidence_score,
        )
    except Exception as exc:
        logger.error("review_item_insert_failed id={} error={}", item_id, str(exc))
        raise

    return ReviewItem(
        id=item_id,
        session_id=session_id,
        user_id=user_id,
        query=query,
        draft_answer=draft_answer,
        citations=citations,
        confidence_score=confidence_score,
        status="pending",
        reviewer_id=None,
        reviewed_at=None,
        reviewer_action=None,
        override_answer=None,
        reviewer_notes=None,
        created_at=now,
    )


async def get_pending_reviews(page: int = 1, page_size: int = 20) -> ReviewItemList:
    """List pending review items (paginated).

    Args:
        page: Page number (1-indexed).
        page_size: Items per page.

    Returns:
        ReviewItemList with items, total, and pagination metadata.
    """
    supabase = get_supabase()
    offset = (page - 1) * page_size

    result = (
        supabase.table("review_queue")
        .select("*", count="exact")
        .eq("status", "pending")
        .order("created_at", desc=True)
        .range(offset, offset + page_size - 1)
        .execute()
    )

    total = result.count if result.count is not None else 0
    items = [ReviewItem(**row) for row in (result.data or [])]

    return ReviewItemList(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=(offset + page_size) < total,
    )


async def get_review_item(item_id: str) -> ReviewItem | None:
    """Retrieve a single review item by ID.

    Returns:
        ReviewItem if found, None otherwise.
    """
    supabase = get_supabase()
    result = supabase.table("review_queue").select("*").eq("id", item_id).execute()
    if result.data:
        return ReviewItem(**result.data[0])
    return None


async def approve_review(item_id: str, reviewer_id: str) -> ReviewItem | None:
    """Approve a pending review item.

    Args:
        item_id: The review item to approve.
        reviewer_id: The reviewer performing the action.

    Returns:
        Updated ReviewItem or None if not found.
    """
    now = datetime.now(timezone.utc)
    supabase = get_supabase()

    result = (
        supabase.table("review_queue")
        .update(
            {
                "status": "approved",
                "reviewer_id": reviewer_id,
                "reviewed_at": now.isoformat(),
                "reviewer_action": ReviewAction.APPROVE.value,
            }
        )
        .eq("id", item_id)
        .eq("status", "pending")
        .execute()
    )

    if result.data:
        logger.info("review_approved id={} reviewer={}", item_id, reviewer_id)
        return ReviewItem(**result.data[0])

    logger.warning("review_approve_failed id={} (not found or already actioned)", item_id)
    return None


async def reject_review(item_id: str, reviewer_id: str, reason: str) -> ReviewItem | None:
    """Reject a pending review item.

    Args:
        item_id: The review item to reject.
        reviewer_id: The reviewer performing the action.
        reason: Reason for rejection.

    Returns:
        Updated ReviewItem or None if not found.
    """
    now = datetime.now(timezone.utc)
    supabase = get_supabase()

    result = (
        supabase.table("review_queue")
        .update(
            {
                "status": "rejected",
                "reviewer_id": reviewer_id,
                "reviewed_at": now.isoformat(),
                "reviewer_action": ReviewAction.REJECT.value,
                "reviewer_notes": reason,
            }
        )
        .eq("id", item_id)
        .eq("status", "pending")
        .execute()
    )

    if result.data:
        logger.info("review_rejected id={} reviewer={} reason={}", item_id, reviewer_id, reason[:50])
        return ReviewItem(**result.data[0])

    logger.warning("review_reject_failed id={} (not found or already actioned)", item_id)
    return None


async def override_review(
    item_id: str,
    reviewer_id: str,
    corrected_answer: str,
    notes: str | None = None,
) -> ReviewItem | None:
    """Override a pending review item with a corrected answer.

    Args:
        item_id: The review item to override.
        reviewer_id: The reviewer performing the action.
        corrected_answer: The reviewer's corrected answer.
        notes: Optional reviewer notes.

    Returns:
        Updated ReviewItem or None if not found.
    """
    now = datetime.now(timezone.utc)
    supabase = get_supabase()

    result = (
        supabase.table("review_queue")
        .update(
            {
                "status": "overridden",
                "reviewer_id": reviewer_id,
                "reviewed_at": now.isoformat(),
                "reviewer_action": ReviewAction.OVERRIDE.value,
                "override_answer": corrected_answer,
                "reviewer_notes": notes,
            }
        )
        .eq("id", item_id)
        .eq("status", "pending")
        .execute()
    )

    if result.data:
        logger.info("review_overridden id={} reviewer={}", item_id, reviewer_id)
        return ReviewItem(**result.data[0])

    logger.warning("review_override_failed id={} (not found or already actioned)", item_id)
    return None


async def get_query_status(session_id: str) -> dict:
    """Get the current status of a query by session_id.

    Checks the review queue for the most recent item with this session_id.

    Returns:
        Dict with status, answer (if approved/overridden), and review_note.
    """
    supabase = get_supabase()
    result = (
        supabase.table("review_queue")
        .select("*")
        .eq("session_id", session_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not result.data:
        return {"status": "not_found", "answer": None, "review_note": None}

    item = result.data[0]
    status = item["status"]

    if status == "approved":
        return {
            "status": "answered",
            "answer": item["draft_answer"],
            "review_note": None,
        }
    elif status == "overridden":
        return {
            "status": "answered",
            "answer": item["override_answer"],
            "review_note": item.get("reviewer_notes"),
        }
    elif status == "rejected":
        return {
            "status": "rejected",
            "answer": None,
            "review_note": item.get("reviewer_notes"),
        }
    else:
        return {"status": "pending_review", "answer": None, "review_note": None}
