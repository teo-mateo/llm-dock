import os
import re
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import create_app
from auth import PageAccess, SESSION_COOKIE_NAME, _totp_sessions, page_access

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


def _login(client):
    response = client.post(
        "/api/auth/session", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert response.status_code == 200
    return response.get_json()["token"]


def _is_login_page(response):
    body = response.get_data(as_text=True)
    return (
        response.status_code == 200
        and 'id="password-form"' in body
        and "/static/js/services.js" not in body
        and 'id="create-service-modal"' not in body
    )


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/benchmark",
        "/design-preview",
        "/v2",
        "/v2/chat/abc",
        "/v2/services/llamacpp-glm-5.3-flash-q2kxl",
        "/login",
        "/nope",
    ],
)
def test_anonymous_page_serves_login_page(client, path):
    response = client.get(path)
    assert _is_login_page(response)
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    "path",
    [
        "/static/js/services.js",
        "/static/index.html",
        "/v2/assets/index-abc.js",
        "/v2/assets/index-abc.css",
        "/favicon.ico",
    ],
)
def test_anonymous_asset_is_401(client, path):
    response = client.get(path)
    assert response.status_code == 401
    assert response.headers["Cache-Control"] == "no-store"


def test_valid_cookie_serves_app(client):
    _login(client)
    response = client.get("/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "/static/js/init.js" in body
    assert response.headers["Cache-Control"] == "no-store"


def test_valid_cookie_serves_v2_shell(client, monkeypatch):
    _login(client)
    monkeypatch.setattr("app.send_from_directory", lambda *args, **kwargs: "spa-shell")
    response = client.get("/v2")
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "spa-shell"


def test_expired_cookie_serves_login_page(client):
    _totp_sessions["totp-expired"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    client.set_cookie(SESSION_COOKIE_NAME, "totp-expired")
    response = client.get("/")
    assert _is_login_page(response)
    assert "totp-expired" not in _totp_sessions


def test_unknown_cookie_serves_login_page(client):
    client.set_cookie(SESSION_COOKIE_NAME, "totp-unknown")
    response = client.get("/")
    assert _is_login_page(response)


def test_bearer_only_page_request_serves_login_page(client):
    token = _login(client)
    client.delete_cookie(SESSION_COOKIE_NAME)
    response = client.get("/", headers={"Authorization": f"Bearer {token}"})
    assert _is_login_page(response)


def test_health_stays_public(client):
    assert client.get("/api/health").status_code == 200


def test_cookie_does_not_authenticate_api(client):
    _login(client)
    assert client.get("/api/services").status_code == 401


def test_page_load_slides_cookie(client):
    _login(client)
    response = client.get("/")
    assert SESSION_COOKIE_NAME in response.headers.get("Set-Cookie", "")


def test_page_access_table():
    assert page_access("/api/services", authenticated=False) is PageAccess.ALLOW
    assert page_access("/api", authenticated=False) is PageAccess.ALLOW
    assert page_access("/login", authenticated=False) is PageAccess.ALLOW
    assert page_access("/", authenticated=False) is PageAccess.LOGIN
    assert page_access("/v2/chat/x", authenticated=False) is PageAccess.LOGIN
    assert page_access("/static/js/app.js", authenticated=False) is PageAccess.UNAUTHORIZED
    assert page_access("/v2/assets/index.js", authenticated=False) is PageAccess.UNAUTHORIZED
    assert page_access("/", authenticated=True) is PageAccess.ALLOW
    assert page_access("/v2/assets/index.js", authenticated=True) is PageAccess.ALLOW


def _token_key(text):
    match = re.search(r"TOKEN_KEY\s*=\s*['\"]([^'\"]+)['\"]", text)
    assert match, text
    return match.group(1)


def test_login_page_token_key_matches_frontend():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "static", "login.html"), encoding="utf-8") as f:
        login_html = f.read()
    with open(os.path.join(root, "frontend", "src", "api.js"), encoding="utf-8") as f:
        frontend_api = f.read()
    assert _token_key(login_html) == _token_key(frontend_api) == "dashboard_token"


def test_every_non_api_route_is_guarded(app, client):
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith("/api/") or rule.rule in ("/api", "/login"):
            continue
        if "GET" not in rule.methods:
            continue
        if rule.rule.startswith("/static/"):
            path = "/static/js/services.js"
        elif rule.rule.startswith("/v2/"):
            path = "/v2/chat/x"
        else:
            path = rule.rule
        response = client.get(path)
        assert response.status_code in (200, 401), (rule.rule, response.status_code)
        if response.status_code == 200:
            assert 'id="password-form"' in response.get_data(as_text=True), rule.rule
