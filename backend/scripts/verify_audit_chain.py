#!/usr/bin/env python
"""Verify the audit hash chain end to end.

    python scripts/verify_audit_chain.py                       # live database
    python scripts/verify_audit_chain.py --file chain.jsonl    # an exported chain
    python scripts/verify_audit_chain.py --expect-head <hash>  # also pin the tail
    python scripts/verify_audit_chain.py --self-test           # prove the verifier works

Exit status: 0 chain intact, 1 chain broken, 2 could not run (bad input /
database unreachable). A broken chain is never reported as success.

``--expect-head`` is what detects entries cut off the END of the chain:
record the printed head hash somewhere the database admin cannot edit, and
pass it here on later runs.

Exported file format: JSON Lines, one object per entry with the columns
seq, prev_hash, entry_hash, canonical, payload.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.audit.chain import (
    GENESIS_HASH,
    ChainEntry,
    make_entry,
    row_to_entry,
    verify_chain,
)

PAGE_SIZE = 1000


async def fetch_from_database() -> list[ChainEntry]:
    from app.core.database import get_async_supabase

    supabase = await get_async_supabase()
    entries: list[ChainEntry] = []
    start = 0
    while True:
        page = await (
            supabase.table("audit_chain")
            .select("seq, prev_hash, entry_hash, canonical, payload")
            .order("seq")
            .range(start, start + PAGE_SIZE - 1)
            .execute()
        )
        rows = page.data or []
        entries.extend(row_to_entry(r) for r in rows)
        if len(rows) < PAGE_SIZE:
            return entries
        start += PAGE_SIZE


def load_file(path: Path) -> list[ChainEntry]:
    entries = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if line.strip():
                try:
                    entries.append(row_to_entry(json.loads(line)))
                except (json.JSONDecodeError, KeyError) as exc:
                    raise ValueError(f"{path}:{number}: not a chain entry ({exc})") from exc
    return entries


def self_test() -> bool:
    """Build a chain, then check the verifier accepts it and rejects each
    kind of tampering. Guards against the verifier silently rotting."""
    chain: list[ChainEntry] = []
    prev = GENESIS_HASH
    for n in range(1, 6):
        entry = make_entry(n, prev, {"n": n, "answer": f"answer {n}"})
        chain.append(entry)
        prev = entry.entry_hash

    def tampered(i: int) -> ChainEntry:
        e = chain[i]
        return ChainEntry(e.seq, e.prev_hash, e.entry_hash, e.canonical.replace("answer", "ANSWER"), e.payload)

    cases = {
        "intact chain is accepted": (chain, None, True),
        "edited entry is detected": ([*chain[:2], tampered(2), *chain[3:]], None, False),
        "deleted middle entry is detected": ([*chain[:2], *chain[3:]], None, False),
        "reordered entries are detected": ([chain[1], chain[0], *chain[2:]], None, False),
        "truncated tail is detected with --expect-head": (chain[:-1], chain[-1].entry_hash, False),
    }
    passed = True
    for name, (entries, head, want_ok) in cases.items():
        result = verify_chain(entries, expected_head=head)
        good = result.ok == want_ok
        passed &= good
        print(f"  {'PASS' if good else 'FAIL'}  {name}")
    return passed


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the AuditSys audit hash chain")
    parser.add_argument("--file", type=Path, help="verify an exported JSONL chain instead of the database")
    parser.add_argument("--anchor", default=GENESIS_HASH, help="hash the first entry must link to (default: genesis)")
    parser.add_argument("--expect-head", help="hash the last entry must have (detects truncation)")
    parser.add_argument("--self-test", action="store_true", help="verify the verifier against synthetic tampering")
    args = parser.parse_args()

    if args.self_test:
        print("Audit chain verifier self-test")
        ok = self_test()
        print("self-test passed" if ok else "SELF-TEST FAILED")
        return 0 if ok else 1

    try:
        entries = load_file(args.file) if args.file else asyncio.run(fetch_from_database())
    except Exception as exc:  # noqa: BLE001 - report any load failure as "could not run", exit 2
        print(f"could not load the chain: {exc}", file=sys.stderr)
        return 2

    result = verify_chain(entries, anchor_hash=args.anchor, expected_head=args.expect_head)
    print(f"entries checked : {result.checked}")
    print(f"head seq        : {result.head_seq}")
    print(f"head hash       : {result.head_hash}   <- record this externally to detect truncation")
    if result.ok:
        print("RESULT          : chain intact")
        return 0
    print("RESULT          : CHAIN BROKEN", file=sys.stderr)
    for error in result.errors:
        print(f"  - {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
