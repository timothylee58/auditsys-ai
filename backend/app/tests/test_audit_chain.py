"""Hash chain: canonicalisation, verification, concurrent append, payload privacy."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.audit import chain as chain_mod
from app.audit.chain import (
    GENESIS_HASH,
    ChainEntry,
    append_entry,
    canonical_json,
    compute_entry_hash,
    make_entry,
    verify_chain,
)
from app.audit.payload import build_chain_payload
from app.guardrails import output as guard_out
from app.guardrails.pii_detector import PIIResult
from app.tests.agent_harness import REVENUE, Harness, claims_json, row, verdicts_json


def build_chain(n: int = 5) -> list[ChainEntry]:
    chain, prev = [], GENESIS_HASH
    for i in range(1, n + 1):
        entry = make_entry(i, prev, {"i": i, "text": f"entry {i}"})
        chain.append(entry)
        prev = entry.entry_hash
    return chain


# -- canonicalisation / hashing ---------------------------------------------------------------------


def test_canonical_json_is_order_and_whitespace_independent():
    assert canonical_json({"b": 1, "a": [2, {"z": 1, "y": 2}]}) == '{"a":[2,{"y":2,"z":1}],"b":1}'
    assert canonical_json({"a": 1, "b": 2}) == canonical_json({"b": 2, "a": 1})


def test_canonical_json_escapes_non_ascii_and_rejects_nan():
    assert canonical_json({"q": "café — “x”"}) == '{"q":"caf\\u00e9 \\u2014 \\u201cx\\u201d"}'
    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})


def test_entry_hash_golden_vector():
    """Pinned so a refactor cannot silently change the hash definition:
    entry_hash = sha256(prev_hash + "\\n" + canonical_json(payload))."""
    canonical = canonical_json({"a": 1})
    assert canonical == '{"a":1}'
    assert compute_entry_hash(GENESIS_HASH, canonical) == "f21735afd2cd6af4fc5804b0045cebfd545aef8396d29d030c39cb8880b45b7f"
    assert compute_entry_hash("p", "c") == hashlib.sha256(b"p\nc").hexdigest()


# -- verification ------------------------------------------------------------------------------------------


def test_intact_chain_verifies_and_reports_head():
    chain = build_chain()
    result = verify_chain(chain)
    assert result.ok and result.checked == 5
    assert result.head_hash == chain[-1].entry_hash and result.head_seq == 5


def test_empty_chain_is_valid_with_genesis_head():
    result = verify_chain([])
    assert result.ok and result.checked == 0 and result.head_hash == GENESIS_HASH


def test_edited_payload_is_detected():
    chain = build_chain()
    e = chain[2]
    forged = ChainEntry(e.seq, e.prev_hash, e.entry_hash, e.canonical.replace("entry 3", "entry X"), e.payload)
    result = verify_chain([*chain[:2], forged, *chain[3:]])
    assert not result.ok and any("entry_hash does not match" in m for m in result.errors)


def test_consistently_rehashed_edit_breaks_the_next_link():
    """An attacker who recomputes the edited entry's own hash is still caught
    by the entry after it, whose prev_hash no longer matches."""
    chain = build_chain()
    forged = make_entry(3, chain[1].entry_hash, {"i": 3, "text": "FORGED"})
    result = verify_chain([*chain[:2], forged, *chain[3:]])
    assert not result.ok
    assert any(m.startswith("seq 4") and "prev_hash" in m for m in result.errors)


def test_deleted_reordered_and_inserted_entries_are_detected():
    chain = build_chain()
    assert not verify_chain([*chain[:2], *chain[3:]]).ok  # deleted
    assert not verify_chain([chain[1], chain[0], *chain[2:]]).ok  # reordered
    extra = make_entry(99, GENESIS_HASH, {"x": 1})
    assert not verify_chain([chain[0], extra, *chain[1:]]).ok  # inserted


def test_truncation_is_only_detectable_with_an_expected_head():
    chain = build_chain()
    assert verify_chain(chain[:-1]).ok  # internally consistent
    result = verify_chain(chain[:-1], expected_head=chain[-1].entry_hash)
    assert not result.ok and any("head hash" in m for m in result.errors)
    assert verify_chain(chain, expected_head=chain[-1].entry_hash).ok


def test_payload_that_differs_from_hashed_canonical_is_detected():
    chain = build_chain(2)
    e = chain[1]
    swapped = ChainEntry(e.seq, e.prev_hash, e.entry_hash, e.canonical, {"i": 2, "text": "different"})
    result = verify_chain([chain[0], swapped])
    assert not result.ok and any("payload differs" in m for m in result.errors)


def test_verification_can_start_from_an_archive_anchor():
    chain = build_chain(6)
    tail = chain[3:]
    assert not verify_chain(tail).ok  # does not link to genesis
    assert verify_chain(tail, anchor_hash=chain[2].entry_hash).ok


def test_non_increasing_seq_is_reported():
    chain = build_chain(3)
    dup = ChainEntry(2, chain[2].prev_hash, chain[2].entry_hash, chain[2].canonical, chain[2].payload)
    assert any("out of order" in m for m in verify_chain([chain[0], chain[1], dup]).errors)


# -- append (against a fake PostgREST client) ---------------------------------------------------------------


class FakeTable:
    def __init__(self, store: list[dict], fail_next_inserts: list[Exception]):
        self.store = store
        self.fail = fail_next_inserts
        self._mode = None
        self._row = None

    def select(self, *_):
        self._mode = "select"
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_):
        return self

    def insert(self, row):
        self._mode, self._row = "insert", row
        return self

    async def execute(self):
        if self._mode == "select":
            return MagicMock(data=[{"seq": len(self.store), "entry_hash": self.store[-1]["entry_hash"]}] if self.store else [])
        if self.fail:
            raise self.fail.pop(0)
        stored = {**self._row, "seq": len(self.store) + 1}
        self.store.append(stored)
        return MagicMock(data=[stored])


class FakeClient:
    def __init__(self, store, fail=None):
        self.store, self.fail = store, fail or []

    def table(self, _name):
        return FakeTable(self.store, self.fail)


class Conflict(Exception):
    code = "23505"


@pytest.mark.asyncio
async def test_append_links_each_entry_to_the_previous_head():
    store: list[dict] = []
    with patch("app.core.database.get_async_supabase", new=AsyncMock(return_value=FakeClient(store))):
        e1 = await append_entry({"n": 1}, user_id="u")
        e2 = await append_entry({"n": 2}, user_id="u")
    assert e1.prev_hash == GENESIS_HASH and e2.prev_hash == e1.entry_hash
    assert verify_chain([chain_mod.row_to_entry(r) for r in store]).ok


@pytest.mark.asyncio
async def test_append_retries_after_a_concurrent_writer_wins():
    store: list[dict] = []
    client = FakeClient(store, fail=[Conflict("duplicate key 23505")])
    with patch("app.core.database.get_async_supabase", new=AsyncMock(return_value=client)):
        entry = await append_entry({"n": 1})
    assert entry.seq == 1 and len(store) == 1


@pytest.mark.asyncio
async def test_append_gives_up_after_max_attempts_and_surfaces_other_errors():
    store: list[dict] = []
    always = FakeClient(store, fail=[Conflict("23505")] * 5)
    with (
        patch("app.core.database.get_async_supabase", new=AsyncMock(return_value=always)),
        pytest.raises(RuntimeError, match="after 5 attempts"),
    ):
        await append_entry({"n": 1})

    broken = FakeClient([], fail=[ConnectionError("db down")])
    with (
        patch("app.core.database.get_async_supabase", new=AsyncMock(return_value=broken)),
        pytest.raises(ConnectionError),
    ):
        await append_entry({"n": 1})


# -- payload ------------------------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def no_pii():
    stub = AsyncMock(return_value=PIIResult(has_pii=False))
    with patch.object(guard_out, "scan_pii", new=stub), patch("app.audit.payload.scan_pii", new=stub):
        yield


async def answered_result():
    h = Harness(
        search_results=[[row(0, REVENUE)]],
        generator=lambda: claims_json(
            ("Total revenue for fiscal 2024 was $1,204.5 million, an increase of 8.5% over the prior year.", ["S1"]),
            ("Revenue was $9,999.0 million.", ["S1"]),
            ("Ghost claim.", ["S5"]),
        ),
        verifier=lambda: verdicts_json(),
    )
    return await h.run()


@pytest.mark.asyncio
async def test_payload_records_the_whole_chain_and_serialises():
    result = await answered_result()
    payload = await build_chain_payload(
        result, question="What was revenue?", session_id="s1", trace_id="t1", user_id="u1"
    )
    canonical_json(payload)  # must be JSON-serialisable with no NaN/objects

    assert payload["outcome"]["status"] == "answered"
    assert [c["claim_id"] for c in payload["claims"]] == ["c1", "c2"]
    shown = {c["claim_id"]: c["shown"] for c in payload["claims"]}
    assert shown == {"c1": True, "c2": False}
    assert payload["claims"][1]["verdict"] == "unsupported" and payload["claims"][1]["method"] == "precheck"
    assert payload["rejected_claims"][0]["reason"].startswith("unknown_span")
    assert payload["retrieval"]["spans"][0]["content_hash"] == result["spans"][0].ref.content_hash
    assert payload["citations"] == [c["span_id"] for c in result["citations"]]
    assert {"pipeline", "generator_model", "verifier_model"} <= payload["versions"].keys()
    assert payload["trace"][0]["node"] == "guard_in"


@pytest.mark.asyncio
async def test_payload_never_stores_document_text_or_the_raw_question():
    result = await answered_result()
    payload = await build_chain_payload(
        result, question="What was revenue?", session_id="s1", trace_id="t1", user_id="u1"
    )
    # Spans are referenced by id/hash; the document text is not copied into the
    # retrieval record (the answer and claims are model output and may quote it).
    retrieval = json.dumps(payload["retrieval"])
    assert REVENUE not in retrieval and "increase of 8.5%" not in retrieval
    assert payload["question_sha256"] == hashlib.sha256(b"What was revenue?").hexdigest()


@pytest.mark.asyncio
async def test_payload_redacts_pii_in_derived_text():
    result = await answered_result()
    redact = AsyncMock(return_value=PIIResult(has_pii=True, entity_types=["PERSON"], anonymised_text="<REDACTED>"))
    with patch("app.audit.payload.scan_pii", new=redact):
        payload = await build_chain_payload(
            result, question="Did Jane Roe sign?", session_id="s", trace_id="t", user_id="u"
        )
    assert payload["final_answer"] == "<REDACTED>"
    assert all(c["text"] == "<REDACTED>" for c in payload["claims"])
    assert "Jane Roe" not in canonical_json(payload)


@pytest.mark.asyncio
async def test_payload_for_a_refusal_is_complete_too():
    h = Harness(search_results=[[row(0, "Irrelevant.", sim=0.01)]])
    result = await h.run()
    payload = await build_chain_payload(result, question="q?", session_id="s", trace_id="t", user_id="u")
    assert payload["outcome"]["status"] == "refused"
    assert payload["outcome"]["refusal_reason"] == "insufficient_evidence"
    assert payload["claims"] == [] and payload["citations"] == []
    canonical_json(payload)


# -- the script ------------------------------------------------------------------------------------------------


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_audit_chain.py"


def run_script(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, timeout=60, check=False)


def write_jsonl(path: Path, entries: list[ChainEntry]):
    path.write_text(
        "\n".join(
            json.dumps(
                {"seq": e.seq, "prev_hash": e.prev_hash, "entry_hash": e.entry_hash, "canonical": e.canonical, "payload": e.payload}
            )
            for e in entries
        )
    )


def test_script_self_test_passes():
    out = run_script("--self-test")
    assert out.returncode == 0, out.stdout + out.stderr
    assert out.stdout.count("PASS") == 5 and "FAIL" not in out.stdout


def test_script_exit_codes_for_intact_tampered_and_unreadable_files(tmp_path):
    chain = build_chain(4)
    good = tmp_path / "good.jsonl"
    write_jsonl(good, chain)
    ok = run_script("--file", str(good))
    assert ok.returncode == 0 and "chain intact" in ok.stdout and chain[-1].entry_hash in ok.stdout

    bad = tmp_path / "bad.jsonl"
    write_jsonl(bad, [*chain[:1], *chain[2:]])
    broken = run_script("--file", str(bad))
    assert broken.returncode == 1 and "CHAIN BROKEN" in broken.stderr

    truncated = tmp_path / "trunc.jsonl"
    write_jsonl(truncated, chain[:-1])
    assert run_script("--file", str(truncated), "--expect-head", chain[-1].entry_hash).returncode == 1

    junk = tmp_path / "junk.jsonl"
    junk.write_text("not json\n")
    assert run_script("--file", str(junk)).returncode == 2
