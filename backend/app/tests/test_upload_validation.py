"""Upload validation tests: magic-byte sniffing, streaming size cap, auth."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.core.auth import CurrentUser, get_current_user
from app.main import app
from app.schemas.document import IngestionResult

TEST_USER = CurrentUser(user_id="uploader-1", role="authenticated")


@pytest.fixture(autouse=True)
def _authed(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _make_pdf_bytes(page_text: str = "A" * 200) -> bytes:
    """Minimal valid PDF via pypdf (same helper approach as test_ingestion)."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class TestMagicByteValidation:
    def test_rejects_non_pdf_magic(self):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/documents/upload",
            files={"file": ("evil.pdf", b"#!/bin/bash\nrm -rf /", "application/pdf")},
        )
        assert response.status_code == 415
        assert "PDF" in response.json()["detail"]

    def test_rejects_plain_text_renamed_to_pdf(self):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/documents/upload",
            files={"file": ("notes.pdf", b"Just some text, definitely not a PDF", "application/pdf")},
        )
        assert response.status_code == 415

    def test_client_mime_type_is_not_trusted(self):
        """A file CLAIMING to be a PDF in its content-type still needs real magic bytes."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/documents/upload",
            files={"file": ("doc.pdf", b"PK\x03\x04 zip masquerading as pdf", "application/pdf")},
        )
        assert response.status_code == 415


class TestSizeCap:
    def test_rejects_oversized_before_full_buffer(self, monkeypatch):
        """A body over the cap must 413 — and never reach ingestion."""
        called = False

        async def _fail(*args, **kwargs):
            nonlocal called
            called = True
            raise AssertionError("ingestion must not run for oversized uploads")

        monkeypatch.setattr(
            "app.api.routes.documents.ingestion_service.ingest_document", _fail
        )

        client = TestClient(app, raise_server_exceptions=False)
        big = b"%PDF-1.4" + b"\x00" * (20 * 1024 * 1024 + 1)
        response = client.post(
            "/documents/upload",
            files={"file": ("big.pdf", big, "application/pdf")},
        )
        assert response.status_code == 413
        assert called is False

    def test_rejects_empty_body(self):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/documents/upload",
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        assert response.status_code == 415


class TestFilenameSanitisation:
    def test_path_traversal_stripped(self):
        """'../../etc/passwd.pdf' must not survive as a filename."""
        captured = {}

        async def _fake_ingest(*, file_bytes, filename, user_id, entity=None, doc_date=None):
            captured["filename"] = filename
            return IngestionResult(
                document_id="doc-1",
                filename=filename,
                chunk_count=1,
                page_count=1,
                content_hash="0" * 64,
                status="indexed",
            )

        import app.api.routes.documents as documents_route

        original = documents_route.ingestion_service.ingest_document
        documents_route.ingestion_service.ingest_document = _fake_ingest
        try:
            client = TestClient(app)
            response = client.post(
                "/documents/upload",
                files={"file": ("../../etc/passwd.pdf", _make_pdf_bytes(), "application/pdf")},
            )
            assert response.status_code == 201
            assert response.json()["filename"] == "passwd.pdf"
            assert captured["filename"] == "passwd.pdf"
        finally:
            documents_route.ingestion_service.ingest_document = original


class TestHappyPath:
    def test_valid_pdf_reaches_ingestion(self, monkeypatch):
        captured = {}

        async def _fake_ingest(*, file_bytes, filename, user_id, entity=None, doc_date=None):
            captured["user_id"] = user_id
            captured["filename"] = filename
            return IngestionResult(
                document_id="doc-1",
                filename=filename,
                chunk_count=3,
                page_count=1,
                content_hash="0" * 64,
                status="indexed",
            )

        monkeypatch.setattr(
            "app.api.routes.documents.ingestion_service.ingest_document", _fake_ingest
        )

        client = TestClient(app)
        response = client.post(
            "/documents/upload",
            files={"file": ("report.pdf", _make_pdf_bytes(), "application/pdf")},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["chunk_count"] == 3
        # Identity comes from the verified token, not from any client header.
        assert captured["user_id"] == "uploader-1"
