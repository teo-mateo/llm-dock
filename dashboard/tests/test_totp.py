#!/usr/bin/env python3
"""Tests for TOTP authentication endpoints and the @require_auth decorator."""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pyotp

import config
from app import create_app
from auth import verify_totp_code, _totp_sessions


@pytest.fixture(autouse=True)
def clear_totp_sessions():
    _totp_sessions.clear()


@pytest.fixture(autouse=True)
def mock_dotenv_writes(monkeypatch):
    """Prevent tests from writing to the real .env file."""
    monkeypatch.setattr(config, "set_key", lambda *a, **kw: None)


@pytest.fixture
def app_with_token(monkeypatch):
    """Create a test app with mock credentials set at module level."""
    monkeypatch.setenv("DASHBOARD_TOKEN", "test_bearer_token")
    monkeypatch.setattr(config, "DASHBOARD_TOKEN", "test_bearer_token")
    original = config.__dict__.get("DASHBOARD_TOKEN")
    monkeypatch.setattr(config, "TOTP_SECRET", None, raising=False)
    monkeypatch.setattr(config, "TOTP_SECRET", "")  # Start disabled
    yield monkeypatch


class TestTOTPVerification:
    """Test the verify_totp_code function."""

    def test_returns_false_when_no_secret(self, app_with_token):
        config.set_totp_secret("")
        assert verify_totp_code("123456") is False

    def test_returns_true_for_valid_code(self, app_with_token):
        test_secret = pyotp.random_base32()
        config.set_totp_secret(test_secret)

        totp = pyotp.TOTP(test_secret)
        valid_code = totp.now()
        assert verify_totp_code(valid_code) is True

    def test_returns_false_for_invalid_code(self, app_with_token):
        config.set_totp_secret(pyotp.random_base32())
        assert verify_totp_code("000000") is False


class TestTOTPEndpoints:
    """Test TOTP API endpoints."""

    @pytest.fixture
    def client(self, app_with_token):
        app = create_app()
        app.testing = True
        app.config["DASHBOARD_TOKEN"] = "test_bearer_token"
        return app.test_client()

    def _bearer(self, token="test_bearer_token"):
        return {"Authorization": f"Bearer {token}"}

    def test_setup_returns_secret_and_qr(self, client):
        resp = client.post("/api/totp/setup", headers=self._bearer())
        assert resp.status_code == 200
        data = resp.get_json()
        assert "secret" in data
        assert "provisioning_uri" in data
        assert "qr_code" in data
        assert data["provisioning_uri"].startswith("otpauth://totp/")
        assert len(data["qr_code"]) > 0

    def test_setup_requires_auth(self, client):
        resp = client.post("/api/totp/setup")
        assert resp.status_code == 401

    def test_verify_success(self, client):
        # Get a secret
        setup_resp = client.post("/api/totp/setup", headers=self._bearer())
        secret = setup_resp.get_json()["secret"]

        # Verify with correct code
        totp = pyotp.TOTP(secret)
        resp = client.post(
            "/api/totp/verify",
            headers=self._bearer(),
            json={"totp_code": totp.now(), "totp_secret": secret},
        )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "enabled"

    def test_verify_invalid_code(self, client):
        setup_resp = client.post("/api/totp/setup", headers=self._bearer())
        secret = setup_resp.get_json()["secret"]

        resp = client.post(
            "/api/totp/verify",
            headers=self._bearer(),
            json={"totp_code": "000000", "totp_secret": secret},
        )
        assert resp.status_code == 401
        assert "Invalid TOTP code" in resp.get_json()["error"]

    def test_status_disabled_by_default(self, client):
        config.set_totp_secret("")
        resp = client.get("/api/totp/status", headers=self._bearer())
        assert resp.status_code == 200
        assert resp.get_json()["enabled"] is False

    def test_status_enabled_after_setup(self, client):
        # Perform setup and verify
        setup = client.post("/api/totp/setup", headers=self._bearer())
        secret = setup.get_json()["secret"]
        client.post(
            "/api/totp/verify",
            headers=self._bearer(),
            json={"totp_code": pyotp.TOTP(secret).now(), "totp_secret": secret},
        )

        resp = client.get("/api/totp/status", headers=self._bearer())
        assert resp.get_json()["enabled"] is True

    def test_disable_removes_secret(self, client):
        # Enable first
        setup = client.post("/api/totp/setup", headers=self._bearer())
        secret = setup.get_json()["secret"]
        client.post(
            "/api/totp/verify",
            headers=self._bearer(),
            json={"totp_code": pyotp.TOTP(secret).now(), "totp_secret": secret},
        )

        resp = client.post("/api/totp/disable", headers=self._bearer())
        assert resp.status_code == 200
        assert config.TOTP_SECRET == ""

    def test_disable_fails_when_not_configured(self, client):
        config.set_totp_secret("")
        resp = client.post("/api/totp/disable", headers=self._bearer())
        assert resp.status_code == 400


