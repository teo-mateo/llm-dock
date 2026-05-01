import json
import os
import sys

from unittest.mock import patch, MagicMock
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

TEST_TOKEN = "test-token-metrics"

SAMPLE_PROMETHEUS_TEXT = """# HELP vllm:num_requests_running Number of requests currently running on the GPU.
# TYPE vllm:num_requests_running gauge
vllm:num_requests_running 3.0
# HELP vllm:num_requests_waiting Number of requests waiting.
# TYPE vllm:num_requests_waiting gauge
vllm:num_requests_waiting 1.0
# HELP vllm:kv_cache_usage_perc KV cache usage percentage.
# TYPE vllm:kv_cache_usage_perc gauge
vllm:kv_cache_usage_perc 0.73
# HELP vllm:prefix_cache_queries_total Total prefix cache queries.
# TYPE vllm:prefix_cache_queries_total counter
vllm:prefix_cache_queries_total 1000.0
# HELP vllm:prefix_cache_hits_total Total prefix cache hits.
# TYPE vllm:prefix_cache_hits_total counter
vllm:prefix_cache_hits_total 800.0
# HELP vllm:prompt_tokens_total Total prompt tokens processed.
# TYPE vllm:prompt_tokens_total counter
vllm:prompt_tokens_total 50000.0
# HELP vllm:generation_tokens_total Total generation tokens produced.
# TYPE vllm:generation_tokens_total counter
vllm:generation_tokens_total 120000.0
# HELP vllm:spec_decode_num_accepted_tokens_total Total accepted speculative tokens.
# TYPE vllm:spec_decode_num_accepted_tokens_total counter
vllm:spec_decode_num_accepted_tokens_total 5000.0
# HELP vllm:spec_decode_num_drafts_total Total draft tokens.
# TYPE vllm:spec_decode_num_drafts_total counter
vllm:spec_decode_num_drafts_total 10000.0
# HELP vllm:spec_decode_num_accepted_tokens_per_pos_total Accepted tokens per position.
# TYPE vllm:spec_decode_num_accepted_tokens_per_pos_total counter
vllm:spec_decode_num_accepted_tokens_per_pos_total{position="0"} 1000.0
vllm:spec_decode_num_accepted_tokens_per_pos_total{position="1"} 600.0
vllm:spec_decode_num_accepted_tokens_per_pos_total{position="2"} 200.0
# HELP vllm:uninteresting_metric A metric not in our whitelist.
# TYPE vllm:uninteresting_metric gauge
vllm:uninteresting_metric 999.0
# HELP some:other_namespace From a different namespace entirely.
# TYPE some:other_namespace gauge
some:other_namespace 42.0
"""


@pytest.fixture
def metrics_client(tmp_path):
    """Create a test client with compose + services.json for metrics testing."""
    compose_content = """services:
  # <<<<<<< BEGIN DYNAMIC
  # >>>>>>> END DYNAMIC

networks:
  llm-network:
    driver: bridge
"""
    compose_path = tmp_path / "docker-compose.yml"
    compose_path.write_text(compose_content)

    services_json = {
        "llamacpp-test": {
            "template_type": "llamacpp",
            "alias": "test",
            "port": 3301,
            "model_path": "/models/test.gguf",
            "api_key": "test-key",
            "params": {"-ngl": "99"},
        },
        "vllm-test": {
            "template_type": "vllm",
            "alias": "vllm-test",
            "port": 3302,
            "model_name": "org/model",
            "api_key": "test-key",
            "params": {},
        },
    }
    services_path = tmp_path / "services.json"
    services_path.write_text(json.dumps(services_json))

    # Ensure env vars are set before imports
    os.environ["DASHBOARD_TOKEN"] = TEST_TOKEN

    from app import create_app

    app = create_app(config={
        "TESTING": True,
        "COMPOSE_FILE": str(compose_path),
        "DASHBOARD_TOKEN": TEST_TOKEN,
    })

    from routes import metrics as metrics_mod
    from compose_manager import ComposeManager

    _orig_get_service_config = metrics_mod._get_service_config

    def _mock_get_service_config(name):
        mgr = ComposeManager(str(compose_path), services_db_file=str(services_path))
        return mgr.get_service_from_db(name)

    metrics_mod._get_service_config = _mock_get_service_config
    client = app.test_client()

    yield client

    metrics_mod._get_service_config = _orig_get_service_config


