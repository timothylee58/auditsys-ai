"""Review queue routes — Human-in-the-Loop compliance review.

Endpoints:
- GET /review — List pending review items
- GET /review/{id} — Single review item
- POST /review/{id}/approve — Approve a pending item
- POST /review/{id}/reject — Reject with reason
- POST /review/{id}/override — Override with corrected answer
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from loguru import logger

from app.schemas.review import (
    ReviewItem,
    ReviewItemList,
    ReviewOverrideRequest,
    ReviewRejectRequest,
)
from app.services.review_service import (
    approve_review,
    get_pending_reviews,
    get_review_item,
    override_review,
    reject_review,
)

router = APIRouter(prefix="/review", tags=["review"])


@router.get("", response_model=ReviewItemList)
async def list_pending_reviews(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
) -> ReviewItemList:
    """List items in the compliance review queue.

    Returns only pending items (not yet approved/rejected/overridden),
    ordered by creation date (newest first).
    """
    return await get_pending_reviews(page=page, page_size=page_size)


@router.get("/{item_id}", response_model=ReviewItem)
async def get_single_review_item(item_id: str) -> ReviewItem:
    """Retrieve a single review item by its unique ID.

    Returns:
        200: ReviewItem with full details.

    Raises:
        404: Item not found.
    """
    item = await get_review_item(item_id)
    if not item:
        raise HTTPException(
            status_code=404,
            detail={
                "type": "https://auditsys.ai/errors/review-item-not-found",
                "title": "Review Item Not Found",
                "status": 404,
                "detail": f"Review item '{item_id}' does not exist.",
            },
        )
    return item


@router.post("/{item_id}/approve", response_model=ReviewItem)
async def approve_item(item_id: str) -> ReviewItem:
    """Approve a pending review item.

    Marks the item as approved, releasing the draft answer to the user.
    The reviewer is identified from the auth context.

    Returns:
        200: Updated ReviewItem.

    Raises:
        404: Item not found or already actioned.
    """
    reviewer_id = "reviewer@auditsys.local"  # TODO: extract from auth token

    result = await approve_review(item_id=item_id, reviewer_id=reviewer_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail={
                "type": "https://auditsys.ai/errors/review-action-failed",
                "title": "Review Action Failed",
                "status": 404,
                "detail": f"Review item '{item_id}' not found or already actioned.",
            },
        )

    return result


@router.post("/{item_id}/reject", response_model=ReviewItem)
async def reject_item(item_id: str, body: ReviewRejectRequest) -> ReviewItem:
    """Reject a pending review item.

    Marks the item as rejected. The user will be notified that their
    query could not be answered.

    Returns:
        200: Updated ReviewItem.

    Raises:
        404: Item not found or already actioned.
    """
    reviewer_id = "reviewer@auditsys.local"  # TODO: extract from auth token

    result = await reject_review(
        item_id=item_id,
        reviewer_id=reviewer_id,
        reason=body.reason,
    )
    if not result:
        raise HTTPException(
            status_code=404,
            detail={
                "type": "https://auditsys.ai/errors/review-action-failed",
                "title": "Review Action Failed",
                "status": 404,
                "detail": f"Review item '{item_id}' not found or already actioned.",
            },
        )

    return result


@router.post("/{item_id}/override", response_model=ReviewItem)
async def override_item(item_id: str, body: ReviewOverrideRequest) -> ReviewItem:
    """Override a pending review item with a corrected answer.

    The reviewer provides a corrected answer that replaces the AI-generated
    draft. This is used when the AI answer was partially correct but needed
    human correction.

    Returns:
        200: Updated ReviewItem with override_answer set.

    Raises:
        404: Item not found or already actioned.
    """
    reviewer_id = "reviewer@auditsys.local"  # TODO: extract from auth token

    result = await override_review(
        item_id=item_id,
        reviewer_id=reviewer_id,
        corrected_answer=body.corrected_answer,
        notes=body.notes,
    )
    if not result:
        raise HTTPException(
            status_code=404,
            detail={
                "type": "https://auditsys.ai/errors/review-action-failed",
                "title": "Review Action Failed",
                "status": 404,
                "detail": f"Review item '{item_id}' not found or already actioned.",
            },
        )

    return result
