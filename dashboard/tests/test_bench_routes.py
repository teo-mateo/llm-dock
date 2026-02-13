import json
import os
import sys
import uuid
from unittest.mock import patch, MagicMock
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

TEST_TOKEN = "test-token-for-benchmarks"


@pytest.fixture(autouse=True)
def set_env_vars():
    """Ensure required env vars are set before any imports."""
    os.environ["DASHBOARD_TOKEN"] = TEST_TOKEN
    os.environ["COMPOSE_FILE"] = "/dev/null"


def _auth_headers():
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


@pytest.fixture
def simple_client(tmp_path):
    """Create a test client using the real app with auth header."""
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
            "optional_flags": {
                "gpu_layers": "99",
                "batch_size": "2048",
                "flash_attn": "",
            },
        },
        "vllm-test": {
            "template_type": "vllm",
            "alias": "vllm-test",
            "port": 3302,
            "model_name": "org/model",
            "api_key": "test-key",
        },
    }
    services_path = tmp_path / "services.json"
    services_path.write_text(json.dumps(services_json))

    db_path = str(tmp_path / "test_benchmarks.db")

    # Use the real app but point COMPOSE_FILE at our temp compose
    os.environ["COMPOSE_FILE"] = str(compose_path)

    # Reimport to get fresh app with correct settings
    import importlib
    import app as app_module
    importlib.reload(app_module)

    # Now override the routes module state AFTER reload (reload calls init_benchmarking)
    from benchmarking.db import BenchmarkDB
    from benchmarking.executor import BenchmarkExecutor
    from benchmarking import routes as routes_mod

    test_db = BenchmarkDB(db_path)
    routes_mod._db = test_db
    routes_mod._executor = BenchmarkExecutor(test_db, str(compose_path))
    routes_mod._compose_file = str(compose_path)

    from compose_manager import ComposeManager

    original_get_cm = routes_mod._get_compose_manager

    def mock_get_compose_manager():
        return ComposeManager(str(compose_path), services_db_file=str(services_path))

    routes_mod._get_compose_manager = mock_get_compose_manager

    app_module.app.config["TESTING"] = True
    client = app_module.app.test_client()

    yield client, test_db, services_path

    routes_mod._get_compose_manager = original_get_cm


class TestStartBenchmark:
    @patch("benchmarking.executor.BenchmarkExecutor.start_benchmark")
    def test_start_success(self, mock_start, simple_client):
        client, db, _ = simple_client
        from benchmarking.models import BenchmarkRun
        mock_run = BenchmarkRun(
            id="test-id", service_name="llamacpp-test",
            model_path="/models/test.gguf", status="pending"
        )
        mock_start.return_value = mock_run

        resp = client.post("/api/benchmarks",
            json={"service_name": "llamacpp-test", "params": {"-p": "512", "-n": "128"}},
            headers=_auth_headers())
        assert resp.status_code == 202
        data = resp.get_json()
        assert data["id"] == "test-id"
        assert data["status"] == "pending"

    def test_start_missing_body(self, simple_client):
        client, db, _ = simple_client
        resp = client.post("/api/benchmarks",
            content_type="application/json",
            headers=_auth_headers())
        assert resp.status_code == 400

    def test_start_missing_service_name(self, simple_client):
        client, db, _ = simple_client
        resp = client.post("/api/benchmarks",
            json={"params": {}},
            headers=_auth_headers())
        assert resp.status_code == 400

    def test_start_nonexistent_service(self, simple_client):
        client, db, _ = simple_client
        resp = client.post("/api/benchmarks",
            json={"service_name": "nonexistent-service", "params": {}},
            headers=_auth_headers())
        assert resp.status_code == 404

    def test_start_vllm_service_rejected(self, simple_client):
        client, db, _ = simple_client
        resp = client.post("/api/benchmarks",
            json={"service_name": "vllm-test", "params": {}},
            headers=_auth_headers())
        assert resp.status_code == 400
        assert "llama.cpp" in resp.get_json()["error"]["message"]

    def test_start_invalid_params(self, simple_client):
        client, db, _ = simple_client
        resp = client.post("/api/benchmarks",
            json={"service_name": "llamacpp-test", "params": {"-m": "/evil/path"}},
            headers=_auth_headers())
        assert resp.status_code == 400
        assert "Reserved" in resp.get_json()["error"]["message"]

    @patch("benchmarking.executor.BenchmarkExecutor.is_running_for_service")
    def test_start_concurrent_rejected(self, mock_running, simple_client):
        client, db, _ = simple_client
        mock_running.return_value = True
        resp = client.post("/api/benchmarks",
            json={"service_name": "llamacpp-test", "params": {"-p": "512"}},
            headers=_auth_headers())
        assert resp.status_code == 409

    def test_start_no_auth(self, simple_client):
        client, db, _ = simple_client
        resp = client.post("/api/benchmarks",
            json={"service_name": "llamacpp-test", "params": {}})
        assert resp.status_code == 401


