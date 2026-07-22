"""Document ingestion pipeline: PDF -> chunk -> embed -> pgvector.

Handles:
1. PDF text extraction (pypdf)
2. Chunking with overlap for context preservation
3. Embedding via Azure OpenAI text-embedding-3-large
4. Storage in Supabase (pgvector document_chunks table)
"""

from __future__ import annotations

import hashlib
import uuid
from io import BytesIO

from loguru import logger

from app.config import settings
from app.core.database import get_supabase
from app.schemas.document import IngestionResult
from app.services.embedding_service import get_embedding

# Chunking parameters
_CHUNK_SIZE = 1000  # characters
_CHUNK_OVERLAP = 200


def _extract_text_from_pdf(pdf_bytes: bytes) -> tuple[str, int]:
    """Extract full text and page count from a PDF file."""
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(pdf_bytes))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text)
    full_text = "\n\n".join(pages)
    return full_text, len(reader.pages)


def _chunk_text(text: str, chunk_size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks."""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


async def ingest_document(
    filename: str,
    pdf_bytes: bytes,
    user_id: str = "system",
    entity: str | None = None,
    doc_date: str | None = None,
) -> IngestionResult:
    """Full ingestion pipeline for a single PDF document.

    Args:
        filename: Original filename of the uploaded PDF.
        pdf_bytes: Raw PDF file content.
        user_id: ID of the uploading user.
        entity: Optional associated entity/client name.
        doc_date: Optional document date.

    Returns:
        IngestionResult with document_id, chunk_count, page_count, content_hash.
    """
    document_id = str(uuid.uuid4())
    content_hash = hashlib.sha256(pdf_bytes).hexdigest()

    logger.info(
        "ingestion_start document_id={} filename={} size_bytes={}",
        document_id,
        filename,
        len(pdf_bytes),
    )

    # Step 1: Extract text from PDF
    full_text, page_count = _extract_text_from_pdf(pdf_bytes)
    logger.info(
        "text_extracted document_id={} pages={} chars={}",
        document_id,
        page_count,
        len(full_text),
    )

    # Step 2: Chunk the text
    chunks = _chunk_text(full_text)
    logger.info("chunking_complete document_id={} chunk_count={}", document_id, len(chunks))

    # Step 3: Store document metadata in Supabase
    supabase = get_supabase()
    supabase.table("documents").insert(
        {
            "id": document_id,
            "filename": filename,
            "status": "indexed",
            "page_count": page_count,
            "chunk_count": len(chunks),
            "content_hash": content_hash,
            "uploaded_by": user_id,
            "entity": entity,
            "doc_date": doc_date,
        }
    ).execute()

    # Step 4: Embed and store each chunk
    for idx, chunk_text in enumerate(chunks):
        chunk_id = str(uuid.uuid4())
        try:
            embedding = await get_embedding(chunk_text)
            supabase.table("document_chunks").insert(
                {
                    "id": chunk_id,
                    "document_id": document_id,
                    "chunk_index": idx,
                    "content": chunk_text,
                    "embedding": embedding,
                    "token_count": len(chunk_text) // 4,  # rough estimate
                }
            ).execute()
        except Exception as exc:
            logger.error(
                "chunk_embed_failed document_id={} chunk_idx={} error={}",
                document_id,
                idx,
                str(exc),
            )

    logger.info(
        "ingestion_complete document_id={} chunks_stored={}",
        document_id,
        len(chunks),
    )

    return IngestionResult(
        document_id=document_id,
        filename=filename,
        chunk_count=len(chunks),
        page_count=page_count,
        content_hash=content_hash,
    )
