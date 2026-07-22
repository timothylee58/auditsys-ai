"""Audit log routes — immutable compliance trail.

Endpoints:
- GET /audit — Paginated audit log with filters
- GET /audit/{id} — Single audit entry
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from loguru import logger

from app.schemas.audit import AuditLogEntry, AuditLogFilter, AuditLogPage
from app.services.audit_service import get_audit_entry, get_audit_log

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=AuditLogPage)
async def list_audit_entries(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status: str | None = Query(default=None, description="Filter by status"),
    date_from: datetime | None = Query(default=None, description="Filter entries from this date"),
    date_to: datetime | None = Query(default=None, description="Filter entries up to this date"),
    min_confidence: float | None = Query(
        default=None, ge=0.0, le=1.0, description="Minimum confidence score"
    ),
    max_confidence: float | None = Query(
        default=None, ge=0.0, le=1.0, description="Maximum confidence score"
    ),
    pii_only: bool = Query(default=False, description="Show only entries with PII detected"),
) -> AuditLogPage:
    """Retrieve paginated audit log entries with optional filters.

    Supports filtering by status, date range, confidence range,
    and PII detection flag. Results are ordered by timestamp (newest first).
    """
    filters = AuditLogFilter(
        status=status,
        date_from=date_from,
        date_to=date_to,
        min_confidence=min_confidence,
        max_confidence=max_confidence,
        pii_only=pii_only,
    )

    return await get_audit_log(filters=filters, page=page, page_size=page_size)


@router.get("/{entry_id}", response_model=AuditLogEntry)
async def get_single_audit_entry(entry_id: str) -> AuditLogEntry:
    """Retrieve a single audit log entry by its unique ID.

    Returns:
        200: AuditLogEntry with full details.

    Raises:
        404: Entry not found.
    """
    entry = await get_audit_entry(entry_id)
    if not entry:
        raise HTTPException(
            status_code=404,
            detail={
                "type": "https://auditsys.ai/errors/audit-entry-not-found",
                "title": "Audit Entry Not Found",
                "status": 404,
                "detail": f"Audit log entry '{entry_id}' does not exist.",
            },
        )
    return entry
