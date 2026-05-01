import json
import os
import sys
from unittest.mock import patch, MagicMock
import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

TEST_TOKEN = "test-token-for-metrics"


@pytest.fixture(autouse=True)
def set_env_vars():
    os.environ["DASHBOARD_TOKEN"] = TEST_TOKEN
    os.environ["COMPOSE_FILE"] = "/dev/null"


def _auth_headers():
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


# Prometheus text format samples — a realistic vLLM metrics dump
SAMPLE_VLLM_METRICS = """# HELP vllm:num_requests_running Number of currently running requests requests.
# TYPE vllm:num_requests_running gauge
vllm:num_requests_running{model_name=qwen3.6-35b-a3b} 3.0
vllm:num_requests_running{model_name=qwen3.6-27b} 1.0
# HELP vllm:num_requests_waiting Number of currently waiting requests requests.
# TYPE vllm:num_requests_waiting gauge
vllm:num_requests_waiting{model_name=qwen3.6-35b-a3b} 2.0
# HELP vllm:num_preemptions_total Number of preemptions requests.
# TYPE vllm:num_preemptions_total counter
vllm:num_preemptions_total{model_name=qwen3.6-35b-a3b} 45.0
# HELP vllm:kv_cache_usage_perc GPU cache usage percentage.
# TYPE vllm:kv_cache_usage_perc gauge
vllm:kv_cache_usage_perc{model_name=qwen3.6-35b-a3b} 0.42
# HELP vllm:prefix_cache_queries_total Number of prefix cache queries.
# TYPE vllm:prefix_cache_queries_total counter
vllm:prefix_cache_queries_total{model_name=qwen3.6-35b-a3b} 150.0
# HELP vllm:prefix_cache_hits_total Number of prefix cache hits.
# TYPE vllm:prefix_cache_hits_total counter
vllm:prefix_cache_hits_total{model_name=qwen3.6-35b-a3b} 120.0
# HELP vllm:prompt_tokens_total Number of prefill tokens processed.
# TYPE vllm:prompt_tokens_total counter
vllm:prompt_tokens_total{model_name=qwen3.6-35b-a3b} 5000.0
# HELP vllm:prompt_tokens_cached_total Number of cached tokens processed.
# TYPE vllm:prompt_tokens_cached_total counter
vllm:prompt_tokens_cached_total{model_name=qwen3.6-35b-a3b} 300.0
# HELP vllm:generation_tokens_total Number of generation tokens processed.
# TYPE vllm:generation_tokens_total counter
vllm:generation_tokens_total{model_name=qwen3.6-35b-a3b} 2500.0
# HELP vllm:spec_decode_num_drafts_total Number of drafts accepted.
# TYPE vllm:spec_decode_num_drafts_total counter
vllm:spec_decode_num_drafts_total{model_name=qwen3.6-35b-a3b} 200.0
# HELP vllm:spec_decode_num_draft_tokens_total Number of draft tokens provided.
# TYPE vllm:spec_decode_num_draft_tokens_total counter
vllm:spec_decode_num_draft_tokens_total{model_name=qwen3.6-35b-a3b} 500.0
# HELP vllm:spec_decode_num_accepted_tokens_total Number of accepted tokens.
# TYPE vllm:spec_decode_num_accepted_tokens_total counter
vllm:spec_decode_num_accepted_tokens_total{model_name=qwen3.6-35b-a3b} 180.0
# HELP vllm:spec_decode_num_accepted_tokens_per_pos Per-position spec-decode acceptance.
# TYPE vllm:spec_decode_num_accepted_tokens_per_pos counter
vllm:spec_decode_num_accepted_tokens_per_pos{pos="0",accepted="1"} 100.0
vllm:spec_decode_num_accepted_tokens_per_pos{pos="1",accepted="1"} 80.0
vllm:spec_decode_num_accepted_tokens_per_pos{pos="2",accepted="1"} 60.0
vllm:spec_decode_num_accepted_tokens_per_pos{pos="3",accepted="1"} 40.0
# HELP vllm:estimated_flops_per_gpu_total Estimated FLOPS.
# TYPE vllm:estimated_flops_per_gpu_total counter
vllm:estimated_flops_per_gpu_total 1.5e13
# HELP vllm:estimated_read_bytes_per_gpu_total Estimated read bytes.
# TYPE vllm:estimated_read_bytes_per_gpu_total counter
vllm:estimated_read_bytes_per_gpu_total 3.2e10
# HELP vllm:estimated_write_bytes_per_gpu_total Estimated write bytes.
# TYPE vllm:estimated_write_bytes_per_gpu_total counter
vllm:estimated_write_bytes_per_gpu_total 1.1e9
"""

