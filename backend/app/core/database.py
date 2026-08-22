from functools import lru_cache
from typing import Any

from supabase import Client, create_client

from app.core.settings import settings


@lru_cache
def get_supabase() -> Client:
    if not settings.supabase_url or not settings.supabase_service_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(settings.supabase_url, settings.supabase_service_key)


_async_client: Any = None


async def get_async_supabase() -> Any:
    """Return a cached async Supabase client (created on first call).

    Uses supabase-py v2.10+ async client via `acreate_client`.
    """
    global _async_client
    if _async_client is None:
        if not settings.supabase_url or not settings.supabase_service_key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
        from supabase._async.client import create_client as _create_async_client

        _async_client = await _create_async_client(
            settings.supabase_url, settings.supabase_service_key
        )
    return _async_client
