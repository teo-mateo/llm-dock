import functools
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import routes.services as services_route
from compose_manager import ComposeManager
from inspector.supervisor import proxy_supervisor
from service_recreate import (
    NOT_FOUND,
    RECREATE_FAILED,
    RECREATE_TIMEOUT_S,
    force_recreate,
    recreate_service,
)
from services.docker_events import ACTION_TO_STATUS

SERVICES = {"a": {"port": 3301}, "b": {"port": 3302}}


class FakeRun:
    def __init__(self, returncode=0, stderr="", raises=None):
        self.calls = []
        self.returncode = returncode
        self.stderr = stderr
        self.raises = raises

    def __call__(self, command, timeout):
        self.calls.append((command, timeout))
        if self.raises:
            raise self.raises
        return subprocess.CompletedProcess(command, self.returncode, "", self.stderr)


def _recreate(services=SERVICES, name="a", statuses=None, run=None, finish=None, events=None):
    events = events if events is not None else []
    run = run or FakeRun()
    result = recreate_service(
        services,
        name,
        statuses or {},
        "/x/docker-compose.yml",
        rebuild=lambda: events.append("rebuild"),
        run=lambda cmd, t: events.append("run") or run(cmd, t),
        finish=finish or (lambda s, n: events.append("finish")),
    )
    return result, run, events


def test_command_is_a_forced_recreate_of_just_that_service():
    run = FakeRun()

    assert force_recreate("/x/docker-compose.yml", "a", run) is None

    assert run.calls == [(
        ["docker", "compose", "-f", "/x/docker-compose.yml", "up", "-d", "--force-recreate", "a"],
        RECREATE_TIMEOUT_S,
    )]


def test_a_stopped_service_is_recreated_too_and_reports_it_was_not_running():
    result, run, _ = _recreate(statuses={"a": "exited"})

    assert result.ok and result.was_running is False
    assert len(run.calls) == 1


def test_a_running_service_reports_it_was_running():
    result, _, _ = _recreate(statuses={"a": "running"})

    assert result.ok and result.was_running is True
    assert result.body() == {"success": True, "service": "a", "was_running": True}


def test_rebuild_runs_before_docker_and_finish_after_it():
    _, _, events = _recreate()

    assert events == ["rebuild", "run", "finish"]


def test_unknown_service_is_not_found_and_touches_nothing():
    result, run, events = _recreate(name="ghost")

    assert result.code == NOT_FOUND and result.http_status() == 404
    assert run.calls == [] and events == []


def test_port_conflict_is_refused_before_rebuild_and_docker():
    services = {"a": {"port": 3301}, "b": {"port": 3301}}

    result, run, events = _recreate(services=services, statuses={"b": "running"})

    assert result.code == "port_in_use" and result.http_status() == 400
    assert "service 'b'" in result.error
    assert run.calls == [] and events == []


def test_docker_failure_surfaces_the_docker_error_and_skips_finish():
    run = FakeRun(returncode=1, stderr="failed to bind host port 0.0.0.0:3301/tcp")

    result, _, events = _recreate(run=run)

    assert not result.ok and result.code == RECREATE_FAILED
    assert result.error == "failed to bind host port 0.0.0.0:3301/tcp"
    assert "finish" not in events


def test_timeout_becomes_an_error_instead_of_an_exception():
    run = FakeRun(raises=subprocess.TimeoutExpired("docker", 240))

    result, _, events = _recreate(run=run)

    assert not result.ok and "timed out" in result.error
    assert "finish" not in events


def test_docker_events_map_the_recreate_sequence_to_statuses():
    sequence = ["die", "destroy", "start"]

    assert [ACTION_TO_STATUS[a] for a in sequence] == ["exited", "removed", "running"]


@pytest.fixture
def env(tmp_path, monkeypatch):
    compose_path = tmp_path / "docker-compose.yml"
    compose_path.write_text("services: {}\n")
    services_path = tmp_path / "services.json"
    services_path.write_text(json.dumps({"svc-a": {"port": 3301, "template_type": "llamacpp"}}))

    monkeypatch.setenv("DASHBOARD_TOKEN", "test-token")
    monkeypatch.setattr(services_route, "COMPOSE_FILE", str(compose_path))
    rebuilds = []
    monkeypatch.setattr(ComposeManager, "rebuild_compose_file", lambda self: rebuilds.append(1))
    monkeypatch.setattr(proxy_supervisor, "sync", lambda: None)
    monkeypatch.setattr(services_route, "current_statuses", lambda: {"svc-a": "running"})

    from app import create_app

    app = create_app(
        config={
            "TESTING": True,
            "DASHBOARD_TOKEN": "test-token",
            "COMPOSE_FILE": str(compose_path),
            "INSPECTOR_DB_PATH": str(tmp_path / "inspector.db"),
        }
    )
    yield {"client": app.test_client(), "rebuilds": rebuilds}
    proxy_supervisor.configure(compose_path=None, db_path=None)


def _post(env, name):
    return env["client"].post(f"/api/services/{name}/recreate", headers={"Authorization": "Bearer test-token"})


def test_route_requires_auth(env):
    assert env["client"].post("/api/services/svc-a/recreate").status_code == 401


def test_route_maps_success_failure_and_not_found(env, monkeypatch):
    fake = FakeRun()
    monkeypatch.setattr(
        services_route, "recreate_service", functools.partial(recreate_service, run=fake)
    )

    ok = _post(env, "svc-a")
    assert ok.status_code == 200
    assert ok.get_json() == {"success": True, "service": "svc-a", "was_running": True}
    assert fake.calls[0][0][-4:] == ["up", "-d", "--force-recreate", "svc-a"]
    assert env["rebuilds"] == [1]

    assert _post(env, "ghost").status_code == 404

    failing = FakeRun(returncode=1, stderr="boom")
    monkeypatch.setattr(
        services_route, "recreate_service", functools.partial(recreate_service, run=failing)
    )
    bad = _post(env, "svc-a")
    assert bad.status_code == 400
    assert bad.get_json() == {"success": False, "error": "boom", "code": RECREATE_FAILED}


def test_route_refuses_the_infrastructure_service(env):
    resp = _post(env, "open-webui")

    assert resp.status_code == 400
    assert env["rebuilds"] == []


def test_recreate_if_running_still_does_nothing_for_a_stopped_service(monkeypatch):
    calls = []
    monkeypatch.setattr(services_route, "get_service_container", lambda n: None)
    monkeypatch.setattr(services_route, "force_recreate", lambda *a, **k: calls.append(a))

    assert services_route._recreate_if_running("svc-a") == {"restarted": False}
    assert calls == []


def test_recreate_if_running_delegates_and_reports_the_error(monkeypatch):
    class Running:
        status = "running"

    monkeypatch.setattr(services_route, "get_service_container", lambda n: Running())
    monkeypatch.setattr(services_route, "force_recreate", lambda *a, **k: "bind failed")

    assert services_route._recreate_if_running("svc-a") == {"restarted": False, "error": "bind failed"}
