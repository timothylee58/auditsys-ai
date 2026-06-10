from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.query_service import QueryResult, run_query

router = APIRouter(prefix="/query", tags=["query"])


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)


class QueryResponse(BaseModel):
    answer: str
    confidence: float
    sources: list[dict]
    flagged_for_review: bool


@router.post("", response_model=QueryResponse)
async def query_documents(body: QueryRequest) -> QueryResponse:
    result: QueryResult = await run_query(body.question)
    return QueryResponse(
        answer=result.answer,
        confidence=result.confidence,
        sources=result.sources,
        flagged_for_review=result.flagged_for_review,
    )
