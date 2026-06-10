from dataclasses import dataclass

from loguru import logger

from app.core.settings import settings
from app.guardrails.confidence_gate import confidence_gate
from app.guardrails.output_validator import validate_output
from app.guardrails.pii_detector import redact_pii


@dataclass
class QueryResult:
    answer: str
    confidence: float
    sources: list[dict]
    flagged_for_review: bool


async def run_query(question: str) -> QueryResult:
    logger.info("query received question_len={}", len(question))

    # PII check on input
    safe_question = redact_pii(question) if settings.presidio_enabled else question

    # TODO: replace stub with LangGraph RAG agent call
    raw_answer = (
        f"Based on the indexed audit documents, no direct policy reference was found "
        f"matching '{safe_question[:60]}...'. Upload relevant documents to enable grounded answers."
    )
    confidence = 0.55
    sources: list[dict] = []

    # Output validation
    validated_answer = validate_output(raw_answer)

    flagged = not confidence_gate(confidence, settings.confidence_threshold)
    if flagged:
        logger.warning("low confidence query flagged confidence={:.2f}", confidence)

    return QueryResult(
        answer=validated_answer,
        confidence=confidence,
        sources=sources,
        flagged_for_review=flagged,
    )
