"""Span model: hashing, ids, offsets and integrity checks."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.cite.spans import Span, SpanRef, content_hash, span_id_for, spans_from_rows
from app.services import ingestion_service
from app.services.ingestion_service import DOCUMENT_VERSION, _chunk_pages

DOC = "11111111-1111-1111-1111-111111111111"

# Golden vectors produced by PostgreSQL 16 running the increment-002 backfill
# SQL (sha256(convert_to(...,'UTF8')) / encode(..., 'hex')) on these exact
# inputs. If Python and SQL ever disagree, backfilled spans stop matching
# freshly ingested ones — these tests pin both sides to the same values.
GOLDEN = [
    (
        0,
        "Revenue was $1,204.5m — up 8%.",
        "cc070aacd30f5b16fa9204e82c17b8d6b67848aa78d7512470409a651756a7ca",
        "07712f75f5d43fe3f99b5ec02cd98115",
    ),
    (
        1,
        "Ünïcode “quotes”\nand newline",
        "8f3b5cd5343fb23e45be0cf9a9476eb02349d62560c3c0e9668ce25bcf6497a7",
        "371eb21767d40296ebcb6cd667a7a62f",
    ),
]


@pytest.mark.parametrize("chunk_index,text,expected_hash,expected_span_id", GOLDEN)
def test_hash_and_span_id_match_sql_backfill(chunk_index, text, expected_hash, expected_span_id):
    assert content_hash(text) == expected_hash
    assert span_id_for(DOC, 1, chunk_index, expected_hash) == expected_span_id


def test_span_id_changes_with_every_component():
    base = span_id_for(DOC, 1, 0, "h")
    assert span_id_for(DOC.replace("1", "2"), 1, 0, "h") != base
    assert span_id_for(DOC, 2, 0, "h") != base
    assert span_id_for(DOC, 1, 1, "h") != base
    assert span_id_for(DOC, 1, 0, "g") != base


def _row(text: str, **overrides):
    row = {
        "span_id": span_id_for(DOC, 1, 0, content_hash(text)),
        "document_id": DOC,
        "version": 1,
        "page_number": 3,
        "char_start": 10,
        "char_end": 10 + len(text),
        "content_hash": content_hash(text),
        "content": text,
    }
    row.update(overrides)
    return row


def test_span_from_row_and_integrity():
    span = Span.from_row(_row("hello world"))
    assert span.ref.page == 3
    assert (span.ref.char_start, span.ref.char_end) == (10, 21)
    assert span.is_intact()


def test_tampered_text_is_not_intact():
    span = Span.from_row(_row("hello world", content="hello w0rld"))
    assert not span.is_intact()


def test_spans_from_rows_drops_tampered_and_unspanned_rows():
    good = _row("good text")
    tampered = _row("bad text", content="bad t3xt")
    legacy = {"document_id": DOC, "content": "no span metadata"}
    spans = spans_from_rows([good, tampered, legacy])
    assert [s.span_id for s in spans] == [good["span_id"]]


def test_legacy_chunk_without_offsets_is_still_valid():
    ref = SpanRef.from_row(_row("legacy", char_start=None, char_end=None))
    assert ref.char_start is None and ref.char_end is None


def test_span_ref_is_immutable():
    ref = SpanRef.from_row(_row("x" * 5))
    with pytest.raises(Exception):  # noqa: B017 - pydantic frozen model error type
        ref.page = 9  # type: ignore[misc]


# -- ingestion: offsets and stored rows -----------------------------------------


@pytest.mark.parametrize(
    "page_text",
    [
        "A" * 7000,
        "   " + "B" * 500 + "   ",
        ("para one. " * 50 + "\n\n   " + "para two. " * 400),
        "Ünï “q” — " * 700,
    ],
)
def test_chunk_offsets_reproduce_chunk_text(page_text):
    page_text = page_text.strip()  # _extract_pages hands over stripped page text
    chunks = _chunk_pages([{"page": 1, "text": page_text}], "f.pdf", None, None)
    assert chunks
    for chunk in chunks:
        assert page_text[chunk["char_start"] : chunk["char_end"]] == chunk["text"]
        assert chunk["content_hash"] == content_hash(chunk["text"])


def test_chunk_offsets_skip_leading_whitespace_inside_a_window():
    # A window that begins on whitespace must report the offset of the first
    # real character, not the window start.
    text = "x" * 3199 + "   " + "y" * 400
    chunks = _chunk_pages([{"page": 1, "text": text}], "f.pdf", None, None)
    for chunk in chunks:
        assert text[chunk["char_start"] : chunk["char_end"]] == chunk["text"]


@pytest.mark.asyncio
async def test_store_chunks_writes_span_fields():
    chunks = _chunk_pages([{"page": 2, "text": "Z" * 500}], "f.pdf", None, None)
    table = MagicMock()
    table.upsert.return_value.execute = AsyncMock()
    table.update.return_value.eq.return_value.execute = AsyncMock()
    supabase = MagicMock()
    supabase.table.return_value = table

    with patch.object(
        ingestion_service, "get_async_supabase", new=AsyncMock(return_value=supabase)
    ):
        await ingestion_service._store_chunks(DOC, chunks, [[0.0]] * len(chunks))

    rows = table.upsert.call_args[0][0]
    assert len(rows) == len(chunks)
    row = rows[0]
    assert row["content_hash"] == content_hash(row["content"])
    assert row["span_id"] == span_id_for(DOC, DOCUMENT_VERSION, row["chunk_index"], row["content_hash"])
    assert row["char_end"] - row["char_start"] == len(row["content"])
    assert row["page_number"] == 2


# -- migrations mirror ------------------------------------------------------------


def test_migrations_sql_is_the_concatenation_of_supabase_migrations():
    """scripts/migrations.sql is the canonical full schema; supabase/migrations
    holds the same SQL split into ordered files. They must never drift."""
    repo = Path(__file__).resolve().parents[3]
    files = sorted((repo / "supabase" / "migrations").glob("*.sql"))
    assert files
    combined = "".join(f.read_text() for f in files)
    assert (repo / "backend" / "scripts" / "migrations.sql").read_text() == combined
