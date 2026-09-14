"""LangGraph RAG agent: retrieve -> synthesise -> validate."""
from __future__ import annotations

import re
from typing import Any, TypedDict

from loguru import logger
from openai import AsyncAzureOpenAI

from app.core.database import get_supabase
from app.core.settings import settings
from app.guardrails.confidence_gate import confidence_gate, score_confidence
from app.guardrails.output_validator import validate_output
from app.guardrails.pii_detector import scan_pii
from app.services.embedding_service import get_embedding

# Matches the "[doc:1a2b3c4d p.3]" labels _build_context_block prepends to
# each chunk and the system prompt asks the model to echo back inline —
# i.e. what the model actually cited, not just what was retrieved.
_CITATION_PATTERN = re.compile(r"\[doc:([0-9a-f]{1,8})\s+p\.(\S+?)\]")

MATCH_COUNT = 6

SYSTEM_PROMPT = (
    "You are AuditSys AI, a governed financial and audit document assistant. "
    "Answer strictly using the provided context excerpts. If the context does "
    "not contain the answer, say you don't have enough grounded evidence — "
    "never speculate or invent figures. Cite the source document/page for "
    "every factual claim."
)

PROMPT_VERSION = "rag-agent-v1"


class AgentState(TypedDict, total=False):
    question: str
    context: dict[str, Any]
    answer: str
    citations: list[dict]
    confidence_score: float
    error: str | None
    validation_passed: bool
    validation_errors: list[str]
    pii_detected: bool


async def retrieve_context(state: AgentState) -> AgentState:
    """pgvector hybrid search node."""
    question = state["question"]
    logger.info("node=retrieve_context question_len={}", len(question))

    try:
        query_embedding = await get_embedding(question)
        client = get_supabase()
        result = client.rpc(
            "match_document_chunks",
            {"query_embedding": query_embedding, "match_count": MATCH_COUNT},
        ).execute()
        chunks = result.data or []
    except Exception as exc:  # noqa: BLE001 - retrieval failure degrades gracefully
        logger.error("retrieve_context_failed error={}", exc)
        chunks = []

    return {**state, "context": {"chunks": chunks}}


def _build_context_block(chunks: list[dict]) -> str:
    parts = []
    for chunk in chunks:
        label = f"[doc:{chunk.get('document_id', '?')[:8]} p.{chunk.get('page_number', '?')}]"
        parts.append(f"{label} {chunk.get('content', '')}")
    return "\n\n".join(parts)


def _parse_cited_chunks(answer: str, chunks: list[dict]) -> list[dict]:
    """
    Find which of the retrieved chunks the model actually cited, by
    matching the "[doc:xxx p.N]" markers it was asked to echo back
    against the same document_id/page_number pairs handed to it in
    _build_context_block. Chunks the model never referenced are excluded
    — this is what makes citation coverage in score_confidence a real
    signal instead of a tautology (citations == retrieved_chunks always
    "matches").
    """
    matches = _CITATION_PATTERN.findall(answer)
    if not matches:
        return []

    cited = []
    seen = set()
    for doc_prefix, page in matches:
        for chunk in chunks:
            document_id = str(chunk.get("document_id") or "")
            page_number = chunk.get("page_number")
            page_str = str(page_number) if page_number is not None else "?"
            if document_id.startswith(doc_prefix) and page_str == page:
                key = (document_id, page_str)
                if key not in seen:
                    seen.add(key)
                    cited.append(chunk)
                break
    return cited


async def synthesise_answer(state: AgentState) -> AgentState:
    """Azure OpenAI answer synthesis node."""
    logger.info("node=synthesise_answer")
    chunks = state.get("context", {}).get("chunks", [])

    if not chunks:
        return {
            **state,
            "answer": (
                "No grounded evidence was found in the indexed documents for this "
                "question. Upload relevant documents or rephrase the query."
            ),
            "citations": [],
            "confidence_score": 0.0,
        }

    context_block = _build_context_block(chunks)
    client = AsyncAzureOpenAI(
        api_key=settings.azure_openai_api_key,
        azure_endpoint=settings.azure_openai_endpoint or "",
        api_version=settings.azure_openai_api_version,
    )
    response = await client.chat.completions.create(
        model=settings.azure_openai_deployment,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Context:\n{context_block}\n\nQuestion: {state['question']}",
            },
        ],
    )
    answer = response.choices[0].message.content or ""

    cited_chunks = _parse_cited_chunks(answer, chunks)
    confidence_score = await score_confidence(answer, chunks, cited_chunks)

    citations = [
        {
            "document_id": c.get("document_id"),
            "page_number": c.get("page_number"),
            "similarity": c.get("similarity"),
        }
        for c in cited_chunks
    ]

    return {
        **state,
        "answer": answer,
        "citations": citations,
        "confidence_score": confidence_score,
    }


async def validate_output_node(state: AgentState) -> AgentState:
    """Guardrails node: schema-leak/injection validation, then PII scan."""
    logger.info("node=validate_output")
    answer = state.get("answer", "")

    validation = await validate_output(answer)
    cleaned = validation.cleaned_text or answer

    pii = await scan_pii(cleaned)
    if pii.has_pii:
        cleaned = pii.anonymised_text

    if not validation.passed:
        logger.warning("output_validation_failed errors={}", validation.errors)

    return {
        **state,
        "answer": cleaned,
        "validation_passed": validation.passed,
        "validation_errors": validation.errors,
        "pii_detected": pii.has_pii,
    }


def build_graph():
    """Build LangGraph pipeline. Call once at startup."""
    from langgraph.graph import END, StateGraph

    graph = StateGraph(AgentState)
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("synthesise_answer", synthesise_answer)
    graph.add_node("validate_output", validate_output_node)

    graph.set_entry_point("retrieve_context")
    graph.add_edge("retrieve_context", "synthesise_answer")
    graph.add_edge("synthesise_answer", "validate_output")
    graph.add_edge("validate_output", END)

    return graph.compile()


_agent_graph = None


def get_agent_graph():
    """Singleton accessor — build the compiled graph once and reuse it."""
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = build_graph()
    return _agent_graph


async def run_agent(question: str) -> AgentState:
    graph = get_agent_graph()
    result = await graph.ainvoke({"question": question})
    passes_gate = confidence_gate(result.get("confidence_score", 0.0), settings.confidence_threshold)
    return {**result, "passes_confidence_gate": passes_gate}
