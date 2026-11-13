"""Hash-chained audit entries.

Every answer appends one entry. Each entry stores the hash of the entry
before it, and its own hash covers that previous hash plus the canonical
JSON of its payload::

    entry_hash = sha256(prev_hash + "\\n" + canonical_json(payload))

Changing, deleting or reordering any past entry breaks every hash after it,
and ``verify_chain`` finds the first break. The exact canonical string that
was hashed is stored next to the (queryable) JSONB payload, so verification
never depends on how Postgres re-serialises JSON.

What this does and does not prove
---------------------------------
* It proves *internal consistency*: nothing in the middle was edited,
  removed or reordered after the fact.
* It does NOT, by itself, prove nothing was cut off the end, or that the
  whole chain was not rebuilt by someone holding write access. Defend the
  tail by recording the head hash somewhere the database admin cannot
  rewrite (a CI artefact, a ticket, a separate store) and passing it back
  as ``expected_head``.
* Database triggers additionally block UPDATE/DELETE/TRUNCATE for every
  role, and ``prev_hash`` is UNIQUE so two writers can never fork the chain.

Privacy: payloads hold span *references and hashes*, not raw document text,
and personal data is redacted before it is written (see ``audit/payload.py``).
Retention: entries are never deleted in place. To enforce a retention
period, archive entries older than the period and verify the remainder from
an anchor (``anchor_hash`` = the last archived entry's hash).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

GENESIS_HASH = "0" * 64
TABLE = "audit_chain"
UNIQUE_VIOLATION = "23505"


def canonical_json(payload: dict[str, Any]) -> str:
    """Deterministic JSON: sorted keys, no whitespace, ASCII-only, no NaN."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def compute_entry_hash(prev_hash: str, canonical: str) -> str:
    return hashlib.sha256(f"{prev_hash}\n{canonical}".encode()).hexdigest()


@dataclass(frozen=True)
class ChainEntry:
    seq: int
    prev_hash: str
    entry_hash: str
    canonical: str
    payload: dict[str, Any]


def make_entry(seq: int, prev_hash: str, payload: dict[str, Any]) -> ChainEntry:
    canonical = canonical_json(payload)
    return ChainEntry(seq, prev_hash, compute_entry_hash(prev_hash, canonical), canonical, payload)


@dataclass
class VerifyResult:
    ok: bool
    checked: int
    head_hash: str
    head_seq: int | None
    errors: list[str] = field(default_factory=list)


def verify_chain(
    entries: Iterable[ChainEntry],
    *,
    anchor_hash: str = GENESIS_HASH,
    expected_head: str | None = None,
) -> VerifyResult:
    """Check linkage, hashes and payload/canonical agreement, in seq order.

    Stops collecting after the first few errors: once one link is broken the
    rest of the chain is untrustworthy anyway, and the first break is what an
    investigator needs.
    """
    errors: list[str] = []
    prev = anchor_hash
    last_seq: int | None = None
    checked = 0

    for entry in entries:
        checked += 1
        if last_seq is not None and entry.seq <= last_seq:
            errors.append(f"seq {entry.seq}: out of order (previous seq {last_seq})")
        if entry.prev_hash != prev:
            errors.append(
                f"seq {entry.seq}: prev_hash does not match the previous entry "
                "(an entry before this one was altered, removed or reordered)"
            )
        if compute_entry_hash(entry.prev_hash, entry.canonical) != entry.entry_hash:
            errors.append(f"seq {entry.seq}: entry_hash does not match its content (entry was altered)")
        try:
            if json.loads(entry.canonical) != entry.payload:
                errors.append(f"seq {entry.seq}: stored payload differs from the hashed canonical form")
        except json.JSONDecodeError:
            errors.append(f"seq {entry.seq}: canonical form is not valid JSON")
        prev = entry.entry_hash
        last_seq = entry.seq
        if len(errors) >= 10:
            break

    if expected_head is not None and prev != expected_head:
        errors.append("head hash does not match the expected head (entries may have been removed from the end)")

    return VerifyResult(ok=not errors, checked=checked, head_hash=prev, head_seq=last_seq, errors=errors)


# -- persistence ------------------------------------------------------------------------------------------


def row_to_entry(row: dict[str, Any]) -> ChainEntry:
    return ChainEntry(
        seq=int(row["seq"]),
        prev_hash=row["prev_hash"],
        entry_hash=row["entry_hash"],
        canonical=row["canonical"],
        payload=row["payload"],
    )


async def append_entry(payload: dict[str, Any], *, user_id: str | None = None, max_attempts: int = 5) -> ChainEntry:
    """Append ``payload`` to the chain.

    Reads the current head, hashes against it and inserts. ``prev_hash`` is
    UNIQUE in the database, so if another writer appended in between, the
    insert is rejected (23505) instead of forking the chain; we then re-read
    the head and retry.
    """
    from app.core.database import get_async_supabase

    supabase = await get_async_supabase()
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        head = await (
            supabase.table(TABLE).select("seq, entry_hash").order("seq", desc=True).limit(1).execute()
        )
        prev_hash = head.data[0]["entry_hash"] if head.data else GENESIS_HASH
        canonical = canonical_json(payload)
        entry_hash = compute_entry_hash(prev_hash, canonical)
        try:
            result = await (
                supabase.table(TABLE)
                .insert(
                    {
                        "prev_hash": prev_hash,
                        "entry_hash": entry_hash,
                        "canonical": canonical,
                        "payload": payload,
                        "user_id": user_id,
                    }
                )
                .execute()
            )
        except Exception as exc:
            if getattr(exc, "code", None) == UNIQUE_VIOLATION or UNIQUE_VIOLATION in str(exc):
                last_error = exc
                logger.info("audit_chain_append_conflict attempt={}", attempt)
                continue
            raise
        row = result.data[0]
        return ChainEntry(int(row["seq"]), prev_hash, entry_hash, canonical, payload)

    raise RuntimeError(f"could not append to the audit chain after {max_attempts} attempts") from last_error
