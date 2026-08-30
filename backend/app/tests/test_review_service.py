"""Tests for the human-in-the-loop review service (Feature 5)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.review import (
    ReviewAction,
    ReviewItem,
    ReviewItemList,
    ReviewOverrideRequest,
)
from app.services import review_service


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

    mock.execute = AsyncMock(return_value=execute_response)

    for method in (
        "table", "select", "insert", "update", "delete",
        "eq", "neq", "gte", "lte", "gt", "lt",
        "order", "range", "limit", "single",
    ):
        getattr(mock, method).return_value = mock

    return mock


def _sample_review_row(
    item_id: str = "item-1",
    status: str = "pending",
) -> dict:
    return {
        "id": item_id,
        "session_id": "session-1",
        "user_id": "user-1",
        "query": "What is the compliance rule?",
        "draft_answer": "The rule states...",
        "citations": [{"source": "policy.pdf", "page": 5}],
        "confidence_score": 0.4,
        "status": status,
        "reviewer_id": None,
        "reviewed_at": None,
        "reviewer_action": None,
        "override_answer": None,
        "reviewer_notes": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


# -- Tests: get_pending_reviews -------------------------------------------------


@pytest.mark.asyncio
async def test_get_pending_reviews_returns_list():
    rows = [_sample_review_row("item-1"), _sample_review_row("item-2")]
    chain = _make_chain_mock(response_data=rows, response_count=2)

    with patch("app.services.review_service.get_supabase", return_value=chain):
        result = await review_service.get_pending_reviews(
            reviewer_user_id="reviewer-1",
            page=1,
            page_size=20,
        )

    assert isinstance(result, ReviewItemList)
    assert result.total == 2
    assert result.page == 1
    assert result.has_next is False
    assert len(result.items) == 2
    assert all(isinstance(item, ReviewItem) for item in result.items)


@pytest.mark.asyncio
async def test_get_pending_reviews_empty():
    chain = _make_chain_mock(response_data=[], response_count=0)

    with patch("app.services.review_service.get_supabase", return_value=chain):
        result = await review_service.get_pending_reviews(
            reviewer_user_id="reviewer-1",
        )

    assert result.total == 0
    assert result.items == []
    assert result.has_next is False


# -- Tests: get_review_item -----------------------------------------------------


@pytest.mark.asyncio
async def test_get_review_item_found():
    row = _sample_review_row("item-1")
    chain = _make_chain_mock(response_data=row)

    with patch("app.services.review_service.get_supabase", return_value=chain):
        result = await review_service.get_review_item("item-1", "reviewer-1")

    assert result is not None
    assert isinstance(result, ReviewItem)
    assert result.id == "item-1"


@pytest.mark.asyncio
async def test_get_review_item_not_found():
    chain = _make_chain_mock(response_data=None)

    with patch("app.services.review_service.get_supabase", return_value=chain):
        result = await review_service.get_review_item("nonexistent", "reviewer-1")

    assert result is None


# -- Tests: approve_review_item -------------------------------------------------


@pytest.mark.asyncio
async def test_approve_review_item_success():
    approved_row = _sample_review_row("item-1", status="approved")
    approved_row["reviewer_id"] = "reviewer-1"
    approved_row["reviewer_action"] = "approve"
    chain = _make_chain_mock(response_data=[approved_row])

    with (
        patch("app.services.review_service.get_supabase", return_value=chain),
        patch("app.services.review_service._log_review_action", new_callable=AsyncMock),
    ):
        result = await review_service.approve_review_item("item-1", "reviewer-1")

    assert isinstance(result, ReviewItem)
    assert result.status == "approved"
    chain.update.assert_called_once()


@pytest.mark.asyncio
async def test_approve_review_item_already_reviewed():
    chain = _make_chain_mock(response_data=[])  # empty = not found/already reviewed

    with patch("app.services.review_service.get_supabase", return_value=chain):
        with pytest.raises(ValueError, match="not found or already reviewed"):
            await review_service.approve_review_item("item-1", "reviewer-1")


# -- Tests: reject_review_item --------------------------------------------------


@pytest.mark.asyncio
async def test_reject_review_item_success():
    rejected_row = _sample_review_row("item-1", status="rejected")
    rejected_row["reviewer_id"] = "reviewer-1"
    rejected_row["reviewer_action"] = "reject"
    rejected_row["reviewer_notes"] = "Inaccurate information"
    chain = _make_chain_mock(response_data=[rejected_row])

    with (
        patch("app.services.review_service.get_supabase", return_value=chain),
        patch("app.services.review_service._log_review_action", new_callable=AsyncMock),
    ):
        result = await review_service.reject_review_item(
            "item-1", "reviewer-1", "Inaccurate information"
        )

    assert isinstance(result, ReviewItem)
    assert result.status == "rejected"
    assert result.reviewer_notes == "Inaccurate information"


@pytest.mark.asyncio
async def test_reject_review_item_already_reviewed():
    chain = _make_chain_mock(response_data=[])

    with patch("app.services.review_service.get_supabase", return_value=chain):
        with pytest.raises(ValueError, match="not found or already reviewed"):
            await review_service.reject_review_item(
                "item-1", "reviewer-1", "Bad answer"
            )


# -- Tests: override_review_item ------------------------------------------------


@pytest.mark.asyncio
async def test_override_review_item_success():
    overridden_row = _sample_review_row("item-1", status="overridden")
    overridden_row["reviewer_id"] = "reviewer-1"
    overridden_row["reviewer_action"] = "override"
    overridden_row["override_answer"] = "The corrected answer is..."
    overridden_row["reviewer_notes"] = "Fixed citation"
    chain = _make_chain_mock(response_data=[overridden_row])

    request = ReviewOverrideRequest(
        corrected_answer="The corrected answer is...",
        notes="Fixed citation",
    )

    with (
        patch("app.services.review_service.get_supabase", return_value=chain),
        patch("app.services.review_service._log_review_action", new_callable=AsyncMock),
    ):
        result = await review_service.override_review_item(
            "item-1", "reviewer-1", request
        )

    assert isinstance(result, ReviewItem)
    assert result.status == "overridden"
    assert result.override_answer == "The corrected answer is..."


@pytest.mark.asyncio
async def test_override_review_item_already_reviewed():
    chain = _make_chain_mock(response_data=[])

    request = ReviewOverrideRequest(
        corrected_answer="Some corrected answer here",
        notes="Fixing it",
    )

    with patch("app.services.review_service.get_supabase", return_value=chain):
        with pytest.raises(ValueError, match="not found or already reviewed"):
            await review_service.override_review_item(
                "item-1", "reviewer-1", request
            )


# -- Tests: get_query_status -----------------------------------------------------


@pytest.mark.asyncio
async def test_get_query_status_approved():
    row = {
        "status": "approved",
        "draft_answer": "The approved answer",
        "override_answer": None,
        "reviewer_notes": None,
    }
    chain = _make_chain_mock(response_data=[row])

    with patch("app.services.review_service.get_supabase", return_value=chain):
        result = await review_service.get_query_status("session-1", "user-1")

    assert result["status"] == "answered"
    assert result["answer"] == "The approved answer"


@pytest.mark.asyncio
async def test_get_query_status_overridden():
    row = {
        "status": "overridden",
        "draft_answer": "Original draft",
        "override_answer": "Corrected answer",
        "reviewer_notes": "Fixed",
    }
    chain = _make_chain_mock(response_data=[row])

    with patch("app.services.review_service.get_supabase", return_value=chain):
        result = await review_service.get_query_status("session-1", "user-1")

    assert result["status"] == "answered"
    assert result["answer"] == "Corrected answer"
    assert result["review_note"] == "Answer provided by compliance reviewer."


@pytest.mark.asyncio
async def test_get_query_status_rejected():
    row = {
        "status": "rejected",
        "draft_answer": "Bad answer",
        "override_answer": None,
        "reviewer_notes": "Inaccurate",
    }
    chain = _make_chain_mock(response_data=[row])

    with patch("app.services.review_service.get_supabase", return_value=chain):
        result = await review_service.get_query_status("session-1", "user-1")

    assert result["status"] == "rejected"
    assert result["answer"] is None
    assert result["review_note"] == "Inaccurate"


@pytest.mark.asyncio
async def test_get_query_status_pending():
    row = {
        "status": "pending",
        "draft_answer": "Waiting for review",
        "override_answer": None,
        "reviewer_notes": None,
    }
    chain = _make_chain_mock(response_data=[row])

    with patch("app.services.review_service.get_supabase", return_value=chain):
        result = await review_service.get_query_status("session-1", "user-1")

    assert result["status"] == "pending_review"


@pytest.mark.asyncio
async def test_get_query_status_not_found():
    chain = _make_chain_mock(response_data=[])

    with patch("app.services.review_service.get_supabase", return_value=chain):
        result = await review_service.get_query_status("session-x", "user-x")

    assert result["status"] == "not_found"
