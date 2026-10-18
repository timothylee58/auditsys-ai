"""Auth layer tests: JWT verification, dependency behaviour, admin gate.

Every protected endpoint must reject anonymous callers (401) and derive
identity exclusively from a verified Supabase token — never from a
client-supplied header or query parameter.
"""

from __future__ import annotations

import time

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from app.core.auth import (
    CurrentUser,
    require_admin,
    verify_token,
)
from app.core.settings import settings
from app.main import app

TEST_SECRET = "unit-test-hs256-secret-with-at-least-32-bytes!!"
TEST_URL = "https://test-project.supabase.co"


def _make_token(
    *,
    sub: str = "11111111-1111-1111-1111-111111111111",
    role: str = "authenticated",
    aud: str = "authenticated",
    issuer: str = f"{TEST_URL}/auth/v1",
    expires_in: int = 600,
    extra: dict | None = None,
) -> str:
    now = int(time.time())
    claims = {
        "sub": sub,
        "role": role,
        "aud": aud,
        "iss": issuer,
        "iat": now,
        "exp": now + expires_in,
    }
    if extra:
        claims.update(extra)
    return pyjwt.encode(claims, TEST_SECRET, algorithm="HS256")


@pytest.fixture(autouse=True)
def _jwt_env(monkeypatch):
    """Point verification at a deterministic HS256 secret.

    The JWKS branch is made to fail hermetically (no network in unit tests);
    verify_token must then fall through to the HS256 path — the same
    ordering production uses when a project still issues symmetric tokens.
    """
    from jwt import PyJWKClientError

    def _no_jwks():
        raise PyJWKClientError("unit tests: JWKS disabled")

    monkeypatch.setattr("app.core.auth._get_jwks_client", _no_jwks)
    monkeypatch.setattr(settings, "supabase_url", TEST_URL)
    monkeypatch.setattr(settings, "supabase_jwt_secret", TEST_SECRET)


class TestVerifyToken:
    def test_valid_token_decodes(self):
        claims = verify_token(_make_token(extra={"email": "auditor@example.com"}))
        assert claims["sub"] == "11111111-1111-1111-1111-111111111111"
        assert claims["email"] == "auditor@example.com"

    def test_expired_token_rejected(self):
        with pytest.raises(pyjwt.InvalidTokenError):
            verify_token(_make_token(expires_in=-10))

    def test_wrong_audience_rejected(self):
        with pytest.raises(pyjwt.InvalidTokenError):
            verify_token(_make_token(aud="anonymous"))

    def test_wrong_issuer_rejected(self):
        with pytest.raises(pyjwt.InvalidTokenError):
            verify_token(_make_token(issuer="https://evil.example.com/auth/v1"))

    def test_garbage_token_rejected(self):
        with pytest.raises(pyjwt.InvalidTokenError):
            verify_token("not-a-jwt")


class TestClaimsToUser:
    def test_authenticated_role_accepted(self):
        from app.core.auth import _claims_to_user

        user = _claims_to_user({"sub": "user-1", "role": "authenticated", "email": "a@b.c"})
        assert user.user_id == "user-1"
        assert user.role == "authenticated"

    def test_anon_role_rejected(self):
        from app.core.auth import _claims_to_user

        with pytest.raises(pyjwt.InvalidTokenError):
            _claims_to_user({"sub": "user-1", "role": "anon"})

    def test_service_role_rejected(self):
        from app.core.auth import _claims_to_user

        with pytest.raises(pyjwt.InvalidTokenError):
            _claims_to_user({"sub": "user-1", "role": "service_role"})

    def test_missing_sub_rejected(self):
        from app.core.auth import _claims_to_user

        with pytest.raises(pyjwt.InvalidTokenError):
            _claims_to_user({"role": "authenticated"})


class TestEndpointAuth:
    """All protected endpoints must 401 without a bearer token."""

    def test_documents_requires_auth(self):
        client = TestClient(app, raise_server_exceptions=False)
        assert client.get("/documents").status_code == 401

    def test_documents_upload_requires_auth(self):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/documents/upload",
            files={"file": ("doc.pdf", b"%PDF-1.4 test", "application/pdf")},
        )
        assert response.status_code == 401

    def test_query_requires_auth(self):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/query", json={"question": "What is the policy?"})
        assert response.status_code == 401

    def test_audit_log_requires_auth(self):
        client = TestClient(app, raise_server_exceptions=False)
        assert client.get("/audit-log").status_code == 401

    def test_review_queue_requires_auth(self):
        client = TestClient(app, raise_server_exceptions=False)
        assert client.get("/review-queue").status_code == 401

    def test_evals_run_requires_auth(self):
        client = TestClient(app, raise_server_exceptions=False)
        assert client.post("/evals/run").status_code == 401

    def test_garbage_token_is_401_not_500(self):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/documents", headers={"Authorization": "Bearer garbage"})
        assert response.status_code == 401

    def test_health_remains_public(self):
        client = TestClient(app)
        assert client.get("/health").status_code == 200


class TestAdminGate:
    @pytest.mark.asyncio
    async def test_admin_allowed(self, monkeypatch):
        user = CurrentUser(user_id="admin-1", role="authenticated")
        monkeypatch.setattr(settings, "admin_user_ids_raw", "admin-1,admin-2")
        assert await require_admin(user) == user

    @pytest.mark.asyncio
    async def test_non_admin_forbidden(self, monkeypatch):
        from fastapi import HTTPException

        user = CurrentUser(user_id="regular-1", role="authenticated")
        monkeypatch.setattr(settings, "admin_user_ids_raw", "admin-1,admin-2")
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_fail_closed_when_unset(self, monkeypatch):
        """No ADMIN_USER_IDS configured -> nobody may trigger admin actions."""
        from fastapi import HTTPException

        user = CurrentUser(user_id="anyone", role="authenticated")
        monkeypatch.setattr(settings, "admin_user_ids_raw", "")
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(user)
        assert exc_info.value.status_code == 403
