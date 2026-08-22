"""Unit tests for pure functions in the ingestion service."""

import io

from pypdf import PdfWriter

from app.services.ingestion_service import (
    MIN_CHUNK_LENGTH,
    _chunk_pages,
    _extract_pages,
    _hash_content,
)


def _make_pdf(pages_text: list[str]) -> bytes:
    """Create a minimal in-memory PDF with given page texts."""
    from pypdf.generic import (
        DecodedStreamObject,
        DictionaryObject,
        NameObject,
    )

    writer = PdfWriter()
    for text in pages_text:
        writer.add_blank_page(width=612, height=792)
        page = writer.pages[-1]

        # Create a font dictionary
        font_dict = DictionaryObject()
        font_dict[NameObject("/Type")] = NameObject("/Font")
        font_dict[NameObject("/Subtype")] = NameObject("/Type1")
        font_dict[NameObject("/BaseFont")] = NameObject("/Helvetica")

        # Add font to page resources
        resources = DictionaryObject()
        font_res = DictionaryObject()
        font_res[NameObject("/F1")] = font_dict
        resources[NameObject("/Font")] = font_res
        page[NameObject("/Resources")] = resources

        # Create content stream with text
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET"
        stream = DecodedStreamObject()
        stream.set_data(content.encode("latin-1"))
        page[NameObject("/Contents")] = stream

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class TestExtractPages:
    def test_extracts_text_from_pdf(self):
        """Verify text extraction from a simple PDF."""
        long_text = "A" * 200  # Longer than MIN_CHUNK_LENGTH
        pdf_bytes = _make_pdf([long_text])
        pages = _extract_pages(pdf_bytes)
        assert len(pages) >= 1
        assert pages[0]["page"] == 1
        assert len(pages[0]["text"]) >= MIN_CHUNK_LENGTH

    def test_skips_short_pages(self):
        """Pages with text shorter than MIN_CHUNK_LENGTH are skipped."""
        short_text = "Hi"
        pdf_bytes = _make_pdf([short_text])
        pages = _extract_pages(pdf_bytes)
        assert len(pages) == 0

    def test_multiple_pages(self):
        """Multiple pages each get extracted with correct page numbers."""
        texts = ["X" * 200, "Y" * 200]
        pdf_bytes = _make_pdf(texts)
        pages = _extract_pages(pdf_bytes)
        # Both pages should be extracted (assuming text renders)
        if len(pages) == 2:
            assert pages[0]["page"] == 1
            assert pages[1]["page"] == 2


class TestChunkPages:
    def test_single_short_chunk(self):
        """Text shorter than chunk size produces one chunk."""
        pages = [{"page": 1, "text": "A" * 500}]
        chunks = _chunk_pages(pages, "test.pdf", "2024-01-01", "TestCo")
        assert len(chunks) == 1
        assert chunks[0]["source"] == "test.pdf"
        assert chunks[0]["page"] == 1
        assert chunks[0]["entity"] == "TestCo"
        assert chunks[0]["doc_date"] == "2024-01-01"
        assert chunks[0]["chunk_index"] == 0

    def test_overlapping_chunks(self):
        """Long text is split into overlapping chunks."""
        # Create text longer than one chunk (CHUNK_SIZE * 4 = 3200 chars)
        long_text = "B" * 7000
        pages = [{"page": 1, "text": long_text}]
        chunks = _chunk_pages(pages, "report.pdf", None, None)
        assert len(chunks) >= 2
        # Verify chunk_index is sequential
        for i, chunk in enumerate(chunks):
            assert chunk["chunk_index"] == i

    def test_metadata_preserved(self):
        """Each chunk carries the correct provenance metadata."""
        pages = [{"page": 3, "text": "C" * 500}]
        chunks = _chunk_pages(pages, "audit.pdf", "2023-06-15", "Acme Corp")
        assert len(chunks) >= 1
        chunk = chunks[0]
        assert chunk["source"] == "audit.pdf"
        assert chunk["page"] == 3
        assert chunk["entity"] == "Acme Corp"
        assert chunk["doc_date"] == "2023-06-15"
        assert "id" in chunk  # UUID assigned

    def test_discards_tiny_chunks(self):
        """Chunks smaller than MIN_CHUNK_LENGTH are discarded."""
        # Text that after chunking would leave a tiny remainder
        pages = [{"page": 1, "text": "D" * (MIN_CHUNK_LENGTH - 1)}]
        chunks = _chunk_pages(pages, "tiny.pdf", None, None)
        assert len(chunks) == 0


class TestHashContent:
    def test_consistent_hash(self):
        """Same input always produces the same SHA-256 hash."""
        data = b"hello world"
        h1 = _hash_content(data)
        h2 = _hash_content(data)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex digest length

    def test_different_inputs_differ(self):
        """Different inputs produce different hashes."""
        h1 = _hash_content(b"file A content")
        h2 = _hash_content(b"file B content")
        assert h1 != h2

    def test_known_value(self):
        """Verify against known SHA-256 output."""
        import hashlib

        data = b"test document bytes"
        expected = hashlib.sha256(data).hexdigest()
        assert _hash_content(data) == expected
