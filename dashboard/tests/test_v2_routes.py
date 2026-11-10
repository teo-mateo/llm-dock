import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import create_app
from page_paths import is_asset_path


def test_dotted_client_route_is_not_an_asset():
    assert is_asset_path("services/llamacpp-glm-5.3-flash-q2kxl/logs") is False


def test_plain_client_route_is_not_an_asset():
    assert is_asset_path("services/llamacpp-glm-5.3/logs") is False


def test_hashed_js_asset_is_an_asset():
    assert is_asset_path("assets/index-B7x9Qk2.js") is True


def test_hashed_css_asset_is_an_asset():
    assert is_asset_path("assets/index-D3f8Lm1.css") is True


@pytest.mark.parametrize(
    "path",
    [
        "assets/photo.avif",
        "assets/clip.webm",
        "assets/clip.mp4",
        "assets/font.otf",
        "assets/font.eot",
        "site.webmanifest",
        "sitemap.xml",
    ],
)
def test_media_and_font_assets_are_assets(path):
    assert is_asset_path(path) is True


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
            "DASHBOARD_TOKEN": "test-token",
        }
    )


@pytest.fixture
def client(app):
    client = app.test_client()
    response = client.post(
        "/api/auth/session", headers={"Authorization": "Bearer test-token"}
    )
    assert response.status_code == 200
    return client


def test_dotted_service_deep_link_serves_spa(client):
    with patch("app.send_from_directory", return_value="spa-index"):
        response = client.get("/v2/services/llamacpp-glm-5.3-flash-q2kxl")
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "spa-index"


def test_dotted_service_logs_deep_link_serves_spa(client):
    with patch("app.send_from_directory", return_value="spa-index"):
        response = client.get("/v2/services/llamacpp-glm-5.3-flash-q2kxl/logs")
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "spa-index"


def test_missing_asset_still_404s(client):
    response = client.get("/v2/assets/index-gone.js")
    assert response.status_code == 404


def test_anonymous_deep_link_serves_login_page(app):
    response = app.test_client().get("/v2/services/llamacpp-glm-5.3-flash-q2kxl")
    assert response.status_code == 200
    assert 'id="password-form"' in response.get_data(as_text=True)


def test_anonymous_asset_is_401(app):
    response = app.test_client().get("/v2/assets/index-gone.js")
    assert response.status_code == 401
