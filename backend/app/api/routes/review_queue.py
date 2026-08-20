from fastapi import APIRouter, HTTPException, Query

from app.schemas.review import ReviewOverrideRequest, ReviewRejectRequest
from app.services import review_service

router = APIRouter(prefix="/review-queue", tags=["review-queue"])


@router.get("")
async def list_review_items(
    status: str = "pending",
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> dict:
    return await review_service.list_review_items(status=status, page=page, page_size=page_size)


@router.get("/{item_id}")
async def get_review_item(item_id: str) -> dict:
    item = await review_service.get_review_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Review item not found")
    return item


@router.post("/{item_id}/approve")
async def approve_review_item(item_id: str) -> dict:
    item = await review_service.approve(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Review item not found")
    return item


@router.post("/{item_id}/reject")
async def reject_review_item(item_id: str, body: ReviewRejectRequest) -> dict:
    item = await review_service.reject(item_id, reason=body.reason)
    if item is None:
        raise HTTPException(status_code=404, detail="Review item not found")
    return item


@router.post("/{item_id}/override")
async def override_review_item(item_id: str, body: ReviewOverrideRequest) -> dict:
    item = await review_service.override(
        item_id, corrected_answer=body.corrected_answer, notes=body.notes
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Review item not found")
    return item
