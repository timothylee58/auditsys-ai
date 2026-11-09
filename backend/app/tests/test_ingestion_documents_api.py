"""list_documents / soft_delete_document must use the documents.uploaded_by column.

The documents table has no ``user_id`` column (see scripts/migrations.sql);
querying it made GET /documents and DELETE /documents/{id} fail against the
real schema.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import ingestion_service


def _chain(data=None, count=None) -> MagicMock:
    mock = MagicMock()
    response = MagicMock()
    response.data = data
    response.count = count
    mock.execute = AsyncMock(return_value=response)
    for method in ("table", "select", "update", "delete", "eq", "neq", "order", "range", "limit"):
        getattr(mock, method).return_value = mock
    return mock


def _patched(chain: MagicMock):
    return patch(
        "app.services.ingestion_service.get_async_supabase",
        new=AsyncMock(return_value=chain),
    )


def _eq_columns(chain: MagicMock) -> list[str]:
    return [call.args[0] for call in chain.eq.call_args_list]


@pytest.mark.asyncio
async def test_list_documents_filters_on_uploaded_by():
    chain = _chain(data=[{"id": "d1"}], count=1)
    with _patched(chain):
        result = await ingestion_service.list_documents(user_id="user-1")

    assert _eq_columns(chain) == ["uploaded_by"]
    chain.eq.assert_called_once_with("uploaded_by", "user-1")
    assert result["documents"] == [{"id": "d1"}]
    assert result["total"] == 1
    assert result["has_next"] is False


@pytest.mark.asyncio
async def test_soft_delete_checks_ownership_via_uploaded_by():
    chain = _chain(data=[{"id": "d1", "uploaded_by": "user-1"}])
    with _patched(chain):
        await ingestion_service.soft_delete_document("d1", user_id="user-1")

    chain.select.assert_called_once_with("id, uploaded_by")
    chain.update.assert_called_once_with({"status": "deleted"})


@pytest.mark.asyncio
async def test_soft_delete_rejects_other_users_document():
    chain = _chain(data=[{"id": "d1", "uploaded_by": "someone-else"}])
    with _patched(chain), pytest.raises(PermissionError):
        await ingestion_service.soft_delete_document("d1", user_id="user-1")

    chain.update.assert_not_called()
    chain.delete.assert_not_called()


@pytest.mark.asyncio
async def test_soft_delete_unknown_document_raises_value_error():
    chain = _chain(data=[])
    with _patched(chain), pytest.raises(ValueError):
        await ingestion_service.soft_delete_document("missing", user_id="user-1")
