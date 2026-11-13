"""Source spans: the unit every citation points at.

A span is one stored chunk of a document, identified well enough that an
auditor can find the exact passage and prove it has not changed:

    document id, document version, page, character range, content hash

* ``content_hash`` is the SHA-256 (hex) of the span text encoded as UTF-8.
* ``span_id`` is derived from ``(document_id, version, chunk_index,
  content_hash)``. It is deterministic, so re-ingesting identical content
  yields identical ids, and it can be computed in SQL — the migration that
  introduced spans backfills existing chunks with the same formula
  (``scripts/migrations.sql``, increment 002). Keep the two in lockstep.
* ``char_start``/``char_end`` are offsets into the *normalised page text*
  (``pypdf`` ``extract_text()`` followed by ``.strip()``), such that
  ``page_text[char_start:char_end] == span text``. Chunks ingested before
  spans existed have no offsets (``None``): their text and hash are still
  verifiable, only the page-level range is unknown until re-ingest.
"""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, ConfigDict

SPAN_ID_LENGTH = 32


def content_hash(text: str) -> str:
    """SHA-256 hex digest of ``text`` (UTF-8)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def span_id_for(document_id: str, version: int, chunk_index: int, text_hash: str) -> str:
    """Deterministic span id. Mirrors the SQL backfill exactly."""
    material = f"{document_id}|{version}|{chunk_index}|{text_hash}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:SPAN_ID_LENGTH]


class SpanRef(BaseModel):
    """Immutable pointer to a passage in a specific document version."""

    model_config = ConfigDict(frozen=True)

    span_id: str
    document_id: str
    version: int
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    content_hash: str

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> SpanRef:
        """Build from a ``match_document_chunks`` row."""
        return cls(
            span_id=row["span_id"],
            document_id=str(row["document_id"]),
            version=int(row.get("version") or 1),
            page=row.get("page_number", row.get("page")),
            char_start=row.get("char_start"),
            char_end=row.get("char_end"),
            content_hash=row["content_hash"],
        )


class Span(BaseModel):
    """A span reference together with its text."""

    model_config = ConfigDict(frozen=True)

    ref: SpanRef
    text: str

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Span:
        return cls(ref=SpanRef.from_row(row), text=row.get("content") or row.get("text") or "")

    @property
    def span_id(self) -> str:
        return self.ref.span_id

    def is_intact(self) -> bool:
        """True if the text still hashes to the recorded content hash."""
        return content_hash(self.text) == self.ref.content_hash


def spans_from_rows(rows: list[dict[str, Any]]) -> list[Span]:
    """Convert retrieval rows to spans, dropping any that lack span metadata
    or whose text no longer matches its recorded hash (corruption/tampering).
    Returns only intact spans; callers can compare lengths to detect drops."""
    spans: list[Span] = []
    for row in rows:
        if not row.get("span_id") or not row.get("content_hash"):
            continue
        span = Span.from_row(row)
        if span.is_intact():
            spans.append(span)
    return spans
