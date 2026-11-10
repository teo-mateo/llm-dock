"""Pins what PUT /api/services/<name> does today: status codes, bodies, the
merge, and the order of its side effects on every branch of the image-change
path. The fakes sit below the recreate helper so that order is real; nothing
here may change when the operation moves out of the route module."""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import docker_utils
import routes.services as services_route
import service_recreate
from compose_manager import ComposeManager
from inspector.supervisor import proxy_supervisor
from services import event_manager

TOKEN = "test-token-update"
NAME = "llamacpp-a"


def _svc(port=3302, **extra):
    config = {
        "template_type": "llamacpp", "alias": "a", "port": port, "api_key": "k",
        "model_path": "/m.gguf", "params": {},
    }
    config.update(extra)
    return config


class Container:
    def __init__(self, status, image="llm-dock-llamacpp"):
        self.status = status
        self.attrs = {"Config": {"Image": image}}


class Seams:
    def __init__(self):
        self.log = []
        self.fail = {}
        self.container = None
        self.docker_rc = 0
        self.image_exists = True

    def step(self, name, *args, result=None):
        self.log.append((name, *args))
        if name in self.fail:
            raise self.fail[name]
        return result

    def names(self):
        return [entry[0] for entry in self.log]


def patch_container_lookup(monkeypatch, seams):
    """The one place that knows where the update reads the container from."""
    monkeypatch.setattr(services_route, "get_service_container", lambda name: seams.container)


@pytest.fixture
def seams(tmp_path, monkeypatch):
    seams = Seams()
    monkeypatch.setenv("DASHBOARD_TOKEN", TOKEN)
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services: {}\n")
    seams.services_path = tmp_path / "services.json"
    seams.services_path.write_text(json.dumps({
        NAME: _svc(favorite=True, inspect_upstream_port=34005),
        "llamacpp-b": _svc(3303),
    }))
    monkeypatch.setattr(services_route, "COMPOSE_FILE", str(compose))
    patch_container_lookup(monkeypatch, seams)

    real_update = ComposeManager.update_service_in_db

    def update(self, name, config):
        seams.step("db_update", name)
        return real_update(self, name, config)

    monkeypatch.setattr(ComposeManager, "update_service_in_db", update)
    monkeypatch.setattr(ComposeManager, "rebuild_compose_file", lambda self: seams.step("rebuild"))
    monkeypatch.setattr(ComposeManager, "get_used_ports", lambda self: set())
    monkeypatch.setattr(proxy_supervisor, "sync", lambda: seams.step("sync"))
    monkeypatch.setattr(event_manager, "emit", lambda event: seams.step("emit", event))
    monkeypatch.setattr(docker_utils, "get_image_info", lambda n: {"exists": seams.image_exists})

    def fake_run(command, *args, **kwargs):
        assert "--force-recreate" in command, command
        seams.step("recreate", command[-1], kwargs.get("timeout"))
        return subprocess.CompletedProcess(command, seams.docker_rc, "", "compose said no")

    monkeypatch.setattr(subprocess, "run", fake_run)

    from app import create_app

    seams.client = create_app(config={"TESTING": True, "DASHBOARD_TOKEN": TOKEN}).test_client()
    seams.log.clear()
    return seams


def _put(seams, body, name=NAME):
    return seams.client.put(f"/api/services/{name}", json=body, headers={"Authorization": f"Bearer {TOKEN}"})


def _stored(seams, name=NAME):
    return json.loads(seams.services_path.read_text())[name]


def _event(seams):
    (event,) = [entry[1] for entry in seams.log if entry[0] == "emit"]
    return event


def test_an_empty_body_is_a_400_even_for_an_unknown_service(seams):
    response = _put(seams, {}, name="ghost")

    assert (response.status_code, response.get_json()) == (400, {"error": "Request body is required"})
    assert seams.log == []


def test_an_unknown_service_is_a_404(seams):
    response = _put(seams, _svc(), name="ghost")

    assert (response.status_code, response.get_json()) == (404, {"error": 'Service "ghost" not found'})
    assert seams.log == []


def test_changing_the_template_type_is_refused(seams):
    response = _put(seams, _svc(template_type="vllm"))

    assert (response.status_code, response.get_json()) == (
        400, {"error": "Cannot change template_type of existing service"},
    )
    assert seams.log == []


def test_an_invalid_config_is_a_400_with_details(seams):
    response = _put(seams, _svc(reasoning_levels="Not Valid!"))

    body = response.get_json()
    assert response.status_code == 400
    assert body["error"] == "Validation failed" and body["details"]
    assert seams.log == []


def test_a_port_another_service_holds_is_a_400_with_the_conflict_code(seams):
    response = _put(seams, _svc(3303))

    body = response.get_json()
    assert response.status_code == 400
    assert body["code"] == "port_in_use"
    assert seams.log == []


def test_keeping_its_own_port_is_not_a_conflict(seams):
    assert _put(seams, _svc(3302)).status_code == 200


def test_an_unchanged_image_writes_rebuilds_syncs_then_emits(seams):
    response = _put(seams, _svc(reasoning_levels="off,low"))

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True, "service_name": NAME, "message": f'Service "{NAME}" updated successfully',
        "configured_image": "llm-dock-llamacpp", "restarted": False,
    }
    assert seams.names() == ["db_update", "rebuild", "sync", "emit"]
    event = _event(seams)
    assert {k: v for k, v in event.items() if k != "timestamp"} == {
        "service_name": NAME, "action": "metadata-changed", "status": None, "container_id": None,
        "metadata": {"reasoning_levels": [{"id": "off", "effort": "off"}, {"id": "low", "effort": "low"}]},
    }
    assert isinstance(event["timestamp"], float)


