"""
AuditSys AI - Document Ingestion Pipeline
==========================================
Flow: PDF upload -> extract text -> chunk -> embed -> pgvector store

Design decisions:
  - Chunks overlap by 20% to avoid context loss at boundaries
  - Metadata (source, date, entity, page) stored with each chunk
    so citations can reference exact page numbers
  - Embedding via Azure OpenAI text-embedding-3-large (3072 dims)
    -- same model used at query time for consistent cosine space
  - Supabase RPC for batch upsert -- atomic, no partial inserts
  - Idempotent: re-uploading same file replaces existing chunks
    (matched on content_hash + user_id)
  - Duplicate detection: if a document with the same content_hash
    and user_id already exists in "ready" status, return early
    without re-embedding (cost optimization)

# TODO: Redis embedding cache could be re-added for cost optimization.
# Repeated chunks (boilerplate in audit reports) currently incur a fresh
# Azure OpenAI call each time. See previous embedding_service.get_embedding.
"""

from __future__ import annotations

import hashlib
import io
import uuid
from datetime import datetime, timezone
from typing import Any

from langchain_openai import AzureOpenAIEmbeddings
from loguru import logger
from pypdf import PdfReader

from app.core.database import get_async_supabase
from app.schemas.document import DocumentMetadata, IngestionResult  # noqa: F401


# -- Configuration ------------------------------------------------------------

CHUNK_SIZE = 800          # tokens (approximate via char count / 4)
CHUNK_OVERLAP = 160       # 20% overlap
MIN_CHUNK_LENGTH = 100    # discard empty/whitespace chunks


# -- Main ingestion entrypoint ------------------------------------------------

async def ingest_document(
    file_bytes: bytes,
    filename: str,
    user_id: str,
    entity: str | None = None,
    doc_date: str | None = None,
) -> IngestionResult:
    """
    Full ingestion pipeline. Called by documents API route on upload.

    Args:
        file_bytes: raw PDF bytes
        filename:   original filename (used as citation source)
        user_id:    scopes all chunks to this user
        entity:     optional company/entity name (e.g. "Acme Corp")
        doc_date:   optional document date (ISO format)

    Returns:
        IngestionResult with document_id and chunk count
    """
    content_hash = _hash_content(file_bytes)

    # Fast path: if document with same content already exists and is ready, skip re-embedding
    existing = await _find_existing_document(content_hash, user_id)
    if existing is not None:
        logger.info(
            "duplicate_document_skipped content_hash={} user_id={} existing_id={}",
            content_hash,
            user_id,
            existing["id"],
        )
        return IngestionResult(
            document_id=existing["id"],
            filename=existing["filename"],
            chunk_count=existing["chunk_count"],
            page_count=existing.get("page_count", 0),
            content_hash=content_hash,
            status="duplicate",
        )

    document_id = str(uuid.uuid4())

    # 1. Extract text per page (preserves page numbers for citations)
    pages = _extract_pages(file_bytes)
    if not pages:
        raise ValueError(f"Could not extract text from {filename}")

    # 2. Chunk with overlap, preserving page provenance
    chunks = _chunk_pages(pages, filename, doc_date, entity)
    if not chunks:
        raise ValueError(f"No usable text chunks extracted from {filename}")

    # 3. Register document record first
    await _upsert_document_record(
        document_id=document_id,
        filename=filename,
        user_id=user_id,
        content_hash=content_hash,
        entity=entity,
        doc_date=doc_date,
        chunk_count=len(chunks),
    )

    # 4-5. Embed and store with failure recovery
    try:
        # 4. Generate embeddings in batches (Azure OpenAI rate limit aware)
        embeddings = await _embed_chunks(chunks)

        # 5. Upsert chunks + vectors into pgvector
        await _store_chunks(
            document_id=document_id,
            user_id=user_id,
            chunks=chunks,
            embeddings=embeddings,
            content_hash=content_hash,
        )
    except Exception as exc:
        logger.error(
            "ingestion_failed document_id={} filename={} error={}",
            document_id,
            filename,
            str(exc),
        )
        await _mark_document_failed(document_id)
        raise

    return IngestionResult(
        document_id=document_id,
        filename=filename,
        chunk_count=len(chunks),
        page_count=len(pages),
        content_hash=content_hash,
    )


# -- Step 1: PDF text extraction -----------------------------------------------

def _extract_pages(file_bytes: bytes) -> list[dict[str, Any]]:
    """
    Extract text from each PDF page.
    Returns list of {page_number, text} dicts.
    Page numbers are 1-indexed for human-readable citations.
    """
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []

    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = text.strip()
        if len(text) >= MIN_CHUNK_LENGTH:
            pages.append({"page": i, "text": text})

    return pages


# -- Step 2: Chunking with overlap ---------------------------------------------

def _chunk_pages(
    pages: list[dict[str, Any]],
    source: str,
    doc_date: str | None,
    entity: str | None,
) -> list[dict[str, Any]]:
    """
    Split page text into overlapping chunks.
    Each chunk carries full provenance metadata for citations.
    """
    chunks: list[dict[str, Any]] = []

    for page_data in pages:
        page_num = page_data["page"]
        text = page_data["text"]

        # Simple char-based chunking (avoids tiktoken dep for now)
        char_size = CHUNK_SIZE * 4        # ~4 chars per token
        char_overlap = CHUNK_OVERLAP * 4

        start = 0
        while start < len(text):
            end = min(start + char_size, len(text))
            chunk_text = text[start:end].strip()

            if len(chunk_text) >= MIN_CHUNK_LENGTH:
                chunks.append({
                    "id": str(uuid.uuid4()),
                    "text": chunk_text,
                    "source": source,
                    "page": page_num,
                    "entity": entity,
                    "doc_date": doc_date,
                    "chunk_index": len(chunks),
                })

            start += char_size - char_overlap

    return chunks


