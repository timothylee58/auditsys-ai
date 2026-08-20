"""Human-in-the-loop (HITL) review queue service.

Low-confidence or otherwise-flagged answers are parked here instead of
being returned directly to the user. A reviewer approves, rejects, or
overrides the draft answer; the outcome is written back to the audit log.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from loguru import logger

from app.core.database import get_supabase

TABLE = "review_queue"


async def create_review_item(
    *,
    session_id: str,
    user_id: str | None,
    query: str,
    draft_answer: str,
    citations: list[dict],
    confidence_score: float,
) -> dict[str, Any]:
    row = {
        "session_id": session_id,
        "user_id": user_id,
        "query": query,
        "draft_answer": draft_answer,
        "citations": citations,
        "confidence_score": confidence_score,
        "status": "pending",
    }
    client = get_supabase()
    result = client.table(TABLE).insert(row).execute()
    item = result.data[0] if result.data else row
    logger.info("review_item_created session_id={} confidence={:.2f}", session_id, confidence_score)
    return item


async def list_review_items(
    *, status: str = "pending", page: int = 1, page_size: int = 25
) -> dict[str, Any]:
    client = get_supabase()
    start = (page - 1) * page_size
    end = start + page_size - 1
    query = client.table(TABLE).select("*", count="exact")
    if status:
        query = query.eq("status", status)
    result = query.order("created_at", desc=True).range(start, end).execute()
    total = result.count or 0
    return {
        "items": result.data or [],
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": start + page_size < total,
    }


async def get_review_item(item_id: str) -> dict[str, Any] | None:
    client = get_supabase()
    result = client.table(TABLE).select("*").eq("id", item_id).limit(1).execute()
    return result.data[0] if result.data else None


async def _resolve(
    item_id: str,
    *,
    action: str,
    status: str,
    reviewer_id: str | None,
    override_answer: str | None = None,
    reviewer_notes: str | None = None,
) -> dict[str, Any] | None:
    client = get_supabase()
    patch = {
        "status": status,
        "reviewer_id": reviewer_id,
        "reviewer_action": action,
        "reviewed_at": datetime.now(UTC).isoformat(),
        "override_answer": override_answer,
        "reviewer_notes": reviewer_notes,
    }
    result = client.table(TABLE).update(patch).eq("id", item_id).execute()
    logger.info("review_item_resolved id={} action={}", item_id, action)
    return result.data[0] if result.data else None


async def approve(item_id: str, *, reviewer_id: str | None = None) -> dict[str, Any] | None:
    return await _resolve(item_id, action="approve", status="approved", reviewer_id=reviewer_id)


async def reject(
    item_id: str, *, reason: str, reviewer_id: str | None = None
) -> dict[str, Any] | None:
    return await _resolve(
        item_id, action="reject", status="rejected", reviewer_id=reviewer_id, reviewer_notes=reason
    )


async def override(
    item_id: str,
    *,
    corrected_answer: str,
    notes: str | None = None,
    reviewer_id: str | None = None,
) -> dict[str, Any] | None:
    return await _resolve(
        item_id,
        action="override",
        status="overridden",
        reviewer_id=reviewer_id,
        override_answer=corrected_answer,
        reviewer_notes=notes,
    )


async def get_query_status(session_id: str) -> dict[str, Any]:
    """Poll target for the frontend: has a pending review been resolved?"""
    client = get_supabase()
    result = (
        client.table(TABLE)
        .select("*")
        .eq("session_id", session_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return {"status": "answered", "answer": None, "review_note": None}

    item = result.data[0]
    if item["status"] == "pending":
        return {"status": "pending_review", "answer": None, "review_note": None}
    if item["status"] == "rejected":
        return {"status": "rejected", "answer": None, "review_note": item.get("reviewer_notes")}
    if item["status"] == "overridden":
        return {
            "status": "answered",
            "answer": item.get("override_answer"),
            "review_note": item.get("reviewer_notes"),
        }
    # approved
    return {"status": "answered", "answer": item.get("draft_answer"), "review_note": None}
