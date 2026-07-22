"""AuditSys AI — FastAPI application entry point.

Provides:
- Lifespan context manager for startup/shutdown
- CORS middleware (Vercel frontend origin)
- Request logging middleware
- /health endpoint
- Mounts all API routers
- Initializes LangGraph agent at startup
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.config import settings

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

_agent_graph: Any = None


def get_agent_graph() -> Any:
    """Return the compiled LangGraph agent (initialized at startup)."""
    return _agent_graph


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — initialize resources on startup, cleanup on shutdown."""
    global _agent_graph

    logger.info("startup_begin version=1.0.0")

    # Initialize LangGraph agent
    try:
        from app.agents.rag_agent import build_graph

        _agent_graph = build_graph()
        logger.info("langgraph_agent_initialized")
    except Exception as exc:
        logger.error("langgraph_agent_init_failed error={}", str(exc))

    # Verify Redis connectivity (non-blocking)
    try:
        from app.core.redis_client import get_redis

        redis = get_redis()
        await redis.ping()
        logger.info("redis_connected")
    except Exception as exc:
        logger.warning("redis_connection_failed error={}", str(exc))

    # Initialize Langfuse tracer
    try:
        from app.core.langfuse_client import get_tracer

        get_tracer()
    except Exception as exc:
        logger.warning("langfuse_init_skipped error={}", str(exc))

    logger.info("startup_complete")
    yield

    # Shutdown
    logger.info("shutdown_begin")
    try:
        from app.core.langfuse_client import get_tracer

        tracer = get_tracer()
        tracer.flush()
    except Exception:
        pass
    logger.info("shutdown_complete")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AuditSys AI",
    description="Governed document intelligence and financial Q&A system",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next: Any) -> Response:
    """Log every request with timing, method, path, and status."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    start_time = time.perf_counter()

    # Attach request_id to state for downstream use
    request.state.request_id = request_id

    response: Response = await call_next(request)

    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    logger.info(
        "request method={} path={} status={} duration_ms={} request_id={}",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        request_id,
    )

    response.headers["X-Request-ID"] = request_id
    return response


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Health check endpoint for load balancers and container orchestrators.

    Returns:
        200 OK with status and version.
    """
    return {"status": "ok", "version": "1.0.0"}


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Any) -> JSONResponse:
    """RFC 7807 Problem Detail for 404."""
    return JSONResponse(
        status_code=404,
        content={
            "type": "https://auditsys.ai/errors/not-found",
            "title": "Not Found",
            "status": 404,
            "detail": f"Resource not found: {request.url.path}",
        },
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: Any) -> JSONResponse:
    """RFC 7807 Problem Detail for 500."""
    logger.exception("unhandled_error path={}", request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "type": "https://auditsys.ai/errors/internal-error",
            "title": "Internal Server Error",
            "status": 500,
            "detail": "An unexpected error occurred. Please try again later.",
        },
    )


# ---------------------------------------------------------------------------
# Router registration
# ---------------------------------------------------------------------------

from app.api.routes import documents, query, audit, review, evals  # noqa: E402

app.include_router(documents.router)
app.include_router(query.router)
app.include_router(audit.router)
app.include_router(review.router)
app.include_router(evals.router)