SAMPLE_VLLM_FULL = """# HELP vllm:num_requests_running Number of currently running requested requests.
# TYPE vllm:num_requests_running gauge
vllm:num_requests_running{model_name=foo} 5.0
# HELP vllm:total_prompt_tokens Total number of prefill tokens processed.
# TYPE vllm:total_prompt_tokens counter
total_prompt_tokens{model_name=foo} 10000.0
# HELP some_unrelated_metric Some other metric
# TYPE some_unrelated_metric gauge
some_unrelated_metric 42.0
"""

SAMPLE_LLAMACPP_METRICS = """HELP http_requests_total Total HTTP requests made.
TYPE http_requests_total counter
http_requests_total{method="GET",status="200"} 1234.0
"""


@pytest.fixture
def metrics_client(tmp_path):
    """Create a test client using the app factory."""
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
            "model_name": "org/qwen3.6-35b-a3b",
            "api_key": "test-key",
        },
    }
    services_path = tmp_path / "services.json"
    services_path.write_text(json.dumps(services_json))

    from app import create_app

    app = create_app(config={
        "TESTING": True,
        "COMPOSE_FILE": str(compose_path),
        "DASHBOARD_TOKEN": TEST_TOKEN,
    })

    from compose_manager import ComposeManager
    from routes import metrics as routes_mod

    original_cm_init = ComposeManager.__init__

    def mock_init(self, compose_file, services_db_file="services.json"):
        # Use the temp test files
        self.compose_path = tmp_path / "docker-compose.yml"
        self.services_db_path = tmp_path / "services.json"

    ComposeManager.__init__ = mock_init

    client = app.test_client()

    yield client, services_path

    ComposeManager.__init__ = original_cm_init


class TestAuthRequired:
    def test_no_headers(self, metrics_client):
        client, _ = metrics_client
        resp = client.get("/api/services/vllm-test/metrics")
        assert resp.status_code == 401

    def test_wrong_token(self, metrics_client):
        client, _ = metrics_client
        resp = client.get("/api/services/vllm-test/metrics",
            headers={"Authorization": "Bearer wrong-token"})
        assert resp.status_code == 401

    def test_bad_format(self, metrics_client):
        client, _ = metrics_client
        resp = client.get("/api/services/vllm-test/metrics",
            headers={"Authorization": "Basic something"})
        assert resp.status_code == 401


class TestServiceNotFound:
    def test_nonexistent_service(self, metrics_client):
        client, _ = metrics_client
        resp = client.get("/api/services/nonexistent/metrics",
            headers=_auth_headers())
        assert resp.status_code == 404
        assert "not found" in resp.get_json()["error"].lower()


class TestLlamaCpp:
    def test_returns_empty(self, metrics_client):
        client, _ = metrics_client
        resp = client.get("/api/services/llamacpp-test/metrics",
            headers=_auth_headers())
        assert resp.status_code == 200
        assert resp.get_json() == {}


