import functools
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import routes.services as services_route
from service_ops import wiring
import service_recreate as service_recreate_module
from compose_manager import ComposeManager
from inspector.supervisor import proxy_supervisor
from flag_metadata import plan_image_change
from service_recreate import (
    COMPOSE_REBUILD_FAILED,
    NOT_FOUND,
    RECREATE_FAILED,
    RECREATE_TIMEOUT,
    RECREATE_TIMEOUT_S,
    RESTART_TIMEOUT_S,
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


def _recreate(services=SERVICES, name="a", statuses=None, run=None, rebuild=None, **kwargs):
    events = []
    run = run or FakeRun()

    def do_rebuild():
        events.append("rebuild")
        if rebuild:
            rebuild()

    result = recreate_service(
        services,
        name,
        statuses or {},
        "/x/docker-compose.yml",
        rebuild=do_rebuild,
        run=lambda cmd, t: events.append("run") or run(cmd, t),
        finish=lambda s, n: events.append("finish"),
        **kwargs,
    )
    return result, run, events


def test_command_is_a_forced_recreate_of_just_that_service():
    run = FakeRun()

    assert force_recreate("/x/docker-compose.yml", "a", run).status == "ok"

    assert run.calls == [(
        ["docker", "compose", "-f", "/x/docker-compose.yml", "up", "-d", "--force-recreate", "a"],
        RECREATE_TIMEOUT_S,
    )]


def test_a_stopped_service_is_recreated_too_and_reports_it_was_not_running():
    result, run, _ = _recreate(statuses={"a": "exited"})

    assert result.ok and result.recreated and result.was_running is False
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

    assert result.code == NOT_FOUND
    assert run.calls == [] and events == []


def test_port_conflict_is_refused_before_rebuild_and_docker():
    services = {"a": {"port": 3301}, "b": {"port": 3301}}

    result, run, events = _recreate(services=services, statuses={"b": "running"})

    assert result.code == "port_in_use"
    assert "service 'b'" in result.error
    assert run.calls == [] and events == []


def test_docker_failure_surfaces_the_docker_error_and_still_finishes():
    run = FakeRun(returncode=1, stderr="failed to bind host port 0.0.0.0:3301/tcp")

    result, _, events = _recreate(run=run)

    assert not result.ok and result.code == RECREATE_FAILED
    assert result.error == "failed to bind host port 0.0.0.0:3301/tcp"
    assert events == ["rebuild", "run", "finish"]


def test_timeout_has_its_own_code_and_still_finishes():
    run = FakeRun(raises=subprocess.TimeoutExpired("docker", 240))

    result, _, events = _recreate(run=run)

    assert not result.ok and result.code == RECREATE_TIMEOUT
    assert "timed out" in result.error
    assert events == ["rebuild", "run", "finish"]


def test_timeout_and_failure_are_distinguishable_outcomes():
    timeout = force_recreate("/x", "a", FakeRun(raises=subprocess.TimeoutExpired("d", 1)))
    failed = force_recreate("/x", "a", FakeRun(returncode=1, stderr="x"))

    assert (timeout.status, failed.status) == ("timeout", "failed")


def test_rebuild_failure_is_an_error_body_not_an_exception_and_skips_docker():
    def broken():
        raise ValueError("generated compose file is invalid")

    result, run, events = _recreate(rebuild=broken)

    assert not result.ok and result.code == COMPOSE_REBUILD_FAILED
    assert result.error == "generated compose file is invalid"
    assert run.calls == []
    assert events == ["rebuild", "finish"]


def test_only_if_running_skips_docker_for_a_stopped_service_but_still_rebuilds():
    result, run, events = _recreate(statuses={"a": "exited"}, only_if_running=True)

    assert result.ok and not result.recreated
    assert run.calls == []
    assert events == ["rebuild", "finish"]


def test_only_if_running_recreates_a_running_service_with_the_given_timeout():
    result, run, _ = _recreate(statuses={"a": "running"}, only_if_running=True, timeout=RESTART_TIMEOUT_S)

    assert result.recreated
    assert run.calls[0][1] == RESTART_TIMEOUT_S


def test_only_if_running_skips_the_port_guard_for_a_stopped_service():
    services = {"a": {"port": 3301}, "b": {"port": 3301}}

    result, _, _ = _recreate(services=services, statuses={"b": "running", "a": "exited"}, only_if_running=True)

    assert result.ok and not result.recreated


def test_restart_status_keeps_the_legacy_shape():
    ok, _, _ = _recreate(statuses={"a": "running"}, only_if_running=True)
    skipped, _, _ = _recreate(statuses={"a": "exited"}, only_if_running=True)
    failed, _, _ = _recreate(statuses={"a": "running"}, only_if_running=True, run=FakeRun(returncode=1, stderr="boom"))

    assert ok.restart_status() == {"restarted": True}
    assert skipped.restart_status() == {"restarted": False}
    assert failed.restart_status() == {"restarted": False, "error": "boom"}


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
        service_recreate_module, "recreate_service", functools.partial(recreate_service, run=fake)
    )

    ok = _post(env, "svc-a")
    assert ok.status_code == 200
    assert ok.get_json() == {"success": True, "service": "svc-a", "was_running": True}
    assert fake.calls[0][0][-4:] == ["up", "-d", "--force-recreate", "svc-a"]
    assert env["rebuilds"] == [1]

    assert _post(env, "ghost").status_code == 404

    failing = FakeRun(returncode=1, stderr="boom")
    monkeypatch.setattr(
        service_recreate_module, "recreate_service", functools.partial(recreate_service, run=failing)
    )
    bad = _post(env, "svc-a")
    assert bad.status_code == 400
    assert bad.get_json() == {"success": False, "error": "boom", "code": RECREATE_FAILED}


