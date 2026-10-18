from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import CurrentUser, get_current_user
from app.schemas.audit import AuditLogEntry, AuditLogFilter, AuditLogPage
from app.services import audit_service

router = APIRouter(prefix="/audit-log", tags=["audit-log"])


@router.get("", response_model=AuditLogPage)
async def list_audit_events(
    user: CurrentUser = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    min_confidence: float | None = Query(None, ge=0, le=1),
    max_confidence: float | None = Query(None, ge=0, le=1),
    pii_only: bool = False,
) -> AuditLogPage:
    """Paginated, filterable view over the append-only audit log.

    Always scoped to the authenticated caller; the previous ``user_id`` query
    parameter let any caller read anyone's audit trail.
    """
    filters = AuditLogFilter(
        status=status,
        date_from=date_from,
        date_to=date_to,
        min_confidence=min_confidence,
        max_confidence=max_confidence,
        pii_only=pii_only,
    )
    return await audit_service.get_audit_log(user.user_id, filters, page, page_size)


@router.get("/{entry_id}")
async def get_audit_event(
    entry_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> AuditLogEntry:
    entry = await audit_service.get_audit_entry(entry_id, user.user_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Audit log entry not found") from None
    return entry
