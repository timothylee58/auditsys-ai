from fastapi import APIRouter

from app.models.schemas import ReviewItem

router = APIRouter(prefix="/review-queue", tags=["review-queue"])


@router.get("", response_model=list[ReviewItem])
def list_review_items() -> list[ReviewItem]:
    return [
        ReviewItem(
            id="rev_001",
            title="Missing dual approval evidence for vendor payment batch",
            severity="high",
            assignee="Timothy Lee",
        ),
        ReviewItem(
            id="rev_002",
            title="Policy clause mismatch in procurement threshold",
            severity="medium",
            assignee="Audit Lead",
        ),
    ]
