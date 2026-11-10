"""Pins what the inspect toggle does today: status codes, bodies, the order of
its side effects in each direction and which failures are fatal. The seams are
faked and append to one log; nothing here may change when the operation moves
out of the route module."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import routes.services as services_route
from compose_manager import ComposeManager
from inspector.supervisor import proxy_supervisor
from service_ops import wiring
from services import event_manager

TOKEN = "test-token-inspect"


def _svc(port, **extra):
    config = {
        "template_type": "llamacpp", "alias": "a", "port": port, "api_key": "k",
        "model_path": "/m.gguf", "params": {},
    }
    config.update(extra)
    return config


class Seams:
    def __init__(self):
        self.log = []
        self.fail = {}
        self.restarted = False
        self.status = []

    def step(self, name, *args, result=None):
        self.log.append((name, *args))
        if name in self.fail:
            raise self.fail[name]
        return result


@pytest.fixture
def seams(tmp_path, monkeypatch):
    seams = Seams()
    monkeypatch.setenv("DASHBOARD_TOKEN", TOKEN)
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services: {}\n")
    (tmp_path / "services.json").write_text(json.dumps({
        "svc-a": _svc(3302),
        "svc-on": _svc(3303, inspect=True, inspect_upstream_port=34007),
        "svc-kept": _svc(3304, inspect=False, inspect_upstream_port=34003),
        "open-webui": _svc(3300),
    }))
    monkeypatch.setattr(services_route, "COMPOSE_FILE", str(compose))
    monkeypatch.setattr(
        ComposeManager, "update_service_in_db",
        lambda self, name, config: seams.step(
            "db_update", name, config.get("inspect"), config.get("inspect_upstream_port")
        ),
    )
    monkeypatch.setattr(ComposeManager, "rebuild_compose_file", lambda self: seams.step("rebuild"))

    def recreate(compose_file, name, *args, **kwargs):
        seams.step("recreate", name)
        return {"restarted": seams.restarted}

    monkeypatch.setattr(wiring, "recreate_if_running", recreate)
    monkeypatch.setattr(proxy_supervisor, "sync", lambda: seams.step("proxy_sync"))
    monkeypatch.setattr(proxy_supervisor, "status", lambda: seams.status)
    monkeypatch.setattr(event_manager, "emit", lambda event: seams.step("emit", event))

    from app import create_app

    seams.client = create_app(config={"TESTING": True, "DASHBOARD_TOKEN": TOKEN}).test_client()
    seams.log.clear()
    return seams


def _post(seams, name, body):
    return seams.client.post(
        f"/api/services/{name}/inspect", json=body, headers={"Authorization": f"Bearer {TOKEN}"}
    )


def _emits(seams):
    return [entry[1] for entry in seams.log if entry[0] == "emit"]


def _names(seams):
    return [entry[0] for entry in seams.log]


def test_open_webui_is_refused_before_the_body_is_read(seams):
    response = _post(seams, "open-webui", {})

    assert (response.status_code, response.get_json()) == (
        400, {"error": "Cannot inspect infrastructure services"},
    )
    assert seams.log == []


@pytest.mark.parametrize("body", [{}, {"enabled": "yes"}, {"enabled": 1}, {"enabled": None}])
def test_a_non_boolean_enabled_is_a_400(seams, body):
    response = _post(seams, "svc-a", body)

    assert (response.status_code, response.get_json()) == (400, {"error": "'enabled' must be a boolean"})
    assert seams.log == []


def test_an_unknown_service_is_a_404(seams):
    response = _post(seams, "ghost", {"enabled": True})

    assert (response.status_code, response.get_json()) == (404, {"error": 'Service "ghost" not found'})
    assert seams.log == []


def test_enabling_writes_rebuilds_recreates_then_syncs_the_proxy(seams):
    seams.restarted = True
    seams.status = [{"service": "svc-a", "running": True, "error": None}]

    response = _post(seams, "svc-a", {"enabled": True})

    assert response.status_code == 200
    assert response.get_json() == {
        "service": "svc-a", "enabled": True, "port": 3302, "upstream_port": 34000,
        "proxy_running": True, "restarted": True, "error": None,
    }
    assert _names(seams) == ["db_update", "rebuild", "recreate", "proxy_sync", "emit"]
    assert seams.log[0] == ("db_update", "svc-a", True, 34000)


def test_disabling_writes_syncs_the_proxy_then_rebuilds_and_recreates(seams):
    seams.status = [{"service": "svc-on", "running": False, "error": None}]

    response = _post(seams, "svc-on", {"enabled": False})

    assert response.status_code == 200
    assert response.get_json() == {
        "service": "svc-on", "enabled": False, "port": 3303, "upstream_port": 34007,
        "proxy_running": False, "restarted": False, "error": None,
    }
    assert _names(seams) == ["db_update", "proxy_sync", "rebuild", "recreate", "emit"]
    assert seams.log[0] == ("db_update", "svc-on", False, 34007)


def test_re_enabling_reuses_the_upstream_port_kept_from_before(seams):
    response = _post(seams, "svc-kept", {"enabled": True})

    assert response.get_json()["upstream_port"] == 34003
    assert seams.log[0] == ("db_update", "svc-kept", True, 34003)


@pytest.mark.parametrize("service,enabled", [("svc-on", True), ("svc-a", False)])
def test_a_toggle_to_the_current_state_changes_nothing_but_still_emits(seams, service, enabled):
    response = _post(seams, service, {"enabled": enabled})

    assert response.status_code == 200
    assert response.get_json()["restarted"] is False
    assert _names(seams) == ["emit"]


def test_the_event_names_the_new_inspect_state(seams):
    _post(seams, "svc-a", {"enabled": True})

    (event,) = _emits(seams)
    assert {k: v for k, v in event.items() if k != "timestamp"} == {
        "service_name": "svc-a", "action": "metadata-changed", "status": None,
        "container_id": None, "metadata": {"inspect": True},
    }
    assert isinstance(event["timestamp"], float)


def test_a_proxy_bind_error_is_reported_with_a_200(seams):
    seams.status = [{"service": "svc-a", "running": False, "error": "address in use"}]

    response = _post(seams, "svc-a", {"enabled": True})

    assert response.status_code == 200
    body = response.get_json()
    assert (body["proxy_running"], body["error"]) == (False, "address in use")


def test_no_status_row_reads_as_not_running_without_an_error(seams):
    body = _post(seams, "svc-a", {"enabled": True}).get_json()

    assert (body["proxy_running"], body["error"]) == (False, None)


@pytest.mark.parametrize("step", ["db_update", "rebuild", "recreate", "proxy_sync"])
def test_a_failing_step_is_a_500_and_stops_the_sequence(seams, step):
    seams.fail[step] = RuntimeError("boom")

    response = _post(seams, "svc-a", {"enabled": True})

    assert (response.status_code, response.get_json()) == (500, {"error": "boom"})
    assert "emit" not in _names(seams)
    assert _names(seams)[-1] == step


def test_a_failing_proxy_sync_while_disabling_stops_before_the_rebuild(seams):
    seams.fail["proxy_sync"] = RuntimeError("no port")

    response = _post(seams, "svc-on", {"enabled": False})

    assert (response.status_code, response.get_json()) == (500, {"error": "no port"})
    assert _names(seams) == ["db_update", "proxy_sync"]
