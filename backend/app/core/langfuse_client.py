"""Langfuse tracer singleton.

Provides observability tracing for LLM calls. Gracefully degrades to a
no-op stub when Langfuse credentials are not configured (local dev).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Protocol

from loguru import logger

from app.config import settings


class TracerProtocol(Protocol):
    """Minimal interface expected by callers."""

    def trace(self, **kwargs: Any) -> Any: ...
    def generation(self, **kwargs: Any) -> Any: ...
    def flush(self) -> None: ...


class _NoOpTracer:
    """Silent stub used when Langfuse is not configured."""

    def trace(self, **kwargs: Any) -> "_NoOpTracer":
        return self

    def generation(self, **kwargs: Any) -> "_NoOpTracer":
        return self

    def span(self, **kwargs: Any) -> "_NoOpTracer":
        return self

    def end(self, **kwargs: Any) -> None:
        pass

    def flush(self) -> None:
        pass

    def __enter__(self) -> "_NoOpTracer":
        return self

    def __exit__(self, *args: Any) -> None:
        pass


@lru_cache
def get_tracer() -> Any:
    """Return the Langfuse client or a no-op stub.

    Uses LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, and LANGFUSE_HOST
    from configuration. If keys are missing, returns a silent no-op
    tracer so local development works without Langfuse.
    """
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        logger.warning("langfuse_keys_not_set — using no-op tracer (local dev mode)")
        return _NoOpTracer()

    try:
        from langfuse import Langfuse

        client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        logger.info("langfuse_client_initialized host={}", settings.langfuse_host)
        return client
    except Exception as exc:
        logger.error("langfuse_init_failed error={}", str(exc))
        return _NoOpTracer()
