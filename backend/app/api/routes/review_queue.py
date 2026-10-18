from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import CurrentUser, get_current_user
from app.schemas.review import ReviewOverrideRequest, ReviewRejectRequest
from app.services import review_service

router = APIRouter(prefix="/review-queue", tags=["review-queue"])


@router.get("")
async def list_pending_reviews(
    user: CurrentUser = Depends(get_current_user),
    page: int = 1,
    page_size: int = 20,
):
    """List pending review items. The reviewer identity comes from the
    verified token, not a client-supplied query parameter."""
    return await review_service.get_pending_reviews(user.user_id, page, page_size)


@router.get("/status/{session_id}")
async def get_query_status(
    session_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    return await review_service.get_query_status(session_id, user.user_id)


@router.get("/{item_id}")
async def get_review_item(
    item_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    item = await review_service.get_review_item(item_id, user.user_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Review item not found") from None
    return item


@router.post("/{item_id}/approve")
async def approve_review_item(
    item_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    try:
        return await review_service.approve_review_item(item_id, user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None


@router.post("/{item_id}/reject")
async def reject_review_item(
    item_id: str,
    body: ReviewRejectRequest,
    user: CurrentUser = Depends(get_current_user),
):
    try:
        return await review_service.reject_review_item(item_id, user.user_id, body.reason)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None


@router.post("/{item_id}/override")
async def override_review_item(
    item_id: str,
    body: ReviewOverrideRequest,
    user: CurrentUser = Depends(get_current_user),
):
    try:
        return await review_service.override_review_item(item_id, user.user_id, body)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