def test_the_merge_keeps_unsent_fields_and_the_body_cannot_set_the_upstream_port(seams):
    _put(seams, {"port": 3302, "alias": "a", "api_key": "k2", "model_path": "/m.gguf", "inspect_upstream_port": 1})

    stored = _stored(seams)
    assert stored["favorite"] is True
    assert stored["inspect_upstream_port"] == 34005
    assert stored["api_key"] == "k2"
    assert stored["template_type"] == "llamacpp"


def test_unknown_flags_warn_over_the_merged_params(seams):
    services = json.loads(seams.services_path.read_text())
    services[NAME]["params"] = {"--definitely-not-a-flag": "1"}
    seams.services_path.write_text(json.dumps(services))

    response = _put(seams, {"port": 3302, "alias": "a", "api_key": "k", "model_path": "/m.gguf"})

    assert response.status_code == 200
    assert any("--definitely-not-a-flag" in w for w in response.get_json()["warnings"])


def test_a_changed_image_on_a_stopped_service_rebuilds_then_syncs_without_recreating(seams):
    response = _put(seams, _svc(image="custom:1"))

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True, "service_name": NAME, "message": f'Service "{NAME}" updated successfully',
        "configured_image": "custom:1", "restarted": False,
    }
    assert seams.names() == ["db_update", "rebuild", "sync", "emit"]
    assert _event(seams)["metadata"]["image"] == "custom:1"


def test_a_changed_image_on_a_running_service_rebuilds_recreates_then_syncs(seams):
    seams.container = Container("running")

    response = _put(seams, _svc(image="custom:1"))

    body = response.get_json()
    assert (response.status_code, body["restarted"], body["configured_image"]) == (200, True, "custom:1")
    assert "recreate_error" not in body
    assert seams.log[:4] == [
        ("db_update", NAME), ("rebuild",), ("recreate", NAME, service_recreate.IMAGE_CHANGE_TIMEOUT_S), ("sync",),
    ]
    assert seams.names()[4:] == ["emit"]
    assert _event(seams)["metadata"]["image"] == "custom:1"


def test_a_failed_recreate_still_syncs_and_is_a_200_with_the_error(seams):
    seams.container = Container("running")
    seams.docker_rc = 1

    response = _put(seams, _svc(image="custom:1"))

    body = response.get_json()
    assert (response.status_code, body["restarted"], body["recreate_error"]) == (200, False, "compose said no")
    assert seams.names() == ["db_update", "rebuild", "recreate", "sync", "emit"]
    assert _event(seams)["metadata"]["image"] == "llm-dock-llamacpp"


def test_a_recreate_that_times_out_still_syncs_and_is_a_200_with_the_error(seams):
    seams.container = Container("running")
    seams.fail["recreate"] = subprocess.TimeoutExpired("docker", 600)

    response = _put(seams, _svc(image="custom:1"))

    body = response.get_json()
    assert (response.status_code, body["restarted"]) == (200, False)
    assert "timed out" in body["recreate_error"]
    assert seams.names() == ["db_update", "rebuild", "recreate", "sync", "emit"]


def test_a_running_service_blocked_from_starting_is_neither_rebuilt_nor_synced(seams, monkeypatch):
    seams.container = Container("running")
    monkeypatch.setattr(service_recreate, "check_start", lambda services, name, statuses: {"error": "port taken"})

    response = _put(seams, _svc(image="custom:1"))

    body = response.get_json()
    assert (response.status_code, body["restarted"], body["recreate_error"]) == (200, False, "port taken")
    assert seams.names() == ["db_update", "emit"]
    assert _stored(seams)["image"] == "custom:1"


def test_a_failing_rebuild_on_the_image_path_still_syncs_then_is_a_500(seams):
    seams.fail["rebuild"] = RuntimeError("compose invalid")

    response = _put(seams, _svc(image="custom:1"))

    assert (response.status_code, response.get_json()) == (500, {"error": "compose invalid"})
    assert seams.names() == ["db_update", "rebuild", "sync"]


def test_a_failing_rebuild_with_the_image_unchanged_is_a_500_without_a_sync(seams):
    seams.fail["rebuild"] = RuntimeError("compose invalid")

    response = _put(seams, _svc())

    assert (response.status_code, response.get_json()) == (500, {"error": "compose invalid"})
    assert seams.names() == ["db_update", "rebuild"]


@pytest.mark.parametrize("image", [None, "custom:1"])
def test_a_failing_sync_is_a_500_and_nothing_is_emitted(seams, image):
    seams.fail["sync"] = RuntimeError("no port")

    response = _put(seams, _svc(**({"image": image} if image else {})))

    assert (response.status_code, response.get_json()) == (500, {"error": "no port"})
    assert seams.names()[-1] == "sync"


def test_a_missing_image_warns_only_when_the_image_changed(seams):
    seams.image_exists = False

    unchanged = _put(seams, _svc()).get_json()
    changed = _put(seams, _svc(image="custom:1")).get_json()

    assert "warnings" not in unchanged
    assert changed["warnings"] == [
        "Image 'custom:1' is not present locally; it will be pulled when the container starts"
    ]
