import json
import os
import socket
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from inspector.supervisor import ProxySupervisor


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _svc(port, **extra):
    cfg = {"template_type": "llamacpp", "alias": "x", "port": port, "api_key": "k", "model_path": "/m.gguf", "params": {}}
    cfg.update(extra)
    return cfg


@pytest.fixture
def supervisor(tmp_path, monkeypatch):
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    (tmp_path / "services.json").write_text("{}")
    sup = ProxySupervisor(str(tmp_path / "docker-compose.yml"), str(tmp_path / "i.db"))
    yield sup, tmp_path
    sup.stop_all()


def _write(tmp_path, services):
    (tmp_path / "services.json").write_text(json.dumps(services))


def test_stopped_inspected_service_does_not_hold_a_contested_port(supervisor, monkeypatch):
    sup, tmp_path = supervisor
    port = _free_port()
    _write(tmp_path, {
        "llama": _svc(port, inspect=True, inspect_upstream_port=_free_port()),
        "maya": _svc(port),
    })
    monkeypatch.setattr(sup, "_running_services", lambda: {"maya"})

    sup.sync()

    assert sup.status() == []


def test_running_inspected_service_still_binds_a_contested_port(supervisor, monkeypatch):
    sup, tmp_path = supervisor
    port = _free_port()
    _write(tmp_path, {
        "llama": _svc(port, inspect=True, inspect_upstream_port=_free_port()),
        "maya": _svc(port),
    })
    monkeypatch.setattr(sup, "_running_services", lambda: {"llama"})

    sup.sync()

    assert [r["service"] for r in sup.status()] == ["llama"]


def test_uncontested_stopped_inspected_service_is_unaffected(supervisor, monkeypatch):
    sup, tmp_path = supervisor
    _write(tmp_path, {"llama": _svc(_free_port(), inspect=True, inspect_upstream_port=_free_port())})
    monkeypatch.setattr(sup, "_running_services", lambda: set())

    sup.sync()

    assert [r["service"] for r in sup.status()] == ["llama"]
