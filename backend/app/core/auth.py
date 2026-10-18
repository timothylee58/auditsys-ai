"""Supabase JWT authentication for FastAPI.

Every authenticated endpoint depends on `get_current_user`, which:
  1. Extracts the Bearer token from the Authorization header.
  2. Verifies it against Supabase Auth (`auth.get_user`) — this checks the
     signature, expiry, audience, AND that the session has not been revoked,
     which local-only verification cannot do.
  3. Returns the caller's identity. `user_id` comes from the verified
     `sub` claim — NEVER from a client-supplied header or query param.

The legacy `X-User-ID` header was removed: it was self-declared and let any
caller impersonate any user (including reading another user's documents,
audit log, and review queue).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger

from app.core.database import get_supabase
from app.core.settings import settings

# auto_error=False so we control the error shape (401 with WWW-Authenticate).
_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    """Identity taken from a verified Supabase access token."""

    user_id: str
    email: str | None = None


def _verify_with_supabase(token: str) -> tuple[str, str | None]:
    """Validate the token against Supabase Auth (blocking call)."""
    client = get_supabase()
    response = client.auth.get_user(token)
    user = response.user
    if user is None or not getattr(user, "id", None):
        raise ValueError("Token valid but no user resolved")
    return str(user.id), getattr(user, "email", None)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthenticatedUser:
    """FastAPI dependency: require and verify a Supabase access token."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        # supabase-py's auth client is synchronous; run it in the default
        # threadpool so the event loop is not blocked by the network call.
        user_id, email = await asyncio.to_thread(_verify_with_supabase, token)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - any failure means "not authenticated"
        logger.debug("auth_rejected reason={}", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return AuthenticatedUser(user_id=user_id, email=email)


async def require_admin(
    user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    """FastAPI dependency: require the caller to be a configured admin.

    Admins are enumerated explicitly via the ADMIN_USER_IDS setting
    (comma-separated Supabase user UUIDs). This protects cost-incurring
    and privileged endpoints (e.g. POST /evals/run, which burns Azure
    OpenAI tokens on every invocation).
    """
    if user.user_id not in settings.admin_user_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return user
