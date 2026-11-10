"""Pins what the default-key rotation does today: the order of its side
effects, the undo when the .env write fails, the partial-failure status and the
body. The seams are faked and append to one log; nothing here may change when
the operation moves out of the route module."""
import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
import routes.services as services_route
from service_ops import wiring
from service_ops.affected import AffectedState
from compose_manager import ComposeManager

TOKEN = "test-token-rotation"

SERVICES = {
    "svc-a": {"template_type": "llamacpp", "port": 3302, "api_key": "old"},
    "svc-b": {"template_type": "llamacpp", "port": 3303, "api_key": "old"},
}


class Seams:
    def __init__(self):
        self.log = []
        self.fail = {}
        self.running = []
        self.registered = []
        self.stop_results = {}

    def step(self, name, *args, result=None):
        self.log.append((name, *args))
        if name in self.fail:
            raise self.fail[name]
        return result


def patch_seams(monkeypatch, seams):
    """The one place that knows where the route reaches its collaborators."""
    def affected():
        return AffectedState(sorted(SERVICES), list(seams.running), list(seams.registered))

    rotate_deps, preview_deps = wiring.rotate_key_deps, wiring.preview_key_rotation_deps
    monkeypatch.setattr(wiring, "rotate_key_deps", lambda compose_file: rotate_deps(compose_file, affected=affected))
    monkeypatch.setattr(
        wiring, "preview_key_rotation_deps", lambda compose_file: preview_deps(compose_file, affected=affected)
    )
    monkeypatch.setattr(
        wiring, "control_service",
        lambda name, action: seams.step("control", name, action, result=seams.stop_results.get(name, {"success": True})),
    )


@pytest.fixture
def seams(tmp_path, monkeypatch):
    seams = Seams()
    monkeypatch.setenv("DASHBOARD_TOKEN", TOKEN)
    monkeypatch.setattr(config, "GLOBAL_API_KEY", "old")
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    monkeypatch.setattr(services_route, "COMPOSE_FILE", str(tmp_path / "docker-compose.yml"))
    patch_seams(monkeypatch, seams)

    def saved(self, services):
        seams.step("save", {name: cfg["api_key"] for name, cfg in services.items()})

    monkeypatch.setattr(ComposeManager, "list_services_in_db", lambda self: copy.deepcopy(SERVICES))
    monkeypatch.setattr(ComposeManager, "save_services_db", saved)
    monkeypatch.setattr(ComposeManager, "rebuild_compose_file", lambda self: seams.step("rebuild"))
    monkeypatch.setattr(config, "set_global_api_key", lambda key, *a, **k: seams.step("env", key))

    from app import create_app

    seams.client = create_app(config={"TESTING": True, "DASHBOARD_TOKEN": TOKEN}).test_client()
    seams.log.clear()
    return seams


def _rotate(seams):
    return seams.client.post("/api/default-api-key/rotate", headers={"Authorization": f"Bearer {TOKEN}"})


def _names(seams):
    return [entry[0] for entry in seams.log]


def test_rotation_commits_services_and_compose_then_env_then_stops_running_containers(seams):
    seams.running = ["svc-b", "svc-a"]
    seams.registered = ["svc-a"]

    response = _rotate(seams)

    body = response.get_json()
    new_key = body["new_api_key"]
    assert response.status_code == 200
    assert new_key and new_key != "old"
    assert body == {
        "success": True, "partial": False, "new_api_key": new_key, "services_updated": 2,
        "total_services": 2, "stopped": ["svc-b", "svc-a"], "stop_errors": {},
        "openwebui_registered": ["svc-a"],
        "message": "Default API key rotated across 2 service(s); 2 running container(s) stopped.",
    }
    assert seams.log == [
        ("save", {"svc-a": new_key, "svc-b": new_key}),
        ("rebuild",),
        ("env", new_key),
        ("control", "svc-b", "stop"),
        ("control", "svc-a", "stop"),
    ]


def test_nothing_running_means_nothing_stopped(seams):
    response = _rotate(seams)

    assert response.status_code == 200
    assert response.get_json()["stopped"] == []
    assert "control" not in _names(seams)


def test_a_failed_stop_is_a_207_partial_that_names_the_containers(seams):
    seams.running = ["svc-a", "svc-b"]
    seams.stop_results = {"svc-a": {"success": False, "error": "busy"}, "svc-b": {"success": False}}

    response = _rotate(seams)

    body = response.get_json()
    assert response.status_code == 207
    assert (body["success"], body["partial"]) == (False, True)
    assert body["stopped"] == []
    assert body["stop_errors"] == {"svc-a": "busy", "svc-b": "unknown error"}
    assert body["message"] == (
        "Default API key rotated across 2 service(s), but 2 running container(s) could NOT be "
        "stopped and still accept the OLD key — stop them manually: svc-a, svc-b."
    )
    assert _names(seams).count("control") == 2


def test_a_service_already_on_the_new_key_is_not_counted_as_updated(seams, monkeypatch):
    monkeypatch.setattr(wiring, "generate_api_key", lambda: "old")

    body = _rotate(seams).get_json()

    assert (body["new_api_key"], body["services_updated"]) == ("old", 0)
    assert seams.log[0] == ("save", {"svc-a": "old", "svc-b": "old"})


def test_a_failing_rebuild_restores_services_and_never_touches_env_or_containers(seams):
    seams.running = ["svc-a"]
    seams.fail["rebuild"] = RuntimeError("compose invalid")

    response = _rotate(seams)

    assert (response.status_code, response.get_json()) == (500, {"success": False, "error": "compose invalid"})
    assert _names(seams) == ["save", "rebuild", "save"]
    assert seams.log[-1] == ("save", {"svc-a": "old", "svc-b": "old"})


def test_a_failing_env_write_undoes_services_and_compose_and_stops_nothing(seams):
    seams.running = ["svc-a"]
    seams.fail["env"] = OSError("read-only")

    response = _rotate(seams)

    assert (response.status_code, response.get_json()) == (500, {"success": False, "error": "read-only"})
    assert _names(seams) == ["save", "rebuild", "env", "save", "rebuild"]
    assert seams.log[3] == ("save", {"svc-a": "old", "svc-b": "old"})


def test_a_raising_stop_is_a_207_that_keeps_the_key_and_still_stops_the_rest(seams):
    seams.running = ["svc-a", "svc-b"]
    seams.fail["control"] = RuntimeError("docker down")

    response = _rotate(seams)

    body = response.get_json()
    assert response.status_code == 207
    assert body["new_api_key"] and (body["success"], body["partial"]) == (False, True)
    assert body["stop_errors"] == {"svc-a": "docker down", "svc-b": "docker down"}
    assert _names(seams) == ["save", "rebuild", "env", "control", "control"]


def test_the_preview_reports_impact_and_changes_nothing(seams):
    seams.running = ["svc-a"]
    seams.registered = ["svc-b"]

    response = seams.client.get("/api/default-api-key/rotation-preview", headers={"Authorization": f"Bearer {TOKEN}"})

    assert (response.status_code, response.get_json()) == (
        200, {"total_services": 2, "running": ["svc-a"], "openwebui_registered": ["svc-b"]},
    )
    assert seams.log == []
