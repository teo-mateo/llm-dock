"""Pins what set-public-port does today: status codes, bodies, the order of
its side effects and which failures are fatal. The seams are faked and append
to one log; nothing here may change when the operation moves out of the route
module."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import routes.services as services_route
from compose_manager import ComposeManager
from inspector.supervisor import proxy_supervisor
from service_ops import wiring

TOKEN = "test-token-public-port"
PUBLIC = 3301


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
        self.free_ports = iter(range(3310, 3320))
        self.restarts = {}

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
        "svc-b": _svc(PUBLIC),
        "svc-c": _svc(PUBLIC, port_note="second holder"),
        "svc-d": _svc(3304),
    }))
    monkeypatch.setattr(services_route, "COMPOSE_FILE", str(compose))
    monkeypatch.setattr(ComposeManager, "get_used_ports", lambda self: {3300, 3302})
    monkeypatch.setattr(
        ComposeManager, "update_service_in_db",
        lambda self, name, config: seams.step("db_update", name, config["port"]),
    )
    monkeypatch.setattr(ComposeManager, "rebuild_compose_file", lambda self: seams.step("rebuild"))

    def pick(services, used, start, end):
        seams.step("next_free_port", sorted(used), start, end)
        return next(seams.free_ports)

    monkeypatch.setattr(wiring, "next_free_port", pick)

    def recreate(compose_file, name, *args, **kwargs):
        seams.step("recreate", name)
        return seams.restarts.get(name, {"restarted": False})

    monkeypatch.setattr(wiring, "recreate_if_running", recreate)
    monkeypatch.setattr(proxy_supervisor, "sync", lambda: seams.step("proxy_sync"))

    from app import create_app

    seams.client = create_app(config={"TESTING": True, "DASHBOARD_TOKEN": TOKEN}).test_client()
    seams.log.clear()
    return seams


def _post(seams, name):
    return seams.client.post(
        f"/api/services/{name}/set-public-port", json={}, headers={"Authorization": f"Bearer {TOKEN}"}
    )


def test_an_unknown_service_is_a_404(seams):
    response = _post(seams, "ghost")

    assert (response.status_code, response.get_json()) == (404, {"error": 'Service "ghost" not found'})
    assert seams.log == []


def test_a_service_already_on_the_public_port_is_a_no_op(seams):
    response = _post(seams, "svc-b")

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True, "message": 'Service "svc-b" is already on port 3301', "no_change": True,
    }
    assert seams.log == []


def test_a_move_with_nobody_displaced_updates_rebuilds_recreates_then_syncs(seams, tmp_path):
    services = json.loads((tmp_path / "services.json").read_text())
    del services["svc-b"], services["svc-c"]
    (tmp_path / "services.json").write_text(json.dumps(services))

    response = _post(seams, "svc-a")

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "message": 'Service "svc-a" now on port 3301',
        "updates": [{"service": "svc-a", "old_port": 3302, "new_port": 3301}],
        "restarts": [{"service": "svc-a", "restarted": False}],
    }
    assert seams.log == [("db_update", "svc-a", 3301), ("rebuild",), ("recreate", "svc-a"), ("proxy_sync",)]


def test_every_holder_of_the_slot_is_moved_in_order_before_the_service_takes_it(seams):
    seams.restarts = {"svc-a": {"restarted": True}, "svc-b": {"restarted": True}}

    response = _post(seams, "svc-a")

    assert response.status_code == 200
    body = response.get_json()
    assert body["updates"] == [
        {"service": "svc-b", "old_port": 3301, "new_port": 3310},
        {"service": "svc-c", "old_port": 3301, "new_port": 3311},
        {"service": "svc-a", "old_port": 3302, "new_port": 3301},
    ]
    assert body["restarts"] == [
        {"service": "svc-a", "restarted": True},
        {"service": "svc-b", "restarted": True},
        {"service": "svc-c", "restarted": False},
    ]
    assert seams.log == [
        ("next_free_port", [3300, 3302], 3300, 3399),
        ("db_update", "svc-b", 3310),
        ("next_free_port", [3300, 3302], 3300, 3399),
        ("db_update", "svc-c", 3311),
        ("db_update", "svc-a", 3301),
        ("rebuild",),
        ("recreate", "svc-a"),
        ("recreate", "svc-b"),
        ("recreate", "svc-c"),
        ("proxy_sync",),
    ]


def test_a_failing_recreate_is_reported_per_service_and_does_not_stop_the_rest(seams):
    seams.fail["recreate"] = RuntimeError("docker down")

    response = _post(seams, "svc-a")

    assert response.status_code == 200
    assert response.get_json()["restarts"] == [
        {"service": "svc-a", "restarted": False, "error": "docker down"},
        {"service": "svc-b", "restarted": False, "error": "docker down"},
        {"service": "svc-c", "restarted": False, "error": "docker down"},
    ]
    assert seams.log[-1] == ("proxy_sync",)


def test_running_out_of_free_ports_is_a_500_with_nothing_written(seams):
    seams.free_ports = iter(())

    response = _post(seams, "svc-a")

    assert response.status_code == 500
    assert "db_update" not in [entry[0] for entry in seams.log]


def test_a_failing_db_update_is_a_500_and_nothing_is_rebuilt(seams):
    seams.fail["db_update"] = RuntimeError("db locked")

    response = _post(seams, "svc-a")

    assert (response.status_code, response.get_json()) == (500, {"error": "db locked"})
    assert "rebuild" not in [entry[0] for entry in seams.log]


def test_a_failing_rebuild_is_a_500_and_nothing_is_recreated(seams):
    seams.fail["rebuild"] = RuntimeError("invalid compose")

    response = _post(seams, "svc-a")

    assert (response.status_code, response.get_json()) == (500, {"error": "invalid compose"})
    assert "recreate" not in [entry[0] for entry in seams.log]


def test_a_failing_proxy_sync_is_a_500_after_the_recreates(seams):
    seams.fail["proxy_sync"] = RuntimeError("inspector down")

    response = _post(seams, "svc-a")

    assert (response.status_code, response.get_json()) == (500, {"error": "inspector down"})
    assert [entry[0] for entry in seams.log].count("recreate") == 3
