import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from service_ops import wiring


def test_delete_deps_takes_an_explicit_stop_container_override():
    calls = []

    deps = wiring.delete_deps("c.yml", stop_container=calls.append)
    deps.stop_container("svc")

    assert calls == ["svc"]


def test_delete_deps_stops_through_docker_compose_by_default(monkeypatch):
    seen = []
    monkeypatch.setattr(wiring.subprocess, "run", lambda command, **kwargs: seen.append((command, kwargs)))

    wiring.delete_deps("c.yml").stop_container("svc")

    assert seen == [(["docker", "compose", "-f", "c.yml", "stop", "svc"], {"capture_output": True, "timeout": 30})]


def test_the_infra_overrides_replace_only_what_they_name():
    deps = wiring.rename_deps("c.yml", now=lambda: 7.0)

    assert deps.infra.now() == 7.0
    assert [h.name for h in deps.infra.hooks] == ["inspector", "benchmarks", "key file", "open webui"]


def test_set_public_port_picks_a_free_port_from_the_33xx_range_by_default(monkeypatch):
    seen = []
    monkeypatch.setattr(wiring, "next_free_port", lambda services, used, start, end: seen.append((start, end)) or 3310)

    deps = wiring.set_public_port_deps("c.yml")

    assert deps.next_free_port({}, set()) == 3310
    assert seen == [(3300, 3399)]


def test_set_public_port_deps_accept_a_picker_and_a_recreate_override():
    deps = wiring.set_public_port_deps(
        "c.yml", next_port=lambda services, used: 3333, recreate=lambda name: {"restarted": True}
    )

    assert deps.next_free_port({}, set()) == 3333
    assert deps.recreate_if_running("svc") == {"restarted": True}


def test_recreate_if_running_reports_not_created_when_there_is_no_container(monkeypatch):
    seen = []
    monkeypatch.setattr(wiring, "get_service_container", lambda name: None)
    monkeypatch.setattr(wiring, "restart_if_running", lambda *args: seen.append(args) or {"restarted": False})

    wiring.recreate_if_running("c.yml", "svc")

    assert seen[0][:3] == ("c.yml", "svc", "not-created")
