from fastapi import APIRouter

from app.models.schemas import AuditEvent

router = APIRouter(prefix="/audit-log", tags=["audit-log"])


@router.get("", response_model=list[AuditEvent])
def list_audit_events() -> list[AuditEvent]:
    return [
        AuditEvent(
            id="evt_001",
            actor="system",
            action="indexed",
            target="FY2025 procurement controls.pdf",
            created_at="2026-06-02T14:02:00Z",
        ),
        AuditEvent(
            id="evt_002",
            actor="reviewer@auditsys.local",
            action="flagged",
            target="Vendor onboarding exceptions.xlsx",
            created_at="2026-06-02T14:21:00Z",
        ),
    ]
