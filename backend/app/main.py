import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.agents.rag_agent import get_agent_graph
from app.api.routes import audit_log, documents, evals, query, review_queue
from app.core.settings import settings

VERSION = "1.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Build the LangGraph RAG agent once at startup so the first request
    # doesn't pay graph-compilation cost.
    app.state.agent_graph = get_agent_graph()
    logger.info("startup agent_graph_ready=true version={}", VERSION)
    yield
    logger.info("shutdown")


app = FastAPI(title="AuditSys AI API", version=VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-User-ID"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "request method={} path={} status_code={} duration_ms={:.1f}",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "version": VERSION}


app.include_router(documents.router)
app.include_router(audit_log.router)
app.include_router(review_queue.router)
app.include_router(query.router)
app.include_router(evals.router)
