from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from app.services import audit_service

router = APIRouter(prefix="/audit-log", tags=["audit-log"])


@router.get("")
async def list_audit_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    status: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    min_confidence: float | None = Query(None, ge=0, le=1),
    pii_only: bool = False,
) -> dict:
    """Paginated, filterable view over the append-only audit log."""
    return await audit_service.get_audit_log(
        page=page,
        page_size=page_size,
        status=status,
        date_from=date_from,
        date_to=date_to,
        min_confidence=min_confidence,
        pii_only=pii_only,
    )


@router.get("/{entry_id}")
async def get_audit_event(entry_id: str) -> dict:
    entry = await audit_service.get_audit_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Audit log entry not found")
    return entry
