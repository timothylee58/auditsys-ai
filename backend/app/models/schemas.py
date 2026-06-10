from pydantic import BaseModel, Field


class DocumentRecord(BaseModel):
    id: str
    name: str
    status: str
    uploaded_at: str = Field(serialization_alias="uploadedAt")
    risk_score: int = Field(serialization_alias="riskScore", ge=0, le=100)


class AuditEvent(BaseModel):
    id: str
    actor: str
    action: str
    target: str
    created_at: str = Field(serialization_alias="createdAt")


class ReviewItem(BaseModel):
    id: str
    title: str
    severity: str
    assignee: str
