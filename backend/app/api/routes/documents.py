import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from app.core.auth import CurrentUser, get_current_user
from app.core.rate_limit import rate_limited
from app.core.settings import settings
from app.services import ingestion_service

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20MB
_PDF_MAGIC = b"%PDF-"
_UPLOAD_CHUNK = 1024 * 1024  # read uploads in 1MB chunks


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    user: CurrentUser = Depends(rate_limited("upload", settings.upload_rate_limit_per_minute)),
    entity: str | None = Form(default=None),
    doc_date: str | None = Form(default=None),
) -> dict:
    """Upload a PDF for ingestion: parse, chunk, embed, and index it.

    The content type is verified via magic bytes (not the client-declared
    MIME type), and the size cap is enforced while streaming so oversized
    bodies are rejected without being fully buffered first.
    """
    # Magic-byte sniff: a PDF must start with "%PDF-". The client-declared
    # content_type is attacker-controlled and is not trusted.
    head = await file.read(len(_PDF_MAGIC))
    if head != _PDF_MAGIC:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File does not appear to be a valid PDF",
        )

    # Stream the remainder with a hard cap so a 2GB body is rejected at the
    # cap instead of being read fully into memory first.
    chunks = [head]
    total = len(head)
    while True:
        block = await file.read(_UPLOAD_CHUNK)
        if not block:
            break
        total += len(block)
        if total > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="File exceeds the 20MB upload limit",
            )
        chunks.append(block)
    file_bytes = b"".join(chunks)

    # Defend against path traversal / control chars in the client filename.
    filename = os.path.basename(file.filename or "document.pdf").strip() or "document.pdf"
    filename = filename.replace("\x00", "")[:255]

    result = await ingestion_service.ingest_document(
        file_bytes=file_bytes,
        filename=filename,
        user_id=user.user_id,
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
    user: CurrentUser = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> dict:
    """List the caller's indexed documents, newest first."""
    return await ingestion_service.list_documents(user_id=user.user_id, page=page, page_size=page_size)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> None:
    """Soft delete a document: verifies ownership, marks it deleted, removes chunks."""
    try:
        await ingestion_service.soft_delete_document(document_id, user_id=user.user_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Document not found") from None
    except PermissionError:
        raise HTTPException(status_code=403, detail="Not authorized to delete this document") from None
