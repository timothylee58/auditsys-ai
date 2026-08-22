from fastapi import APIRouter, File, Form, Header, HTTPException, Query, UploadFile, status

from app.services import ingestion_service

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20MB

# TODO: Auth middleware is needed to validate the X-User-ID header (e.g. JWT
# verification). Currently the header is trusted without verification. This is
# out of scope for the ingestion pipeline feature.


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    user_id: str = Header(..., alias="X-User-ID"),
    entity: str | None = Form(default=None),
    doc_date: str | None = Form(default=None),
) -> dict:
    """Upload a PDF for ingestion: parse, chunk, embed, and index it."""
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 20MB upload limit")

    result = await ingestion_service.ingest_document(
        file_bytes=file_bytes,
        filename=file.filename or "document.pdf",
        user_id=user_id,
        entity=entity,
        doc_date=doc_date,
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
async def list_documents(
    user_id: str = Header(..., alias="X-User-ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> dict:
    """List the caller's indexed documents, newest first."""
    return await ingestion_service.list_documents(user_id=user_id, page=page, page_size=page_size)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    user_id: str = Header(..., alias="X-User-ID"),
) -> None:
    """Soft delete a document: verifies ownership, marks it deleted, removes chunks."""
    try:
        await ingestion_service.soft_delete_document(document_id, user_id=user_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Document not found")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Not authorized to delete this document")
