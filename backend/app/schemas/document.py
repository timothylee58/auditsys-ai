from pydantic import BaseModel


class DocumentMetadata(BaseModel):
    document_id: str
    filename: str
    entity: str | None = None
    doc_date: str | None = None


class IngestionResult(BaseModel):
    document_id: str
    filename: str
    chunk_count: int
    page_count: int
    content_hash: str
    status: str = "indexed"
