"""Document management routes.

Endpoints:
- POST /documents/upload — Upload a PDF for ingestion
- GET /documents — List user's documents (paginated)
- DELETE /documents/{id} — Soft delete (sets status="deleted", removes chunks)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from loguru import logger

from app.core.database import get_supabase
from app.schemas.document import DocumentListPage, IngestionResult
from app.services.ingestion_service import ingest_document

router = APIRouter(prefix="/documents", tags=["documents"])

# Constants
_MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB
_ALLOWED_CONTENT_TYPE = "application/pdf"


@router.post("/upload", response_model=IngestionResult, status_code=201)
async def upload_document(file: UploadFile) -> IngestionResult:
    """Upload a PDF document for ingestion into the RAG pipeline.

    Accepts a single PDF file (max 20MB). The file is processed through
    the ingestion pipeline: text extraction, chunking, embedding, and
    storage in pgvector.

    Returns:
        201 Created with IngestionResult containing document_id and metadata.

    Raises:
        400: Invalid file type or empty file.
        413: File exceeds 20MB size limit.
    """
    # Validate content type
    if file.content_type != _ALLOWED_CONTENT_TYPE:
        return JSONResponse(
            status_code=400,
            content={
                "type": "https://auditsys.ai/errors/invalid-content-type",
                "title": "Invalid Content Type",
                "status": 400,
                "detail": f"Only PDF files are accepted. Received: {file.content_type}",
            },
        )

    # Read file content
    content = await file.read()

    # Validate file size
    if len(content) > _MAX_FILE_SIZE_BYTES:
        return JSONResponse(
            status_code=413,
            content={
                "type": "https://auditsys.ai/errors/file-too-large",
                "title": "File Too Large",
                "status": 413,
                "detail": f"File exceeds maximum size of 20MB. Received: {len(content)} bytes.",
            },
        )

    if len(content) == 0:
        return JSONResponse(
            status_code=400,
            content={
                "type": "https://auditsys.ai/errors/empty-file",
                "title": "Empty File",
                "status": 400,
                "detail": "Uploaded file is empty.",
            },
        )

    filename = file.filename or "unnamed.pdf"
    logger.info("document_upload_start filename={} size_bytes={}", filename, len(content))

    try:
        result = await ingest_document(filename=filename, pdf_bytes=content)
        return result
    except Exception as exc:
        logger.error("document_upload_failed filename={} error={}", filename, str(exc))
        raise HTTPException(
            status_code=500,
            detail={
                "type": "https://auditsys.ai/errors/ingestion-failed",
                "title": "Ingestion Failed",
                "status": 500,
                "detail": "Document ingestion failed. Please try again.",
            },
        ) from exc


@router.get("", response_model=DocumentListPage)
async def list_documents(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
) -> DocumentListPage:
    """List user's documents with pagination.

    Returns paginated list of documents ordered by upload date (newest first).
    Soft-deleted documents are excluded.
    """
    supabase = get_supabase()
    offset = (page - 1) * page_size

    result = (
        supabase.table("documents")
        .select("*", count="exact")
        .neq("status", "deleted")
        .order("uploaded_at", desc=True)
        .range(offset, offset + page_size - 1)
        .execute()
    )

    total = result.count if result.count is not None else 0
    documents = result.data or []

    return DocumentListPage(
        documents=documents,
        total=total,
        page=page,
        page_size=page_size,
        has_next=(offset + page_size) < total,
    )


@router.delete("/{document_id}", status_code=200)
async def delete_document(document_id: str) -> dict:
    """Soft delete a document and remove its chunks.

    Sets the document status to "deleted" and removes associated
    chunks from the document_chunks table.

    Returns:
        200 OK with confirmation message.

    Raises:
        404: Document not found.
    """
    supabase = get_supabase()

    # Verify document exists
    doc_result = (
        supabase.table("documents")
        .select("id, status")
        .eq("id", document_id)
        .execute()
    )

    if not doc_result.data:
        return JSONResponse(
            status_code=404,
            content={
                "type": "https://auditsys.ai/errors/document-not-found",
                "title": "Document Not Found",
                "status": 404,
                "detail": f"Document with id '{document_id}' does not exist.",
            },
        )

    if doc_result.data[0]["status"] == "deleted":
        return JSONResponse(
            status_code=404,
            content={
                "type": "https://auditsys.ai/errors/document-not-found",
                "title": "Document Not Found",
                "status": 404,
                "detail": f"Document with id '{document_id}' has already been deleted.",
            },
        )

    # Soft delete the document
    supabase.table("documents").update({"status": "deleted"}).eq("id", document_id).execute()

    # Remove chunks
    supabase.table("document_chunks").delete().eq("document_id", document_id).execute()

    logger.info("document_deleted document_id={}", document_id)
    return {"message": "Document deleted successfully", "document_id": document_id}
