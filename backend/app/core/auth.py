"""Supabase JWT verification for FastAPI.

Every protected route derives identity from a Supabase access token sent as
``Authorization: Bearer <access_token>``. This replaces the previous
self-asserted ``X-User-ID`` header, which allowed any caller to impersonate
any user simply by setting a header (audit finding #1).

Verification strategy (first success wins):
  1. Asymmetric keys (RS256/ES256) resolved via the project's JWKS endpoint
     — default for current Supabase projects.
  2. HS256 with the legacy project JWT secret when ``SUPABASE_JWT_SECRET``
     is configured.

Tokens issued for anonymous or service-role contexts are rejected
explicitly, and ``aud`` must be ``authenticated``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import jwt as pyjwt
from fastapi import Depends, HTTPException, Request, status
from jwt import InvalidTokenError, PyJWKClientError
from loguru import logger

from app.core.settings import settings

_AUDIENCE = "authenticated"
_JWKS_CLIENT_TTL_SECONDS = 3600

_jwks_client: pyjwt.PyJWKClient | None = None
_jwks_client_loaded_at: float = 0.0


@dataclass(frozen=True)
class CurrentUser:
    """Identity extracted from a verified Supabase access token."""

    user_id: str
    email: str | None = None
    role: str | None = None


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _get_jwks_client() -> pyjwt.PyJWKClient:
    global _jwks_client, _jwks_client_loaded_at
    now = time.time()
    if _jwks_client is None or now - _jwks_client_loaded_at > _JWKS_CLIENT_TTL_SECONDS:
        jwks_url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        # Bound the JWKS fetch: a hung auth server must not hang request handling.
        _jwks_client = pyjwt.PyJWKClient(jwks_url, cache_keys=True, timeout=5)
        _jwks_client_loaded_at = now
    return _jwks_client


def _decode_with_jwks(token: str) -> dict:
    client = _get_jwks_client()
    signing_key = client.get_signing_key_from_jwt(token)
    return pyjwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256", "ES256"],
        audience=_AUDIENCE,
        options={"require": ["exp", "sub"]},
    )


def _decode_with_hs256(token: str) -> dict:
    secret = settings.supabase_jwt_secret
    if not secret:
        raise InvalidTokenError("no HS256 secret configured")
    return pyjwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        audience=_AUDIENCE,
        issuer=f"{settings.supabase_url.rstrip('/')}/auth/v1",
        options={"require": ["exp", "sub"]},
    )


def verify_token(token: str) -> dict:
    """Verify a Supabase access token and return its claims.

    Tries the JWKS (asymmetric) path first, then falls back to HS256 with
    the configured project secret. Raises InvalidTokenError on failure.
    """
    errors: list[str] = []

    if settings.supabase_url:
        try:
            return _decode_with_jwks(token)
        except (PyJWKClientError, InvalidTokenError) as exc:
            errors.append(f"jwks: {exc}")
        except Exception as exc:  # noqa: BLE001 - network/URL misconfig
            errors.append(f"jwks: {exc}")

    try:
        return _decode_with_hs256(token)
    except InvalidTokenError as exc:
        errors.append(f"hs256: {exc}")

    logger.debug("jwt_verification_failed attempts={}", errors)
    raise InvalidTokenError("; ".join(errors))


def _claims_to_user(claims: dict) -> CurrentUser:
    role = claims.get("role")
    if role in ("anon", "service_role"):
        # anon tokens are unauthenticated; service_role tokens must never be
        # accepted from an inbound request (they would bypass all scoping).
        raise InvalidTokenError(f"role '{role}' is not permitted on inbound requests")
    user_id = claims.get("sub")
    if not user_id:
        raise InvalidTokenError("token is missing the sub claim")
    return CurrentUser(user_id=str(user_id), email=claims.get("email"), role=role)


async def get_current_user(request: Request) -> CurrentUser:
    """FastAPI dependency: require and verify a Supabase bearer token."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise _unauthorized("Missing bearer token")

    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        raise _unauthorized("Missing bearer token")

    try:
        claims = verify_token(token)
    except InvalidTokenError:
        raise _unauthorized("Invalid or expired token") from None

    try:
        return _claims_to_user(claims)
    except InvalidTokenError:
        raise _unauthorized("Invalid token claims") from None


async def require_admin(
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Gate expensive or privileged endpoints behind an explicit admin list.

    Fail-closed: when ADMIN_USER_IDS is unset, nobody passes. This exists so
    endpoints like POST /evals/run (which burns Azure OpenAI spend) cannot be
    triggered by any authenticated account.
    """
    if user.user_id not in settings.admin_user_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return user