def test_route_returns_the_rebuild_error_not_a_500(env, monkeypatch):
    def broken(self):
        raise ValueError("generated compose file is invalid")

    monkeypatch.setattr(ComposeManager, "rebuild_compose_file", broken)

    resp = _post(env, "svc-a")

    assert resp.status_code == 400
    assert resp.get_json() == {
        "success": False,
        "error": "generated compose file is invalid",
        "code": COMPOSE_REBUILD_FAILED,
    }


def test_route_maps_a_timeout_to_its_own_code(env, monkeypatch):
    fake = FakeRun(raises=subprocess.TimeoutExpired("docker", 240))
    monkeypatch.setattr(
        service_recreate_module, "recreate_service", functools.partial(recreate_service, run=fake)
    )

    assert _post(env, "svc-a").get_json()["code"] == RECREATE_TIMEOUT


def test_recreate_if_running_does_nothing_for_a_stopped_service(env, monkeypatch):
    monkeypatch.setattr(wiring, "get_service_container", lambda n: None)
    monkeypatch.setattr(service_recreate_module, "run_compose", lambda *a: pytest.fail("docker called"))

    assert services_route._recreate_if_running("svc-a") == {"restarted": False}


def test_recreate_if_running_still_raises_when_the_compose_rebuild_fails(env, monkeypatch):
    class Running:
        status = "running"

    def broken(self):
        raise ValueError("generated compose file is invalid")

    monkeypatch.setattr(wiring, "get_service_container", lambda n: Running())
    monkeypatch.setattr(ComposeManager, "rebuild_compose_file", broken)

    with pytest.raises(ValueError, match="invalid"):
        services_route._rebuild_and_restart(ComposeManager(services_route.COMPOSE_FILE), "svc-a")


@pytest.mark.parametrize(
    "engine,before,after,changed",
    [
        ("llamacpp", {}, {"image": ""}, False),
        ("llamacpp", {"image": "a:1"}, {"image": "a:1"}, False),
        ("llamacpp", {"image": "a:1"}, {"image": ""}, True),
        ("vllm", {}, {"image": "b:2"}, True),
        ("ds4", {}, {"image": "b:2"}, False),
    ],
)
def test_plan_image_change_compares_effective_images(engine, before, after, changed):
    assert plan_image_change(engine, before, after).changed is changed
