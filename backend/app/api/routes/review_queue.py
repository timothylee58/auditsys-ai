from fastapi import APIRouter, HTTPException, Query

from app.schemas.review import ReviewOverrideRequest, ReviewRejectRequest
from app.services import review_service

router = APIRouter(prefix="/review-queue", tags=["review-queue"])


@router.get("")
async def list_pending_reviews(
    reviewer_user_id: str = Query(..., description="Reviewer user ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return await review_service.get_pending_reviews(reviewer_user_id, page, page_size)


@router.get("/status/{session_id}")
async def get_query_status(
    session_id: str,
    user_id: str = Query(..., description="User ID for scoped access"),
):
    return await review_service.get_query_status(session_id, user_id)


@router.get("/{item_id}")
async def get_review_item(
    item_id: str,
    reviewer_user_id: str = Query(..., description="Reviewer user ID"),
):
    item = await review_service.get_review_item(item_id, reviewer_user_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Review item not found")
    return item


@router.post("/{item_id}/approve")
async def approve_review_item(
    item_id: str,
    reviewer_user_id: str = Query(..., description="Reviewer user ID"),
):
    try:
        return await review_service.approve_review_item(item_id, reviewer_user_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/{item_id}/reject")
async def reject_review_item(
    item_id: str,
    body: ReviewRejectRequest,
    reviewer_user_id: str = Query(..., description="Reviewer user ID"),
):
    try:
        return await review_service.reject_review_item(
            item_id, reviewer_user_id, body.reason
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/{item_id}/override")
async def override_review_item(
    item_id: str,
    body: ReviewOverrideRequest,
    reviewer_user_id: str = Query(..., description="Reviewer user ID"),
):
    try:
        return await review_service.override_review_item(
            item_id, reviewer_user_id, body
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
