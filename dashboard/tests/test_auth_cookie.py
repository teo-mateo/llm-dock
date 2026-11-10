import os
import sys

import pytest
import pyotp

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from app import create_app
from auth import SESSION_COOKIE_NAME, _totp_sessions

TOKEN = "test-token"


@pytest.fixture
def app(tmp_path):
    compose_path = tmp_path / "docker-compose.yml"
    compose_path.write_text(
        "services:\n"
        "  # <<<<<<< BEGIN DYNAMIC\n"
        "  # >>>>>>> END DYNAMIC\n"
    )
    return create_app(
        config={
            "TESTING": True,
            "COMPOSE_FILE": str(compose_path),
            "BENCHMARK_DB_PATH": str(tmp_path / "benchmarks.db"),
            "DASHBOARD_TOKEN": TOKEN,
        }
    )


@pytest.fixture
def client(app):
    return app.test_client()


def _session(client):
    response = client.post(
        "/api/auth/session", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert response.status_code == 200
    return response.get_json()["token"]


def _cookie_header(response):
    return response.headers.get("Set-Cookie", "")


def test_session_login_sets_cookie(client):
    response = client.post(
        "/api/auth/session", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    header = _cookie_header(response)
    assert f"{SESSION_COOKIE_NAME}=" in header
    assert "HttpOnly" in header
    assert "SameSite=Strict" in header
    assert "Path=/" in header
    assert "Max-Age=28800" in header
    assert "Secure" not in header


def test_totp_login_sets_cookie(client, monkeypatch):
    secret = pyotp.random_base32()
    monkeypatch.setattr(config, "TOTP_SECRET", secret)
    response = client.post(
        "/api/auth/login", headers={"X-TOTP-Code": pyotp.TOTP(secret).now()}
    )
    assert response.status_code == 200
    assert f"{SESSION_COOKIE_NAME}=" in _cookie_header(response)


def test_secure_cookie_on_https(client):
    response = client.post(
        "/api/auth/session",
        headers={"Authorization": f"Bearer {TOKEN}"},
        base_url="https://localhost",
    )
    assert "Secure" in _cookie_header(response)


def test_forwarded_proto_ignored_by_default(client):
    response = client.post(
        "/api/auth/session",
        headers={"Authorization": f"Bearer {TOKEN}", "X-Forwarded-Proto": "https"},
    )
    assert "Secure" not in _cookie_header(response)


def test_forwarded_proto_trusted_when_enabled(client, monkeypatch):
    monkeypatch.setattr(config, "TRUST_PROXY_HEADERS", True)
    response = client.post(
        "/api/auth/session",
        headers={"Authorization": f"Bearer {TOKEN}", "X-Forwarded-Proto": "https"},
    )
    assert "Secure" in _cookie_header(response)


def test_session_bearer_with_cookie_slides(client):
    token = _session(client)
    response = client.get(
        "/api/services", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert f"{SESSION_COOKIE_NAME}=" in _cookie_header(response)


def test_session_bearer_without_cookie_sets_no_cookie(app):
    token = _session(app.test_client())
    fresh = app.test_client()
    response = fresh.get(
        "/api/services", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert "Set-Cookie" not in response.headers


def test_session_bearer_with_foreign_cookie_sets_no_cookie(client):
    first = _session(client)
    second = _session(client)
    client.set_cookie(SESSION_COOKIE_NAME, first)
    response = client.get(
        "/api/services", headers={"Authorization": f"Bearer {second}"}
    )
    assert response.status_code == 200
    assert "Set-Cookie" not in response.headers


def test_static_token_sets_no_cookie(client):
    response = client.get(
        "/api/services", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert response.status_code == 200
    assert "Set-Cookie" not in response.headers


def test_cookie_value_is_session_token(client):
    response = client.post(
        "/api/auth/session", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    token = response.get_json()["token"]
    header = _cookie_header(response)
    assert f"{SESSION_COOKIE_NAME}={token}" in header
    assert TOKEN not in header


def test_logout_with_bearer_clears_and_revokes(client):
    token = _session(client)
    response = client.post(
        "/api/auth/logout", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 204
    header = _cookie_header(response)
    assert f"{SESSION_COOKIE_NAME}=" in header
    assert "Max-Age=0" in header
    assert (
        client.get(
            "/api/services", headers={"Authorization": f"Bearer {token}"}
        ).status_code
        == 401
    )


def test_logout_with_cookie_clears_and_revokes(client):
    token = _session(client)
    response = client.post("/api/auth/logout")
    assert response.status_code == 204
    assert "Max-Age=0" in _cookie_header(response)
    assert token not in _totp_sessions


def test_logout_without_credentials_sets_no_cookie(app):
    token = _session(app.test_client())
    fresh = app.test_client()
    response = fresh.post("/api/auth/logout")
    assert response.status_code == 204
    assert "Set-Cookie" not in response.headers
    assert (
        app.test_client()
        .get("/api/services", headers={"Authorization": f"Bearer {token}"})
        .status_code
        == 200
    )


def test_logout_with_invalid_bearer_sets_no_cookie(client):
    response = client.post(
        "/api/auth/logout", headers={"Authorization": "Bearer wrong"}
    )
    assert response.status_code == 204
    assert "Set-Cookie" not in response.headers
