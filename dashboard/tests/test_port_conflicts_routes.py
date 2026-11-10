import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import routes.services as services_route
from compose_manager import ComposeManager
from inspector.supervisor import proxy_supervisor


def _svc(port, name, **extra):
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


def _auth():
    return {"Authorization": "Bearer test-token"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    compose_path = tmp_path / "docker-compose.yml"
    compose_path.write_text("services: {}\n")
    services_path = tmp_path / "services.json"

    monkeypatch.setenv("DASHBOARD_TOKEN", "test-token")
    monkeypatch.setenv("LLM_DOCK_TABBY_KEYS_DIR", str(tmp_path / "keys"))
    monkeypatch.setattr(services_route, "COMPOSE_FILE", str(compose_path))
    monkeypatch.setattr(ComposeManager, "rebuild_compose_file", lambda self: None)
    monkeypatch.setattr(services_route, "_recreate_if_running", lambda name: {"restarted": False})
    monkeypatch.setattr(proxy_supervisor, "sync", lambda: None)

    from app import create_app

    app = create_app(
        config={
            "TESTING": True,
            "DASHBOARD_TOKEN": "test-token",
            "COMPOSE_FILE": str(compose_path),
            "INSPECTOR_DB_PATH": str(tmp_path / "inspector.db"),
        }
    )

    def write(services):
        services_path.write_text(json.dumps(services))

    def read():
        return json.loads(services_path.read_text())

    yield {"client": app.test_client(), "write": write, "read": read}
    proxy_supervisor.configure(compose_path=None, db_path=None)


def _create_body(port, alias="new-one"):
    return {
        "template_type": "llamacpp",
        "alias": alias,
        "port": port,
        "model_path": "/models/new.gguf",
        "api_key": "key-new",
        "params": {},
    }


class TestWriteRoutes:
    def test_create_with_a_taken_port_is_refused(self, env):
        env["write"]({"svc-a": _svc(3301, "svc-a")})

        resp = env["client"].post("/api/services", json=_create_body(3301), headers=_auth())

        assert resp.status_code == 400
        body = resp.get_json()
        assert body["code"] == "port_in_use"
        assert "svc-a" in body["error"]
        assert set(env["read"]()) == {"svc-a"}

    def test_create_on_another_services_inspector_upstream_port_is_refused(self, env):
        env["write"]({"svc-a": _svc(3301, "svc-a", inspect=True, inspect_upstream_port=34000)})

        resp = env["client"].post("/api/services", json=_create_body(34000), headers=_auth())

        assert resp.status_code == 400
        assert resp.get_json()["code"] == "port_in_use"

    def test_create_on_a_free_port_still_works(self, env):
        env["write"]({"svc-a": _svc(3301, "svc-a")})

        resp = env["client"].post("/api/services", json=_create_body(3310), headers=_auth())

        assert resp.status_code in (200, 201)
        assert len(env["read"]()) == 2

    def test_update_to_a_taken_port_is_refused(self, env):
        env["write"]({"svc-a": _svc(3301, "svc-a"), "svc-b": _svc(3302, "svc-b")})

        resp = env["client"].put("/api/services/svc-b", json=_svc(3301, "svc-b"), headers=_auth())

        assert resp.status_code == 400
        assert resp.get_json()["code"] == "port_in_use"
        assert env["read"]()["svc-b"]["port"] == 3302

    def test_editing_other_fields_of_a_service_in_a_preexisting_duplicate_still_works(self, env):
        env["write"]({"svc-a": _svc(3301, "svc-a"), "svc-b": _svc(3301, "svc-b")})

        resp = env["client"].put(
            "/api/services/svc-b", json={**_svc(3301, "svc-b"), "params": {"-c": "4096"}}, headers=_auth()
        )

        assert resp.status_code == 200
        assert env["read"]()["svc-b"]["params"] == {"-c": "4096"}


class TestStartRoute:
    @pytest.fixture
    def docker(self, monkeypatch):
        calls = []
        statuses = {}
        monkeypatch.setattr(
            services_route, "get_docker_services",
            lambda: [{"name": n, "status": s} for n, s in statuses.items()],
        )
        monkeypatch.setattr(
            services_route, "control_service",
            lambda name, action: calls.append((name, action)) or {"success": True},
        )
        return calls, statuses

    def test_start_is_refused_before_docker_when_a_running_service_holds_the_port(self, env, docker):
        calls, statuses = docker
        env["write"]({"svc-a": _svc(3301, "svc-a"), "svc-b": _svc(3301, "svc-b")})
        statuses.update({"svc-a": "exited", "svc-b": "running"})

        resp = env["client"].post("/api/services/svc-a/start", headers=_auth())

        assert resp.status_code == 400
        body = resp.get_json()
        assert body["code"] == "port_in_use" and "svc-b" in body["error"]
        assert calls == []

    def test_start_is_refused_when_a_stopped_inspected_service_holds_the_port(self, env, docker):
        calls, statuses = docker
        env["write"]({
            "svc-a": _svc(3301, "svc-a"),
            "svc-b": _svc(3301, "svc-b", inspect=True, inspect_upstream_port=34000),
        })
        statuses.update({"svc-a": "exited", "svc-b": "exited"})

        resp = env["client"].post("/api/services/svc-a/start", headers=_auth())

        assert resp.status_code == 400
        assert calls == []

    def test_start_goes_through_when_nothing_holds_the_port(self, env, docker):
        calls, statuses = docker
        env["write"]({"svc-a": _svc(3301, "svc-a"), "svc-b": _svc(3301, "svc-b")})
        statuses.update({"svc-a": "exited", "svc-b": "exited"})

        resp = env["client"].post("/api/services/svc-a/start", headers=_auth())

        assert resp.status_code == 200
        assert calls == [("svc-a", "start")]


class TestSetPublicPort:
    def test_never_leaves_two_services_on_one_port(self, env, monkeypatch):
        monkeypatch.setattr(services_route, "get_service_container", lambda name: None)
        env["write"]({
            "svc-a": _svc(3302, "svc-a"),
            "svc-b": _svc(3301, "svc-b", inspect=True, inspect_upstream_port=3303),
            "svc-c": _svc(3304, "svc-c"),
        })

        resp = env["client"].post("/api/services/svc-a/set-public-port", json={}, headers=_auth())

        assert resp.status_code == 200
        stored = env["read"]()
        assert stored["svc-a"]["port"] == 3301
        claimed = [stored[n]["port"] for n in stored]
        claimed += [stored[n]["inspect_upstream_port"] for n in stored if "inspect_upstream_port" in stored[n]]
        assert len(claimed) == len(set(claimed))

    def test_picker_collision_with_services_json_falls_back_to_a_free_port(self, env, monkeypatch):
        monkeypatch.setattr(services_route, "get_service_container", lambda name: None)
        monkeypatch.setattr(ComposeManager, "get_next_available_port", lambda self, **kw: 3302)
        env["write"]({
            "svc-a": _svc(3302, "svc-a"),
            "svc-b": _svc(3301, "svc-b"),
        })
        monkeypatch.setattr(ComposeManager, "get_used_ports", lambda self: set())

        resp = env["client"].post("/api/services/svc-a/set-public-port", json={}, headers=_auth())

        assert resp.status_code == 200
        stored = env["read"]()
        assert stored["svc-a"]["port"] == 3301
        assert stored["svc-b"]["port"] not in (3301, 3302)


class TestRename:
    def test_rename_neither_introduces_nor_clears_a_port_conflict(self, env, monkeypatch):
        monkeypatch.setattr(services_route, "get_service_container", lambda name: None)
        env["write"]({"llamacpp-a": _svc(3301, "a"), "llamacpp-b": _svc(3302, "b")})

        resp = env["client"].post(
            "/api/services/llamacpp-a/rename", json={"new_name": "llamacpp-z"}, headers=_auth()
        )

        assert resp.status_code == 200
        stored = env["read"]()
        assert {n: c["port"] for n, c in stored.items()} == {"llamacpp-z": 3301, "llamacpp-b": 3302}