def _auth_headers():
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


class TestVLLMMetrics:
    @patch("routes.metrics.requests.get")
    def test_happy_path_returns_metrics(self, mock_get, metrics_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_PROMETHEUS_TEXT
        mock_get.return_value = mock_resp

        resp = metrics_client.get(
            "/api/services/vllm-test/metrics", headers=_auth_headers()
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert "scraped_at" in data
        metrics = data["metrics"]
        assert "vllm:num_requests_running" in metrics
        assert "vllm:kv_cache_usage_perc" in metrics
        assert "vllm:generation_tokens_total" in metrics

    @patch("routes.metrics.requests.get")
    def test_whitelist_filters_extra_metrics(self, mock_get, metrics_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_PROMETHEUS_TEXT
        mock_get.return_value = mock_resp

        resp = metrics_client.get(
            "/api/services/vllm-test/metrics", headers=_auth_headers()
        )

        data = resp.get_json()
        metrics = data["metrics"]
        assert "vllm:uninteresting_metric" not in metrics
        assert "some:other_namespace" not in metrics

    @patch("routes.metrics.requests.get")
    def test_spec_decode_position_flattened(self, mock_get, metrics_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_PROMETHEUS_TEXT
        mock_get.return_value = mock_resp

        resp = metrics_client.get(
            "/api/services/vllm-test/metrics", headers=_auth_headers()
        )

        data = resp.get_json()
        pos_metric = data["metrics"]["vllm:spec_decode_num_accepted_tokens_per_pos_total"]
        assert pos_metric["position_0"] == 1000.0
        assert pos_metric["position_1"] == 600.0
        assert pos_metric["position_2"] == 200.0

    def test_scraped_at_timestamp_present(self, metrics_client):
        with patch("routes.metrics.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = SAMPLE_PROMETHEUS_TEXT
            mock_get.return_value = mock_resp

            resp = metrics_client.get(
                "/api/services/vllm-test/metrics", headers=_auth_headers()
            )

            data = resp.get_json()
            assert "T" in data["scraped_at"]


class TestNonVLLMService:
    def test_llamacpp_returns_empty_metrics(self, metrics_client):
        resp = metrics_client.get(
            "/api/services/llamacpp-test/metrics", headers=_auth_headers()
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["metrics"] == {}
        assert "scraped_at" in data


class TestErrorStates:
    def test_nonexistent_service_returns_404(self, metrics_client):
        resp = metrics_client.get(
            "/api/services/nonexistent/metrics", headers=_auth_headers()
        )

        assert resp.status_code == 404

    def test_connection_error_returns_empty(self, metrics_client):
        import requests as requests_lib
        with patch("routes.metrics.requests.get", side_effect=requests_lib.ConnectionError):
            resp = metrics_client.get(
                "/api/services/vllm-test/metrics", headers=_auth_headers()
            )

            assert resp.status_code == 200
            data = resp.get_json()
            assert data["metrics"] == {}

    def test_timeout_returns_empty(self, metrics_client):
        import requests as requests_lib
        with patch("routes.metrics.requests.get", side_effect=requests_lib.Timeout):
            resp = metrics_client.get(
                "/api/services/vllm-test/metrics", headers=_auth_headers()
            )

            assert resp.status_code == 200
            data = resp.get_json()
            assert data["metrics"] == {}


class TestAuth:
    def test_no_auth_returns_401(self, metrics_client):
        resp = metrics_client.get("/api/services/vllm-test/metrics")
        assert resp.status_code == 401
