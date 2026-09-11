import os
import sys
from unittest.mock import patch

import pytest
from werkzeug.exceptions import NotFound

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import _is_asset_request, create_app


def test_dotted_client_route_is_not_an_asset():
    assert _is_asset_request("services/llamacpp-glm-5.3-flash-q2kxl/logs") is False


def test_plain_client_route_is_not_an_asset():
    assert _is_asset_request("services/llamacpp-glm-5.3/logs") is False


def test_hashed_js_asset_is_an_asset():
    assert _is_asset_request("assets/index-B7x9Qk2.js") is True


def test_hashed_css_asset_is_an_asset():
    assert _is_asset_request("assets/index-D3f8Lm1.css") is True


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


def test_dotted_service_logs_deep_link_serves_spa(app):
    view = app.view_functions["serve_v2_static"]
    path = "services/llamacpp-glm-5.3-flash-q2kxl/logs"
    with app.test_request_context(f"/v2/{path}"):
        with patch("app.send_from_directory", return_value="spa-index") as send:
            result = view(whatever=path)
    assert result == "spa-index"
    send.assert_called_once_with("frontend/dist", "index.html")


def test_missing_asset_still_404s(app):
    view = app.view_functions["serve_v2_static"]
    with app.test_request_context("/v2/assets/index-gone.js"):
        with pytest.raises(NotFound):
            view(whatever="assets/index-gone.js")
