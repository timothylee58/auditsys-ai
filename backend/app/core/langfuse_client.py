"""Langfuse tracer singleton — a graceful no-op when keys aren't configured."""
from __future__ import annotations

from functools import lru_cache

from loguru import logger

from app.core.settings import settings


class _NoOpTracer:
    """Drop-in stand-in used in local dev when Langfuse isn't configured."""

    def __getattr__(self, _name: str):
        def _noop(*_args, **_kwargs):
            return None

        return _noop


@lru_cache
def get_tracer():
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        logger.debug("langfuse_disabled reason=missing_keys")
        return _NoOpTracer()

    from langfuse import Langfuse

    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )
