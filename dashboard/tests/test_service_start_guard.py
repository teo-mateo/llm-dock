import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import service_start_guard
from inspector.supervisor import proxy_supervisor

SERVICES = {"a": {"port": 3301}, "b": {"port": 3301}}


def test_check_start_names_the_running_owner_without_docker():
    body = service_start_guard.check_start(SERVICES, "a", {"b": "running"})

    assert body["code"] == "port_in_use"
    assert "service 'b'" in body["error"]


def test_check_start_passes_when_the_owner_is_stopped():
    assert service_start_guard.check_start(SERVICES, "a", {"b": "exited"}) is None


def test_check_start_ignores_an_unknown_service():
    assert service_start_guard.check_start(SERVICES, "ghost", {}) is None


def test_finish_start_syncs_only_for_an_inspected_service(monkeypatch):
    syncs = []
    monkeypatch.setattr(proxy_supervisor, "sync", lambda: syncs.append(1))

    service_start_guard.finish_start({"a": {"port": 1}}, "a")
    assert syncs == []

    service_start_guard.finish_start({"a": {"port": 1, "inspect": True}}, "a")
    assert syncs == [1]
