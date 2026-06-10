from fastapi import APIRouter

from app.models.schemas import DocumentRecord

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[DocumentRecord])
def list_documents() -> list[DocumentRecord]:
    return [
        DocumentRecord(
            id="doc_001",
            name="FY2025 procurement controls.pdf",
            status="indexed",
            uploaded_at="2026-06-02",
            risk_score=72,
        ),
        DocumentRecord(
            id="doc_002",
            name="Vendor onboarding exceptions.xlsx",
            status="needs_review",
            uploaded_at="2026-06-02",
            risk_score=84,
        ),
    ]