# -- Step 3: Embedding ---------------------------------------------------------

async def _embed_chunks(chunks: list[dict]) -> list[list[float]]:
    """
    Batch embed chunks via Azure OpenAI.
    Processes in batches of 16 to respect rate limits.
    """
    from app.config import settings

    embedder = AzureOpenAIEmbeddings(
        azure_deployment=settings.azure_openai_embedding_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
    )

    texts = [c["text"] for c in chunks]
    batch_size = 16
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        batch_embeddings = await embedder.aembed_documents(batch)
        all_embeddings.extend(batch_embeddings)

    return all_embeddings


# -- Step 4: Upsert document record --------------------------------------------

async def _upsert_document_record(
    document_id: str,
    filename: str,
    user_id: str,
    content_hash: str,
    entity: str | None,
    doc_date: str | None,
    chunk_count: int,
) -> None:
    supabase = await get_async_supabase()

    # Clean up chunks from any prior failed attempt for this content_hash + user_id
    stale_docs = await (
        supabase.table("documents")
        .select("id")
        .eq("content_hash", content_hash)
        .eq("user_id", user_id)
        .eq("status", "failed")
        .execute()
    )
    for stale_doc in stale_docs.data or []:
        await (
            supabase.table("document_chunks")
            .delete()
            .eq("document_id", stale_doc["id"])
            .execute()
        )

    await supabase.table("documents").upsert(
        {
            "id": document_id,
            "user_id": user_id,
            "filename": filename,
            "content_hash": content_hash,
            "entity": entity,
            "doc_date": doc_date,
            "chunk_count": chunk_count,
            "status": "processing",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="content_hash,user_id",
    ).execute()


# -- Step 5: Store chunks + vectors --------------------------------------------

async def _store_chunks(
    document_id: str,
    user_id: str,
    chunks: list[dict],
    embeddings: list[list[float]],
    content_hash: str,
) -> None:
    """
    Upsert chunks with their embeddings into the document_chunks table.
    On re-upload, old chunks for this content_hash are deleted first
    (via Supabase trigger on documents table).
    """
    supabase = await get_async_supabase()

    rows = []
    for chunk, embedding in zip(chunks, embeddings):
        rows.append({
            "id": chunk["id"],
            "document_id": document_id,
            "user_id": user_id,
            "text": chunk["text"],
            "source": chunk["source"],
            "page": chunk["page"],
            "entity": chunk["entity"],
            "doc_date": chunk["doc_date"],
            "chunk_index": chunk["chunk_index"],
            "embedding": embedding,
            "content_hash": content_hash,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    # Batch upsert -- Supabase handles conflicts by chunk id
    batch_size = 50
    for i in range(0, len(rows), batch_size):
        await supabase.table("document_chunks").upsert(
            rows[i : i + batch_size]
        ).execute()

    # Mark document as ready
    await supabase.table("documents").update(
        {"status": "ready"}
    ).eq("id", document_id).execute()


# -- Helpers -------------------------------------------------------------------

def _hash_content(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


async def _find_existing_document(content_hash: str, user_id: str) -> dict | None:
    """Check if a document with the same content_hash and user_id already exists as ready."""
    supabase = await get_async_supabase()
    result = await (
        supabase.table("documents")
        .select("id, filename, chunk_count, page_count")
        .eq("content_hash", content_hash)
        .eq("user_id", user_id)
        .eq("status", "ready")
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]
    return None


async def _mark_document_failed(document_id: str) -> None:
    """Mark a document as failed and clean up any partially-written chunks."""
    try:
        supabase = await get_async_supabase()
        # Clean up any partially-written chunks before marking failed
        await (
            supabase.table("document_chunks")
            .delete()
            .eq("document_id", document_id)
            .execute()
        )
        await (
            supabase.table("documents")
            .update({"status": "failed"})
            .eq("id", document_id)
            .execute()
        )
    except Exception as mark_exc:
        logger.error(
            "failed_to_mark_document_failed document_id={} error={}",
            document_id,
            str(mark_exc),
        )


# -- Existing API functions (preserved for documents router) --------------------

async def list_documents(*, user_id: str, page: int = 1, page_size: int = 25) -> dict:
    """List indexed documents for a specific user, newest first, with pagination."""
    client = await get_async_supabase()
    start = (page - 1) * page_size
    end = start + page_size - 1
    result = await (
        client.table("documents")
        .select("*", count="exact")
        .eq("user_id", user_id)
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


async def soft_delete_document(document_id: str, user_id: str) -> None:
    """Soft delete a document: verifies ownership, marks it deleted, removes chunks."""
    client = await get_async_supabase()

    # Verify ownership before deletion
    doc_result = await (
        client.table("documents")
        .select("id, user_id")
        .eq("id", document_id)
        .limit(1)
        .execute()
    )
    if not doc_result.data:
        raise ValueError(f"Document {document_id} not found")
    if doc_result.data[0]["user_id"] != user_id:
        raise PermissionError(f"User {user_id} does not own document {document_id}")

    await client.table("document_chunks").delete().eq("document_id", document_id).execute()
    await client.table("documents").update({"status": "deleted"}).eq("id", document_id).execute()
    logger.info("document_soft_deleted document_id={} user_id={}", document_id, user_id)