class TestTOTPAuthentication:
    """Test that TOTP codes work for authenticating protected endpoints."""

    @pytest.fixture
    def client(self, app_with_token):
        app = create_app()
        app.testing = True
        app.config["DASHBOARD_TOKEN"] = "test_bearer_token"
        return app.test_client()

    def _bearer(self, token="test_bearer_token"):
        return {"Authorization": f"Bearer {token}"}

    def _totp_header(self, code):
        return {"X-TOTP-Code": code}

    def test_rejects_unauthenticated(self, client):
        resp = client.get("/api/system/info")
        assert resp.status_code == 401

    def test_accepts_valid_bearer_token(self, client):
        resp = client.get("/api/system/info", headers=self._bearer())
        assert resp.status_code == 200

    def test_accepts_valid_totp_code(self, client):
        # Enable TOTP
        test_secret = pyotp.random_base32()
        config.set_totp_secret(test_secret)

        totp = pyotp.TOTP(test_secret)
        resp = client.get("/api/system/info", headers=self._totp_header(totp.now()))
        assert resp.status_code == 200
        assert "X-TOTP-Token" in resp.headers

    def test_rejects_invalid_totp_code(self, client):
        config.set_totp_secret(pyotp.random_base32())
        resp = client.get("/api/system/info", headers=self._totp_header("000000"))
        assert resp.status_code == 401

    def test_short_lived_token_works(self, client):
        # Enable TOTP
        test_secret = pyotp.random_base32()
        config.set_totp_secret(test_secret)

        totp = pyotp.TOTP(test_secret)

        # First request with TOTP code gets a short-lived token
        resp1 = client.get("/api/system/info", headers=self._totp_header(totp.now()))
        short_token = resp1.headers.get("X-TOTP-Token")
        assert short_token is not None

        # Subsequent request with short-lived token works
        resp2 = client.get(
            "/api/system/info", headers={"Authorization": f"Bearer {short_token}"}
        )
        assert resp2.status_code == 200

    def test_bearer_totp_token_has_sliding_expiry(self, client):
        # Enable TOTP
        test_secret = pyotp.random_base32()
        config.set_totp_secret(test_secret)

        totp = pyotp.TOTP(test_secret)

        # Get an initial short-lived token via TOTP code
        resp1 = client.get("/api/system/info", headers=self._totp_header(totp.now()))
        initial_token = resp1.headers.get("X-TOTP-Token")
        assert initial_token is not None

        # Use it as a bearer token — should work (sliding expiry)
        resp2 = client.get(
            "/api/system/info", headers={"Authorization": f"Bearer {initial_token}"}
        )
        assert resp2.status_code == 200

        # Same token should still work for concurrent requests
        resp3 = client.get(
            "/api/system/info", headers={"Authorization": f"Bearer {initial_token}"}
        )
        assert resp3.status_code == 200


class TestTOTPLoginEndpoint:
    """Test the unauthenticated POST /api/auth/login endpoint."""

    @pytest.fixture
    def client(self, app_with_token):
        app = create_app()
        app.testing = True
        app.config["DASHBOARD_TOKEN"] = "test_bearer_token"
        return app.test_client()

    def test_login_rejects_missing_header(self, client):
        resp = client.post("/api/auth/login")
        assert resp.status_code == 400
        assert "Missing X-TOTP-Code header" in resp.get_json()["error"]

    def test_login_rejects_when_totp_not_configured(self, client):
        config.set_totp_secret("")
        resp = client.post("/api/auth/login", headers={"X-TOTP-Code": "123456"})
        assert resp.status_code == 400
        assert "TOTP is not configured" in resp.get_json()["error"]

    def test_login_rejects_invalid_code(self, client):
        config.set_totp_secret(pyotp.random_base32())
        resp = client.post("/api/auth/login", headers={"X-TOTP-Code": "000000"})
        assert resp.status_code == 401
        assert "Invalid TOTP code" in resp.get_json()["error"]

    def test_login_returns_token_on_valid_code(self, client):
        test_secret = pyotp.random_base32()
        config.set_totp_secret(test_secret)

        totp = pyotp.TOTP(test_secret)
        resp = client.post("/api/auth/login", headers={"X-TOTP-Code": totp.now()})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "token" in data
        assert data["token"].startswith("totp-")
        assert data["expires_in"] == 300

    def test_login_token_can_authenticate(self, client):
        test_secret = pyotp.random_base32()
        config.set_totp_secret(test_secret)

        totp = pyotp.TOTP(test_secret)
        login_resp = client.post("/api/auth/login", headers={"X-TOTP-Code": totp.now()})
        short_token = login_resp.get_json()["token"]

        # Use returned token to authenticate a protected endpoint
        resp = client.get(
            "/api/system/info",
            headers={"Authorization": f"Bearer {short_token}"},
        )
        assert resp.status_code == 200