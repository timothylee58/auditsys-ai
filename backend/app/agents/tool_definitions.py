"""
AuditSys AI — Governed Read-Only Tool Definitions
==================================================
Every tool enforces:
  - user_id scoping (RLS at app layer, not just DB)
  - read-only: no INSERT / UPDATE / DELETE
  - column allow-lists: raw internal fields never returned
  - input validation via Pydantic

The agent never touches the DB directly — only through these tools.

Note: these tools are not yet wired into `rag_agent.py`'s retrieval node,
and `user_id` is not yet threaded through the query pipeline (no auth
layer exists). They are landed here as the governed data-access surface
the agent will call once auth is in place; `retrieve_context` in
`rag_agent.py` continues to call `match_document_chunks` directly (with
no user_id filter) until that wiring happens.
"""

from typing import Any

from pydantic import BaseModel, Field

from app.core.database import get_supabase

# ── Allow-lists (columns safe to return to LLM) ──────────────────────────────

CHUNK_ALLOWED_FIELDS = {"text", "source", "page", "entity", "doc_date", "score"}
METRIC_ALLOWED_FIELDS = {"metric_name", "value", "period", "unit", "source_doc"}
SCHEMA_ALLOWED_FIELDS = {"table_name", "column_name", "description", "data_type"}


# ── Tool: vector_search ───────────────────────────────────────────────────────


class VectorSearchInput(BaseModel):
    query_vector: list[float] = Field(..., description="Embedding vector of the query")
    user_id: str = Field(..., description="Scopes search to user's documents only")
    top_k: int = Field(default=6, ge=1, le=20)
    similarity_threshold: float = Field(default=0.5, ge=0.0, le=1.0)


async def vector_search(
    query_vector: list[float],
    user_id: str,
    top_k: int = 6,
    similarity_threshold: float = 0.5,
) -> list[dict[str, Any]]:
    """
    Semantic search over user-scoped document chunks.
    Calls Supabase RPC — pgvector cosine similarity.
    Returns only CHUNK_ALLOWED_FIELDS — never raw IDs or internal metadata.
    """
    supabase = get_supabase()

    # Supabase RPC wraps the pgvector query with RLS enforcement
    response = supabase.rpc(
        "match_document_chunks",
        {
            "query_embedding": query_vector,
            "user_id": user_id,
            "match_threshold": similarity_threshold,
            "match_count": top_k,
        },
    ).execute()

    chunks = response.data or []

    # Strip any fields not in allow-list before returning to LLM
    return [{k: v for k, v in chunk.items() if k in CHUNK_ALLOWED_FIELDS} for chunk in chunks]


# ── Tool: metric_lookup ───────────────────────────────────────────────────────


class MetricLookupInput(BaseModel):
    metric_names: list[str] = Field(..., description="e.g. ['revenue', 'EBITDA']")
    user_id: str
    period: str | None = Field(default=None, description="e.g. 'FY2023', 'Q3-2024'")


async def metric_lookup(
    metric_names: list[str],
    user_id: str,
    period: str | None = None,
) -> list[dict[str, Any]]:
    """
    Read-only lookup of pre-approved financial metrics.
    Queries a materialised view — never the raw financial tables.
    Column allow-list enforced before returning.
    """
    supabase = get_supabase()

    query = (
        supabase.table("financial_metrics_view")
        .select("metric_name,value,period,unit,source_doc")
        .eq("user_id", user_id)
        .in_("metric_name", metric_names)
    )

    if period:
        query = query.eq("period", period)

    response = query.limit(50).execute()
    metrics = response.data or []

    return [{k: v for k, v in m.items() if k in METRIC_ALLOWED_FIELDS} for m in metrics]


# ── Tool: schema_context ──────────────────────────────────────────────────────


class SchemaContextInput(BaseModel):
    document_source: str = Field(..., description="source_doc identifier to look up schema for")
    user_id: str


async def schema_context(document_source: str, user_id: str) -> list[dict[str, Any]]:
    """
    Returns structural metadata about a document (field names, data types).
    Used by the agent to understand document schema before querying.
    Never returns row data — only schema descriptions.
    """
    supabase = get_supabase()

    response = (
        supabase.table("document_schema_registry")
        .select("table_name,column_name,description,data_type")
        .eq("user_id", user_id)
        .eq("source_doc", document_source)
        .execute()
    )

    schema = response.data or []
    return [{k: v for k, v in s.items() if k in SCHEMA_ALLOWED_FIELDS} for s in schema]
