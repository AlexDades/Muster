"""Security tests — JWT auth, rate limits (mocked), security headers."""
from __future__ import annotations
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from fastapi.testclient import TestClient
from jose import jwt

from app.main import app
from app.auth.jwt_auth import create_access_token, require_auth, _ALGORITHM
from app.config import settings
import app.dependencies as deps


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def authed_client():
    app.dependency_overrides[require_auth] = lambda: "test-user"
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── JWT unit tests ───────────────────────────────────────────────────────────

class TestJWT:
    def test_create_token_is_valid_jwt(self):
        token = create_access_token()
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
        assert payload["sub"] == "muster"

    def test_token_has_expiry(self):
        token = create_access_token()
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
        assert "exp" in payload

    def test_expired_token_rejected(self, client):
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        expired = jwt.encode({"exp": past, "sub": "muster"}, settings.jwt_secret, algorithm=_ALGORITHM)
        r = client.get("/documents", headers={"Authorization": f"Bearer {expired}"})
        assert r.status_code == 401

    def test_wrong_secret_rejected(self, client):
        bad = jwt.encode({"sub": "muster"}, "wrong-secret", algorithm=_ALGORITHM)
        r = client.get("/documents", headers={"Authorization": f"Bearer {bad}"})
        assert r.status_code == 401

    def test_malformed_token_rejected(self, client):
        r = client.get("/documents", headers={"Authorization": "Bearer not.a.token"})
        assert r.status_code == 401

    def test_missing_token_rejected(self, client):
        r = client.get("/documents")
        assert r.status_code == 401

    def test_valid_token_accepted(self, client):
        token = create_access_token()
        # /documents will fail with 500 if no store, but auth passes if we get past 401
        r = client.get("/documents", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code != 401


# ── Auth endpoint ────────────────────────────────────────────────────────────

class TestAuthEndpoint:
    def test_valid_api_key_returns_token(self, client):
        with patch.object(settings, "api_key", "test-key"):
            r = client.post("/auth/token", json={"api_key": "test-key"})
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_invalid_api_key_returns_401(self, client):
        with patch.object(settings, "api_key", "test-key"):
            r = client.post("/auth/token", json={"api_key": "wrong-key"})
        assert r.status_code == 401

    def test_empty_api_key_returns_401(self, client):
        with patch.object(settings, "api_key", "test-key"):
            r = client.post("/auth/token", json={"api_key": ""})
        assert r.status_code == 401

    def test_no_api_key_configured_returns_401(self, client):
        with patch.object(settings, "api_key", ""):
            r = client.post("/auth/token", json={"api_key": "anything"})
        assert r.status_code == 401

    def test_returned_token_is_valid(self, client):
        with patch.object(settings, "api_key", "test-key"):
            r = client.post("/auth/token", json={"api_key": "test-key"})
        token = r.json()["access_token"]
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
        assert payload["sub"] == "muster"


# ── Protected endpoint coverage ──────────────────────────────────────────────

class TestProtectedEndpoints:
    PROTECTED = [
        ("GET", "/documents"),
        ("GET", "/drafts"),
        ("GET", "/audit"),
        ("GET", "/settings"),
    ]

    @pytest.mark.parametrize("method,path", PROTECTED)
    def test_unauthenticated_returns_401(self, client, method, path):
        r = client.request(method, path)
        assert r.status_code == 401

    def test_health_is_public(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_auth_token_endpoint_is_public(self, client):
        r = client.post("/auth/token", json={"api_key": "x"})
        assert r.status_code in (200, 401)  # not 404 or 403


# ── Security headers ─────────────────────────────────────────────────────────

class TestSecurityHeaders:
    def test_x_content_type_options(self, client):
        r = client.get("/health")
        assert r.headers.get("x-content-type-options") == "nosniff"

    def test_x_frame_options(self, client):
        r = client.get("/health")
        assert r.headers.get("x-frame-options") == "DENY"

    def test_x_xss_protection(self, client):
        r = client.get("/health")
        assert r.headers.get("x-xss-protection") == "1; mode=block"

    def test_referrer_policy(self, client):
        r = client.get("/health")
        assert r.headers.get("referrer-policy") == "strict-origin-when-cross-origin"

    def test_permissions_policy(self, client):
        r = client.get("/health")
        assert "geolocation=()" in r.headers.get("permissions-policy", "")

    def test_headers_also_on_protected_routes(self, authed_client):
        r = authed_client.get("/settings")
        assert r.headers.get("x-content-type-options") == "nosniff"
