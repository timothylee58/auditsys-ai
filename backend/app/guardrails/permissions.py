"""Per-document access control, applied BEFORE retrieval.

The rule the architecture depends on: a document the caller may not read must
never reach the model. Filtering the answer afterwards is a leak — the model
has already seen the text. So:

1. ``allowed_document_ids`` resolves the caller's readable documents first.
2. Retrieval is constrained to exactly that set (``filter_document_ids``),
   on top of the SQL function's own ``uploaded_by = user_id`` predicate.
3. ``assert_rows_permitted`` re-checks every returned row against the set and
   raises ``PermissionLeak`` on any violation, so a regression in the
   retrieval query fails loudly instead of leaking quietly.

Today access is ownership (``documents.uploaded_by``). When sharing or roles
ship, this module is the only place the rule changes: return the extra
document ids here and every downstream stage inherits them.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.core.database import get_async_supabase

MAX_ALLOWED_DOCUMENTS = 1000


class PermissionLeak(RuntimeError):
    """Retrieval returned a document outside the caller's allowed set."""


async def allowed_document_ids(user_id: str) -> list[str]:
    """Indexed documents the user may read, newest first."""
    supabase = await get_async_supabase()
    result = await (
        supabase.table("documents")
        .select("id")
        .eq("uploaded_by", user_id)
        .eq("status", "indexed")
        .order("created_at", desc=True)
        .limit(MAX_ALLOWED_DOCUMENTS)
        .execute()
    )
    return [str(row["id"]) for row in (result.data or [])]


def assert_rows_permitted(rows: Iterable[dict[str, Any]], allowed: Iterable[str]) -> None:
    allowed_set = set(allowed)
    for row in rows:
        document_id = str(row.get("document_id"))
        if document_id not in allowed_set:
            raise PermissionLeak(f"retrieval returned document {document_id} outside the caller's allowed set")
