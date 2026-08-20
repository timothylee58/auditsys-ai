"""PDF ingestion pipeline: parse -> chunk -> embed -> store in pgvector."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO

from loguru import logger
from pypdf import PdfReader

from app.core.database import get_supabase
from app.services.embedding_service import get_embedding

CHUNK_SIZE = 1000  # characters
CHUNK_OVERLAP = 150

DOCUMENTS_TABLE = "documents"
CHUNKS_TABLE = "document_chunks"


@dataclass
class IngestionResult:
    document_id: str
    filename: str
    chunk_count: int
    page_count: int
    content_hash: str
    status: str = "indexed"
    error: str | None = None


@dataclass
class _PageChunk:
    content: str
    page_number: int


def _extract_pages(file_bytes: bytes) -> list[str]:
    reader = PdfReader(BytesIO(file_bytes))
    return [page.extract_text() or "" for page in reader.pages]


def _chunk_pages(pages: list[str]) -> list[_PageChunk]:
    chunks: list[_PageChunk] = []
    for page_number, text in enumerate(pages, start=1):
        text = text.strip()
        if not text:
            continue
        start = 0
        while start < len(text):
            end = min(start + CHUNK_SIZE, len(text))
            chunks.append(_PageChunk(content=text[start:end], page_number=page_number))
            if end == len(text):
                break
            start = end - CHUNK_OVERLAP
    return chunks


async def ingest_document(
    *,
    filename: str,
    file_bytes: bytes,
    entity: str | None = None,
    doc_date: str | None = None,
    uploaded_by: str | None = None,
) -> IngestionResult:
    """Parse a PDF, chunk it, embed each chunk, and persist to Supabase."""
    content_hash = hashlib.sha256(file_bytes).hexdigest()
    client = get_supabase()

    existing = (
        client.table(DOCUMENTS_TABLE)
        .select("id")
        .eq("content_hash", content_hash)
        .neq("status", "deleted")
        .limit(1)
        .execute()
    )
    if existing.data:
        doc = existing.data[0]
        logger.info("ingest_skip_duplicate content_hash={}", content_hash[:12])
        return IngestionResult(
            document_id=doc["id"],
            filename=filename,
            chunk_count=0,
            page_count=0,
            content_hash=content_hash,
            status="duplicate",
        )

    pages = _extract_pages(file_bytes)
    page_chunks = _chunk_pages(pages)

    doc_row = (
        client.table(DOCUMENTS_TABLE)
        .insert(
            {
                "filename": filename,
                "entity": entity,
                "doc_date": doc_date,
                "content_hash": content_hash,
                "page_count": len(pages),
                "chunk_count": 0,
                "status": "processing",
                "uploaded_by": uploaded_by,
            }
        )
        .execute()
    )
    document_id = doc_row.data[0]["id"]

    try:
        chunk_rows = []
        for index, chunk in enumerate(page_chunks):
            embedding = await get_embedding(chunk.content)
            chunk_rows.append(
                {
                    "document_id": document_id,
                    "chunk_index": index,
                    "content": chunk.content,
                    "embedding": embedding,
                    "page_number": chunk.page_number,
                    "token_count": len(chunk.content) // 4,
                }
            )

        if chunk_rows:
            client.table(CHUNKS_TABLE).insert(chunk_rows).execute()

        client.table(DOCUMENTS_TABLE).update(
            {"status": "indexed", "chunk_count": len(chunk_rows)}
        ).eq("id", document_id).execute()

        logger.info(
            "ingest_complete document_id={} chunks={} pages={}",
            document_id,
            len(chunk_rows),
            len(pages),
        )
        return IngestionResult(
            document_id=document_id,
            filename=filename,
            chunk_count=len(chunk_rows),
            page_count=len(pages),
            content_hash=content_hash,
        )
    except Exception as exc:
        client.table(DOCUMENTS_TABLE).update({"status": "failed"}).eq("id", document_id).execute()
        logger.error("ingest_failed document_id={} error={}", document_id, exc)
        raise


async def list_documents(*, page: int = 1, page_size: int = 25) -> dict:
    client = get_supabase()
    start = (page - 1) * page_size
    end = start + page_size - 1
    result = (
        client.table(DOCUMENTS_TABLE)
        .select("*", count="exact")
        .neq("status", "deleted")
        .order("created_at", desc=True)
        .range(start, end)
        .execute()
    )
    total = result.count or 0
    return {
        "documents": result.data or [],
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": start + page_size < total,
    }


async def soft_delete_document(document_id: str) -> None:
    client = get_supabase()
    client.table(CHUNKS_TABLE).delete().eq("document_id", document_id).execute()
    client.table(DOCUMENTS_TABLE).update({"status": "deleted"}).eq("id", document_id).execute()
    logger.info("document_soft_deleted document_id={}", document_id)
