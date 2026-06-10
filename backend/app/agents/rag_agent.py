"""LangGraph RAG agent — stub ready for full implementation."""
from typing import TypedDict

from langchain_core.messages import BaseMessage
from loguru import logger


class AgentState(TypedDict):
    messages: list[BaseMessage]
    context: dict
    metadata: dict
    error: str | None


async def retrieve_context(state: AgentState) -> AgentState:
    """pgvector hybrid search node."""
    logger.info("node=retrieve_context")
    # TODO: embed query, search supabase pgvector
    return {**state, "context": {"chunks": [], "scores": []}}


async def synthesise_answer(state: AgentState) -> AgentState:
    """Azure OpenAI answer synthesis node."""
    logger.info("node=synthesise_answer")
    # TODO: call Azure OpenAI with retrieved chunks as context
    return {**state, "metadata": {**state.get("metadata", {}), "answer": ""}}


async def validate_output(state: AgentState) -> AgentState:
    """Guardrails + confidence gate node."""
    logger.info("node=validate_output")
    return state


def build_graph():
    """Build LangGraph pipeline. Call once at startup."""
    from langgraph.graph import END, StateGraph

    graph = StateGraph(AgentState)
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("synthesise_answer", synthesise_answer)
    graph.add_node("validate_output", validate_output)

    graph.set_entry_point("retrieve_context")
    graph.add_edge("retrieve_context", "synthesise_answer")
    graph.add_edge("synthesise_answer", "validate_output")
    graph.add_edge("validate_output", END)

    return graph.compile()