class TestListBenchmarks:
    def test_list_empty(self, simple_client):
        client, db, _ = simple_client
        resp = client.get("/api/benchmarks", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["runs"] == []
        assert data["total"] == 0

    def test_list_with_runs(self, simple_client):
        client, db, _ = simple_client
        from benchmarking.models import BenchmarkRun
        for i in range(3):
            db.create_run(BenchmarkRun(
                id=str(uuid.uuid4()),
                service_name="llamacpp-test",
                model_path="/models/test.gguf",
            ))

        resp = client.get("/api/benchmarks", headers=_auth_headers())
        data = resp.get_json()
        assert data["total"] == 3
        assert len(data["runs"]) == 3

    def test_list_by_service(self, simple_client):
        client, db, _ = simple_client
        from benchmarking.models import BenchmarkRun
        db.create_run(BenchmarkRun(id=str(uuid.uuid4()), service_name="svc-a", model_path="/m"))
        db.create_run(BenchmarkRun(id=str(uuid.uuid4()), service_name="svc-b", model_path="/m"))

        resp = client.get("/api/benchmarks?service_name=svc-a", headers=_auth_headers())
        data = resp.get_json()
        assert data["total"] == 1


class TestGetBenchmark:
    def test_get_existing(self, simple_client):
        client, db, _ = simple_client
        from benchmarking.models import BenchmarkRun
        run_id = str(uuid.uuid4())
        db.create_run(BenchmarkRun(
            id=run_id, service_name="llamacpp-test",
            model_path="/models/test.gguf",
            params_json={"-p": "512"},
        ))

        resp = client.get(f"/api/benchmarks/{run_id}", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == run_id
        assert data["params"] == {"-p": "512"}

    def test_get_nonexistent(self, simple_client):
        client, db, _ = simple_client
        resp = client.get("/api/benchmarks/nonexistent", headers=_auth_headers())
        assert resp.status_code == 404


class TestDeleteBenchmark:
    def test_delete_completed(self, simple_client):
        client, db, _ = simple_client
        from benchmarking.models import BenchmarkRun
        run_id = str(uuid.uuid4())
        db.create_run(BenchmarkRun(
            id=run_id, service_name="llamacpp-test", model_path="/m"
        ))
        db.update_status(run_id, "completed")

        resp = client.delete(f"/api/benchmarks/{run_id}", headers=_auth_headers())
        assert resp.status_code == 200
        assert db.get_run(run_id) is None

    @patch("benchmarking.executor.BenchmarkExecutor.cancel_benchmark")
    def test_delete_running_cancels(self, mock_cancel, simple_client):
        client, db, _ = simple_client
        mock_cancel.return_value = True
        from benchmarking.models import BenchmarkRun
        run_id = str(uuid.uuid4())
        db.create_run(BenchmarkRun(
            id=run_id, service_name="llamacpp-test", model_path="/m"
        ))
        db.update_status(run_id, "running")

        resp = client.delete(f"/api/benchmarks/{run_id}", headers=_auth_headers())
        assert resp.status_code == 200
        assert "cancelled" in resp.get_json()["message"].lower()

    def test_delete_nonexistent(self, simple_client):
        client, db, _ = simple_client
        resp = client.delete("/api/benchmarks/nonexistent", headers=_auth_headers())
        assert resp.status_code == 404


class TestApplyBenchmark:
    def test_apply_completed_run(self, simple_client):
        client, db, services_path = simple_client
        from benchmarking.models import BenchmarkRun
        run_id = str(uuid.uuid4())
        db.create_run(BenchmarkRun(
            id=run_id, service_name="llamacpp-test",
            model_path="/models/test.gguf",
            params_json={"-p": "512", "-n": "128", "-ngl": "80", "-b": "4096", "-fa": ""},
        ))
        db.update_status(run_id, "completed")

        resp = client.put(f"/api/benchmarks/{run_id}/apply", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "-ngl" in data["applied_params"]
        assert "-b" in data["applied_params"]
        assert "-fa" in data["applied_params"]
        assert "-p" in data["skipped_flags"]
        assert "-n" in data["skipped_flags"]

    def test_apply_non_completed_rejected(self, simple_client):
        client, db, _ = simple_client
        from benchmarking.models import BenchmarkRun
        run_id = str(uuid.uuid4())
        db.create_run(BenchmarkRun(
            id=run_id, service_name="llamacpp-test", model_path="/m"
        ))

        resp = client.put(f"/api/benchmarks/{run_id}/apply", headers=_auth_headers())
        assert resp.status_code == 400

    def test_apply_nonexistent(self, simple_client):
        client, db, _ = simple_client
        resp = client.put("/api/benchmarks/nonexistent/apply", headers=_auth_headers())
        assert resp.status_code == 404

    def test_denylist_flags_never_applied(self, simple_client):
        client, db, _ = simple_client
        from benchmarking.models import BenchmarkRun
        run_id = str(uuid.uuid4())
        db.create_run(BenchmarkRun(
            id=run_id, service_name="llamacpp-test",
            model_path="/m",
            params_json={"-p": "512", "-n": "128", "-r": "5", "-ngl": "99"},
        ))
        db.update_status(run_id, "completed")

        resp = client.put(f"/api/benchmarks/{run_id}/apply", headers=_auth_headers())
        data = resp.get_json()
        for flag in ["-p", "-n", "-r"]:
            assert flag in data["skipped_flags"]
            assert flag not in data["applied_params"]


class TestServiceDefaults:
    def test_get_defaults(self, simple_client):
        client, db, _ = simple_client
        resp = client.get("/api/benchmarks/service-defaults/llamacpp-test",
            headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["service_name"] == "llamacpp-test"
        assert data["model_path"] == "/models/test.gguf"
        params = data["params"]
        assert params["-p"] == "512"
        assert params["-n"] == "128"
        assert params["-r"] == "5"
        assert params["-ngl"] == "99"
        assert params["-b"] == "2048"
        assert params["-fa"] == ""

    def test_nonexistent_service(self, simple_client):
        client, db, _ = simple_client
        resp = client.get("/api/benchmarks/service-defaults/nonexistent",
            headers=_auth_headers())
        assert resp.status_code == 404

    def test_vllm_service_rejected(self, simple_client):
        client, db, _ = simple_client
        resp = client.get("/api/benchmarks/service-defaults/vllm-test",
            headers=_auth_headers())
        assert resp.status_code == 400
