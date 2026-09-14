"""Tests for the audit log service (Feature 4)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.audit import AuditLogEntry, AuditLogFilter, AuditLogPage
from app.services import audit_service

# -- Helpers -------------------------------------------------------------------


def _make_chain_mock(response_data=None, response_count=None):
    """
    Build a mock that supports Supabase's chained-method pattern.
    Each method returns the same mock so .table().select().eq()... works,
    and .execute() returns an AsyncMock with the specified response.
    """
    mock = MagicMock()
    execute_response = MagicMock()
    execute_response.data = response_data
    execute_response.count = response_count

    # Make execute() async
    mock.execute = AsyncMock(return_value=execute_response)

    # Every chainable method returns the same mock
    for method in (
        "table", "select", "insert", "update", "delete",
        "eq", "neq", "gte", "lte", "gt", "lt",
        "order", "range", "limit", "single",
    ):
        getattr(mock, method).return_value = mock

    return mock


def _sample_audit_row(entry_id: str = "entry-1") -> dict:
    return {
        "id": entry_id,
        "session_id": "session-1",
        "user_id": "user-1",
        "query": "What is the policy?",
        "answer": "The policy states...",
        "citations": [{"source": "doc1.pdf", "page": 3}],
        "confidence_score": 0.85,
        "prompt_version": "v1.0",
        "model_name": "gpt-4",
        "trace_id": "trace-1",
        "status": "answered",
        "review_item_id": None,
        "pii_detected": False,
        "validation_passed": True,
        "validation_errors": [],
        "created_at": datetime.now(UTC).isoformat(),
    }


# -- Tests: write_audit_entry --------------------------------------------------


@pytest.mark.asyncio
async def test_write_audit_entry_returns_entry_id():
    chain = _make_chain_mock(response_data=[_sample_audit_row()])

    with patch("app.services.audit_service.get_supabase", return_value=chain):
        entry_id = await audit_service.write_audit_entry(
            session_id="session-1",
            user_id="user-1",
            query="What is the policy?",
            answer="The policy states...",
            citations=[{"source": "doc1.pdf", "page": 3}],
            confidence_score=0.85,
            prompt_version="v1.0",
            model_name="gpt-4",
            trace_id="trace-1",
            status="answered",
        )

    assert isinstance(entry_id, str)
    assert len(entry_id) > 0
    # Verify insert was called
    chain.table.assert_called_with("audit_log")
    chain.insert.assert_called_once()


@pytest.mark.asyncio
async def test_write_audit_entry_with_optional_fields():
    chain = _make_chain_mock(response_data=[_sample_audit_row()])

    with patch("app.services.audit_service.get_supabase", return_value=chain):
        entry_id = await audit_service.write_audit_entry(
            session_id="session-2",
            user_id="user-2",
            query="PII question?",
            answer=None,
            citations=[],
            confidence_score=0.3,
            prompt_version="v1.0",
            model_name="gpt-4",
            trace_id="trace-2",
            status="pending_review",
            review_item_id="review-1",
            pii_detected=True,
            validation_passed=False,
            validation_errors=["PII found in query"],
        )

    assert isinstance(entry_id, str)
    insert_call_args = chain.insert.call_args[0][0]
    assert insert_call_args["pii_detected"] is True
    assert insert_call_args["validation_passed"] is False
    assert insert_call_args["validation_errors"] == ["PII found in query"]
    assert insert_call_args["review_item_id"] == "review-1"


# -- Tests: get_audit_log ------------------------------------------------------


@pytest.mark.asyncio
async def test_get_audit_log_returns_paginated_results():
    rows = [_sample_audit_row("entry-1"), _sample_audit_row("entry-2")]
    chain = _make_chain_mock(response_data=rows, response_count=2)

    with patch("app.services.audit_service.get_supabase", return_value=chain):
        result = await audit_service.get_audit_log(
            user_id="user-1",
            filters=AuditLogFilter(),
            page=1,
            page_size=50,
        )

    assert isinstance(result, AuditLogPage)
    assert result.total == 2
    assert result.page == 1
    assert result.page_size == 50
    assert result.has_next is False
    assert len(result.entries) == 2
    assert all(isinstance(e, AuditLogEntry) for e in result.entries)


@pytest.mark.asyncio
async def test_get_audit_log_with_filters():
    chain = _make_chain_mock(response_data=[], response_count=0)

    filters = AuditLogFilter(
        status="answered",
        date_from=datetime(2024, 1, 1, tzinfo=UTC),
        date_to=datetime(2024, 12, 31, tzinfo=UTC),
        min_confidence=0.5,
        max_confidence=0.9,
        pii_only=True,
    )

    with patch("app.services.audit_service.get_supabase", return_value=chain):
        result = await audit_service.get_audit_log(
            user_id="user-1",
            filters=filters,
            page=1,
            page_size=25,
        )

    assert isinstance(result, AuditLogPage)
    assert result.total == 0
    assert result.entries == []


@pytest.mark.asyncio
async def test_get_audit_log_has_next_true():
    rows = [_sample_audit_row(f"entry-{i}") for i in range(10)]
    chain = _make_chain_mock(response_data=rows, response_count=25)

    with patch("app.services.audit_service.get_supabase", return_value=chain):
        result = await audit_service.get_audit_log(
            user_id="user-1",
            filters=AuditLogFilter(),
            page=1,
            page_size=10,
        )

    assert result.has_next is True
    assert result.total == 25


# -- Tests: get_audit_entry -----------------------------------------------------


@pytest.mark.asyncio
async def test_get_audit_entry_found():
    row = _sample_audit_row("entry-1")
    chain = _make_chain_mock(response_data=row)

    with patch("app.services.audit_service.get_supabase", return_value=chain):
        result = await audit_service.get_audit_entry("entry-1", "user-1")

    assert result is not None
    assert isinstance(result, AuditLogEntry)
    assert result.id == "entry-1"


@pytest.mark.asyncio
async def test_get_audit_entry_not_found():
    chain = _make_chain_mock(response_data=None)

    with patch("app.services.audit_service.get_supabase", return_value=chain):
        result = await audit_service.get_audit_entry("nonexistent", "user-1")

    assert result is None
