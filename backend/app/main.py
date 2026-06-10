from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import audit_log, documents, health, query, review_queue
from app.core.settings import settings

app = FastAPI(title="AuditSys AI API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(health.router)
app.include_router(documents.router)
app.include_router(audit_log.router)
app.include_router(review_queue.router)
app.include_router(query.router)
