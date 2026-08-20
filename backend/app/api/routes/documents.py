from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

from app.services import ingestion_service

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20MB


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(file: UploadFile = File(...)) -> dict:
    """Upload a PDF for ingestion: parse, chunk, embed, and index it."""
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 20MB upload limit")

    result = await ingestion_service.ingest_document(
        filename=file.filename or "document.pdf",
        file_bytes=file_bytes,
    )
    return {
        "document_id": result.document_id,
        "filename": result.filename,
        "chunk_count": result.chunk_count,
        "page_count": result.page_count,
        "content_hash": result.content_hash,
        "status": result.status,
    }


@router.get("")
async def list_documents(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)) -> dict:
    """List the caller's indexed documents, newest first."""
    return await ingestion_service.list_documents(page=page, page_size=page_size)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: str) -> None:
    """Soft delete a document: marks it deleted and removes its chunks."""
    await ingestion_service.soft_delete_document(document_id)
