import json
import os
import socket
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import routes.services as services_route
from compose_manager import ComposeManager
from inspector.db import InspectorDB
from inspector.models import Capture
from inspector.supervisor import proxy_supervisor


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _port_free(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False


def _llamacpp_service(port: int, name: str = "svc-a", **extra) -> dict:
    cfg = {
        "template_type": "llamacpp",
        "alias": name,
        "port": port,
        "model_path": f"/models/{name}.gguf",
        "api_key": "key-test",
        "params": {},
    }
    cfg.update(extra)
    return cfg


@pytest.fixture(autouse=True)
def set_env_vars(monkeypatch):
    monkeypatch.setenv("DASHBOARD_TOKEN", "test-token")


@pytest.fixture
def env(tmp_path, monkeypatch):
    compose_path = tmp_path / "docker-compose.yml"
    compose_path.write_text("services: {}\n")
    services_path = tmp_path / "services.json"
    db_path = tmp_path / "inspector.db"

    monkeypatch.setattr(services_route, "COMPOSE_FILE", str(compose_path))
    monkeypatch.setenv("LLM_DOCK_TABBY_KEYS_DIR", str(tmp_path / "keys"))
    monkeypatch.setattr(
        ComposeManager, "rebuild_compose_file", lambda self: None
    )
    monkeypatch.setattr(
        services_route, "_recreate_if_running", lambda name: {"restarted": False}
    )

    os.environ["DASHBOARD_TOKEN"] = "test-token"
    from app import create_app

    app = create_app(
        config={
            "TESTING": True,
            "DASHBOARD_TOKEN": "test-token",
            "COMPOSE_FILE": str(compose_path),
            "INSPECTOR_DB_PATH": str(db_path),
        }
    )
    yield {
        "app": app,
        "client": app.test_client(),
        "compose_path": compose_path,
        "services_path": services_path,
        "db_path": db_path,
        "supervisor": proxy_supervisor,
    }
    proxy_supervisor.stop_all()
    proxy_supervisor.configure(compose_path=None, db_path=None)


def _services(env):
    if env["services_path"].exists():
        return json.loads(env["services_path"].read_text())
    return {}


def _write_services(env, services):
    env["services_path"].write_text(json.dumps(services))


def _auth():
    return {"Authorization": "Bearer test-token"}


class TestToggleEndpoint:
    def test_enable_writes_fields_and_starts_proxy(self, env, monkeypatch):
        port = _free_port()
        upstream_port = _free_port()
        monkeypatch.setattr(
            services_route, "allocate_upstream_port",
            lambda services, name: upstream_port,
        )
        _write_services(env, {"svc-a": _llamacpp_service(port)})

        resp = env["client"].post(
            "/api/services/svc-a/inspect", json={"enabled": True}, headers=_auth()
        )

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["service"] == "svc-a"
        assert body["enabled"] is True
        assert body["port"] == port
        assert body["upstream_port"] == upstream_port
        assert body["proxy_running"] is True
        assert body["restarted"] is False
        assert body["error"] is None

        stored = _services(env)["svc-a"]
        assert stored["inspect"] is True
        assert stored["inspect_upstream_port"] == upstream_port

        # The proxy answers on the public port; upstream is down -> 502 JSON.
        import requests

        r = requests.get(f"http://127.0.0.1:{port}/health", timeout=5)
        assert r.status_code == 502
        assert r.json()["error"]["type"] == "upstream_unavailable"

    def test_disable_stops_proxy_and_keeps_upstream_port(self, env):
        port = _free_port()
        _write_services(env, {"svc-a": _llamacpp_service(port)})
        env["client"].post("/api/services/svc-a/inspect", json={"enabled": True}, headers=_auth())

        resp = env["client"].post(
            "/api/services/svc-a/inspect", json={"enabled": False}, headers=_auth()
        )

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["enabled"] is False
        assert body["upstream_port"] == 34000
        assert body["proxy_running"] is False
        assert _port_free(port)

        stored = _services(env)["svc-a"]
        assert stored["inspect"] is False
        assert stored["inspect_upstream_port"] == 34000

    def test_enable_twice_is_noop_not_double_bind(self, env):
        port = _free_port()
        _write_services(env, {"svc-a": _llamacpp_service(port)})
        first = env["client"].post(
            "/api/services/svc-a/inspect", json={"enabled": True}, headers=_auth()
        ).get_json()
        second = env["client"].post(
            "/api/services/svc-a/inspect", json={"enabled": True}, headers=_auth()
        ).get_json()

        assert second["enabled"] is True
        assert second["proxy_running"] is True
        assert second["upstream_port"] == first["upstream_port"] == 34000
        assert len(env["supervisor"].status()) == 1

    def test_disable_when_disabled_returns_200(self, env):
        port = _free_port()
        _write_services(env, {"svc-a": _llamacpp_service(port)})

        resp = env["client"].post(
            "/api/services/svc-a/inspect", json={"enabled": False}, headers=_auth()
        )

        assert resp.status_code == 200
        assert resp.get_json()["enabled"] is False
        assert resp.get_json()["proxy_running"] is False
        assert _port_free(port)

    def test_non_bool_enabled_is_400(self, env):
        _write_services(env, {"svc-a": _llamacpp_service(_free_port())})

        assert (
            env["client"].post(
                "/api/services/svc-a/inspect", json={"enabled": "yes"}, headers=_auth()
            ).status_code
            == 400
        )
        assert (
            env["client"].post(
                "/api/services/svc-a/inspect", json={}, headers=_auth()
            ).status_code
            == 400
        )

    def test_unknown_service_is_404(self, env):
        _write_services(env, {"svc-a": _llamacpp_service(_free_port())})

        resp = env["client"].post(
            "/api/services/missing/inspect", json={"enabled": True}, headers=_auth()
        )

        assert resp.status_code == 404

    def test_bind_failure_reports_error_with_200(self, env):
        port = _free_port()
        blocker = socket.socket()
        blocker.bind(("0.0.0.0", port))
        _write_services(env, {"svc-a": _llamacpp_service(port)})

        resp = env["client"].post(
            "/api/services/svc-a/inspect", json={"enabled": True}, headers=_auth()
        )

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["enabled"] is True
        assert body["proxy_running"] is False
        assert body["error"]
        blocker.close()


class TestWritePathSync:
    def test_rename_moves_captures_and_leaves_one_proxy(self, env, monkeypatch):
        import uuid

        monkeypatch.setattr(services_route, "get_service_container", lambda name: None)
        monkeypatch.setattr("benchmarking.routes.rename_service", lambda old, new: 0)
        monkeypatch.setattr(services_route, "is_service_registered_in_openwebui", lambda *a, **k: False)

        port = _free_port()
        _write_services(env, {"svc-a": _llamacpp_service(port)})
        env["client"].post("/api/services/svc-a/inspect", json={"enabled": True}, headers=_auth())

        db = InspectorDB(str(env["db_path"]))
        db.insert_capture(
            Capture(id=str(uuid.uuid4()), service_name="svc-a", method="POST", path="/v1/chat/completions")
        )

        resp = env["client"].post(
            "/api/services/svc-a/rename", json={"new_name": "svc-b"}, headers=_auth()
        )

        assert resp.status_code == 200
        assert db.list_captures(service="svc-a")[1] == 0
        assert db.list_captures(service="svc-b")[1] == 1

        rows = env["supervisor"].status()
        assert len(rows) == 1
        assert rows[0]["service"] == "svc-b"
        assert rows[0]["running"] is True
        assert rows[0]["listen_port"] == port

    def test_set_public_port_rebinds_both_proxies(self, env, monkeypatch):
        monkeypatch.setattr(services_route, "get_service_container", lambda name: None)

        public_port = _free_port()
        monkeypatch.setattr(services_route, "PUBLIC_SLOT_PORT", public_port)

        # Pin the displaced service's replacement port: the picker scans
        # 3300-3399 against the compose file only, which knows nothing about
        # host listeners (Open WebUI sits on 3300 on this machine).
        displaced_port = _free_port()
        monkeypatch.setattr(ComposeManager, "get_next_available_port", lambda self, **kw: displaced_port)

        other_port = _free_port()
        _write_services(
            env,
            {
                "svc-a": _llamacpp_service(other_port),
                "svc-b": _llamacpp_service(public_port, name="svc-b"),
            },
        )
        env["client"].post("/api/services/svc-a/inspect", json={"enabled": True}, headers=_auth())
        env["client"].post("/api/services/svc-b/inspect", json={"enabled": True}, headers=_auth())

        resp = env["client"].post(
            "/api/services/svc-a/set-public-port", json={}, headers=_auth()
        )

        assert resp.status_code == 200
        stored = _services(env)
        assert stored["svc-a"]["port"] == public_port
        assert stored["svc-b"]["port"] != public_port

        rows = {row["service"]: row for row in env["supervisor"].status()}
        assert rows["svc-a"]["listen_port"] == public_port
        assert rows["svc-a"]["running"] is True
        assert rows["svc-b"]["listen_port"] == stored["svc-b"]["port"]
        assert rows["svc-b"]["running"] is True

    def test_delete_stops_proxy_and_keeps_captures(self, env, monkeypatch):
        import subprocess as _subprocess

        monkeypatch.setattr(services_route.subprocess, "run", lambda *a, **k: _subprocess.CompletedProcess(a, 0, stdout="", stderr=""))

        port = _free_port()
        _write_services(env, {"svc-a": _llamacpp_service(port)})
        env["client"].post("/api/services/svc-a/inspect", json={"enabled": True}, headers=_auth())

        db = InspectorDB(str(env["db_path"]))
        import uuid

        db.insert_capture(
            Capture(id=str(uuid.uuid4()), service_name="svc-a", method="POST", path="/v1/chat/completions")
        )

        resp = env["client"].delete("/api/services/svc-a", headers=_auth())

        assert resp.status_code == 200
        assert env["supervisor"].status() == []
        assert _port_free(port)
        assert db.list_captures(service="svc-a")[1] == 1

    def test_update_put_cannot_set_upstream_port(self, env):
        port = _free_port()
        cfg = _llamacpp_service(port)
        _write_services(env, {"svc-a": cfg})

        resp = env["client"].put(
            "/api/services/svc-a",
            json={**cfg, "inspect_upstream_port": 49999},
            headers=_auth(),
        )

        assert resp.status_code == 200
        assert "inspect_upstream_port" not in _services(env)["svc-a"]

    def test_create_cannot_set_upstream_port(self, env):
        port = _free_port()
        data = {
            "template_type": "llamacpp",
            "alias": "new-svc",
            "port": port,
            "model_path": "/models/new.gguf",
            "params": {},
            "inspect": True,
            "inspect_upstream_port": 49999,
        }

        resp = env["client"].post("/api/services", json=data, headers=_auth())

        assert resp.status_code == 201
        stored = _services(env)[resp.get_json()["service_name"]]
        assert "inspect_upstream_port" not in stored
        assert stored["inspect"] is True

    def test_inspect_non_bool_rejected_by_validation(self, env):
        port = _free_port()
        cfg = _llamacpp_service(port)
        _write_services(env, {"svc-a": cfg})

        resp = env["client"].put(
            "/api/services/svc-a", json={**cfg, "inspect": "yes"}, headers=_auth()
        )

        assert resp.status_code == 400
        assert "inspect" in resp.get_json()["details"][0]