class TestVllmSuccess:
    @patch("routes.metrics.requests.get")
    def test_metrics_parsed(self, mock_get, metrics_client):
        client, _ = metrics_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SAMPLE_VLLM_METRICS
        mock_get.return_value = mock_response

        resp = client.get("/api/services/vllm-test/metrics",
            headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.get_json()

        assert "vllm:num_requests_running" in data
        assert "vllm:num_requests_waiting" in data
        assert "vllm:num_preemptions_total" in data
        assert "vllm:kv_cache_usage_perc" in data
        assert "vllm:prefix_cache_queries_total" in data
        assert "vllm:prompt_tokens_total" in data
        assert "vllm:generation_tokens_total" in data
        assert "vllm:spec_decode_num_drafts_total" in data
        assert "vllm:spec_decode_num_accepted_tokens_total" in data
        assert "vllm:spec_decode_num_accepted_tokens_per_pos" in data
        assert "vllm:estimated_flops_per_gpu_total" in data
        assert "vllm:estimated_read_bytes_per_gpu_total" in data
        assert "vllm:estimated_write_bytes_per_gpu_total" in data

    @patch("routes.metrics.requests.get")
    def test_num_requests_grouped_by_model(self, mock_get, metrics_client):
        client, _ = metrics_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SAMPLE_VLLM_METRICS
        mock_get.return_value = mock_response

        resp = client.get("/api/services/vllm-test/metrics",
            headers=_auth_headers())
        data = resp.get_json()

        running = data["vllm:num_requests_running"]
        assert "qwen3.6-35b-a3b" in running
        assert running["qwen3.6-35b-a3b"] == 3.0
        assert "qwen3.6-27b" in running
        assert running["qwen3.6-27b"] == 1.0

    @patch("routes.metrics.requests.get")
    def test_spec_decode_per_pos_pre_aggregated(self, mock_get, metrics_client):
        client, _ = metrics_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SAMPLE_VLLM_METRICS
        mock_get.return_value = mock_response

        resp = client.get("/api/services/vllm-test/metrics",
            headers=_auth_headers())
        data = resp.get_json()

        per_pos = data["vllm:spec_decode_num_accepted_tokens_per_pos"]
        # Total = 100 + 80 + 60 + 40 = 280
        # 0: 100/280*100 = 35.7
        # 1: 80/280*100 = 28.6
        assert "0" in per_pos
        assert "1" in per_pos
        assert "2" in per_pos
        assert "3" in per_pos
        # Sum should be 100 (percentages)
        total = sum(per_pos.values())
        assert 99.9 <= total <= 100.1

    @patch("routes.metrics.requests.get")
    def test_kv_cache_returns_single_model(self, mock_get, metrics_client):
        client, _ = metrics_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SAMPLE_VLLM_METRICS
        mock_get.return_value = mock_response

        resp = client.get("/api/services/vllm-test/metrics",
            headers=_auth_headers())
        data = resp.get_json()

        kv = data["vllm:kv_cache_usage_perc"]
        assert "qwen3.6-35b-a3b" in kv
        assert kv["qwen3.6-35b-a3b"] == 0.42


class TestVllmErrorHandling:
    @patch("routes.metrics.requests.get")
    def test_connection_error_returns_empty(self, mock_get, metrics_client):
        client, _ = metrics_client

        mock_get.side_effect = requests.ConnectionError("connection refused")

        resp = client.get("/api/services/vllm-test/metrics",
            headers=_auth_headers())
        assert resp.status_code == 200
        assert resp.get_json() == {}

    @patch("routes.metrics.requests.get")
    def test_non200_returns_empty(self, mock_get, metrics_client):
        client, _ = metrics_client

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        resp = client.get("/api/services/vllm-test/metrics",
            headers=_auth_headers())
        assert resp.status_code == 200
        assert resp.get_json() == {}

    @patch("routes.metrics.requests.get")
    def test_timeout_returns_empty(self, mock_get, metrics_client):
        client, _ = metrics_client

        mock_get.side_effect = requests.Timeout("timeout")

        resp = client.get("/api/services/vllm-test/metrics",
            headers=_auth_headers())
        assert resp.status_code == 200

    @patch("routes.metrics.requests.get")
    def test_empty_response(self, mock_get, metrics_client):
        client, _ = metrics_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ""
        mock_get.return_value = mock_response

        resp = client.get("/api/services/vllm-test/metrics",
            headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)


class TestMetricsCurated:
    @patch("routes.metrics.requests.get")
    def test_only_curated_metrics_returned(self, mock_get, metrics_client):
        client, _ = metrics_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SAMPLE_VLLM_FULL
        mock_get.return_value = mock_response

        resp = client.get("/api/services/vllm-test/metrics",
            headers=_auth_headers())
        data = resp.get_json()

        # curated = vllm:num_requests_running
        assert "vllm:num_requests_running" in data
        # not curated
        assert "vllm:total_prompt_tokens" not in data
        assert "some_unrelated_metric" not in data
