"""Supabase async client singleton.

Supports both local development (env vars from .env) and production
(secrets pulled from Azure Key Vault via DefaultAzureCredential).
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from loguru import logger

from app.config import settings

if TYPE_CHECKING:
    from supabase import Client


@lru_cache
def get_supabase() -> "Client":
    """Return a cached Supabase client singleton.

    Raises:
        RuntimeError: If SUPABASE_URL or SUPABASE_SERVICE_KEY are not configured.
    """
    if not settings.supabase_url or not settings.supabase_service_key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set "
            "(via .env or Azure Key Vault)"
        )

    from supabase import create_client

    client = create_client(settings.supabase_url, settings.supabase_service_key)
    logger.info("supabase_client_initialized url={}", settings.supabase_url[:40])
    return client


def reset_supabase() -> None:
    """Clear the cached client (useful for testing)."""
    get_supabase.cache_clear()
