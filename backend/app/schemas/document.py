"""Document-related request/response schemas."""

from pydantic import BaseModel, Field


class DocumentMetadata(BaseModel):
    """Metadata attached to an uploaded document."""

    document_id: str = Field(..., description="Unique document identifier")
    filename: str = Field(..., description="Original filename")
    entity: str | None = Field(default=None, description="Associated entity/client name")
    doc_date: str | None = Field(default=None, description="Document date (ISO 8601)")


class IngestionResult(BaseModel):
    """Result returned after successful document ingestion."""

    document_id: str = Field(..., description="Unique document identifier")
    filename: str = Field(..., description="Original filename")
    chunk_count: int = Field(..., ge=0, description="Number of text chunks created")
    page_count: int = Field(..., ge=0, description="Number of pages in the document")
    content_hash: str = Field(..., description="SHA-256 hash of document content")


class DocumentListItem(BaseModel):
    """Single document in a list response."""

    id: str
    filename: str
    status: str = Field(..., description="indexed | processing | deleted")
    page_count: int
    chunk_count: int
    content_hash: str
    uploaded_at: str
    uploaded_by: str | None = None


class DocumentListPage(BaseModel):
    """Paginated document list."""

    documents: list[DocumentListItem]
    total: int
    page: int
    page_size: int
    has_next: bool
