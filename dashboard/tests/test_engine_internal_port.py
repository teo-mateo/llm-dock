import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import openwebui_integration
from flag_metadata import ENGINE_INTERNAL_PORTS, engine_internal_port, openwebui_base_url

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

PUBLISHED_PORT = re.compile(r'-\s*"\{\{ port \}\}:(\d+)"')


class _Completed:
    returncode = 0
    stdout = ""
    stderr = ""


@pytest.fixture
def captured_docker_exec(monkeypatch):
    """Record the script each registration helper sends into the Open WebUI container."""
    scripts = []

    def fake_run(cmd, *args, **kwargs):
        scripts.append(cmd[-1])
        return _Completed()

    monkeypatch.setattr(openwebui_integration.subprocess, "run", fake_run)
    return scripts


@pytest.mark.parametrize(
    "template_type, port",
    [
        ("llamacpp", 8080),
        ("ik_llamacpp", 8080),
        ("vllm", 8000),
        ("ds4", 8000),
        ("tabbyapi", 8000),
        ("ninfer", 8080),
    ],
)
def test_table_pins_each_engine(template_type, port):
    assert engine_internal_port(template_type) == port


def test_unknown_engine_defaults_to_8000():
    assert engine_internal_port("not-an-engine") == 8000


def test_table_matches_what_the_templates_publish():
    """The port Open WebUI dials has to be the port the compose file publishes —
    and exactly one: a second published port (a metrics port beside the API
    port) would drift the table the guard exists to pin."""
    published = {}
    for template in sorted(TEMPLATES_DIR.glob("*.j2")):
        matches = PUBLISHED_PORT.findall(template.read_text())
        assert len(matches) == 1, (
            f"{template.name} publishes {len(matches)} container ports; "
            "the table pins exactly one"
        )
        published[template.stem] = int(matches[0])

    assert published == ENGINE_INTERNAL_PORTS


@pytest.mark.parametrize("engine", sorted(ENGINE_INTERNAL_PORTS))
def test_base_url_pins_the_wire_format(engine):
    """Scheme, port source and suffix have one owner; this is what it must emit."""
    assert openwebui_base_url("svc-a", engine) == f"http://svc-a:{ENGINE_INTERNAL_PORTS[engine]}/v1"


class _FakeComposeMgr:
    """Stand-in for ComposeManager reading entries straight from a dict."""

    def __init__(self, entries):
        self._entries = entries

    def get_service_from_db(self, name):
        return self._entries.get(name)


class _FakeContainer:
    """One running container, so the container-exists branch is exercised too."""

    def __init__(self, service_name):
        self.labels = {"com.docker.compose.service": service_name}
        self.status = "running"
        self.id = "deadbeefcafe"
        self.attrs = {"Created": "2026-01-01T00:00:00Z", "State": {"ExitCode": 0}}
        self.ports = {}


class _FakeContainerList:
    def __init__(self, containers):
        self._containers = containers

    def list(self, **kwargs):
        return list(self._containers)


class _FakeClient:
    def __init__(self, containers=None):
        self.containers = _FakeContainerList(containers or [])


def _payload_with_registered_urls(monkeypatch, engine, registered_urls):
    """The get_docker_services payload for one service, with a fixed registered-URL list."""
    import docker
    import docker_utils

    name = "svc-a"
    monkeypatch.setattr(
        docker, "from_env", lambda: _FakeClient([_FakeContainer(name)])
    )
    monkeypatch.setattr(docker_utils, "get_compose_services", lambda: [name])
    monkeypatch.setattr(docker_utils, "get_compose_service_ports", lambda: {name: 3301})
    monkeypatch.setattr(
        docker_utils, "get_openwebui_registered_urls", lambda: list(registered_urls)
    )
    monkeypatch.setattr(docker_utils, "compute_model_size", lambda *a, **k: (None, None))
    monkeypatch.setattr(
        docker_utils, "ComposeManager",
        lambda *a, **k: _FakeComposeMgr(
            {name: {"api_key": "k", "template_type": engine}}
        ),
    )
    return {s["name"]: s for s in docker_utils.get_docker_services()}[name]


@pytest.mark.parametrize("engine", sorted(ENGINE_INTERNAL_PORTS))
def test_payload_flag_and_registration_check_agree(monkeypatch, engine):
    """The payload's openwebui_registered flag (docker_utils) and
    is_service_registered_in_openwebui (openwebui_integration) compare the same
    URL for every engine — today's drift class, where two modules each built
    http://{name}:{port}/v1 by hand and could disagree, must not return."""
    import openwebui_integration

    name = "svc-a"
    port = ENGINE_INTERNAL_PORTS[engine]
    url = openwebui_base_url(name, engine)
    wrong_port_url = url.replace(f":{port}", f":{port + 1}")

    monkeypatch.setattr(
        openwebui_integration, "get_openwebui_registered_urls", lambda: [url]
    )
    assert _payload_with_registered_urls(monkeypatch, engine, [url])["openwebui_registered"] is True
    assert openwebui_integration.is_service_registered_in_openwebui(name, engine) is True

    monkeypatch.setattr(
        openwebui_integration, "get_openwebui_registered_urls", lambda: [wrong_port_url]
    )
    assert _payload_with_registered_urls(monkeypatch, engine, [wrong_port_url])["openwebui_registered"] is False
    assert openwebui_integration.is_service_registered_in_openwebui(name, engine) is False


@pytest.mark.parametrize(
    "engine, url",
    [
        ("llamacpp", "http://svc-a:8080/v1"),
        ("ik_llamacpp", "http://svc-a:8080/v1"),
        ("vllm", "http://svc-a:8000/v1"),
    ],
)
def test_registered_check_matches_the_engine(
    captured_docker_exec, monkeypatch, engine, url
):
    """The bug: an ik_llamacpp service served 8080 and registered at :8000, so the
    registered endpoint was dead and the check never reported it."""
    monkeypatch.setattr(
        openwebui_integration, "get_openwebui_registered_urls", lambda: [url]
    )
    assert openwebui_integration.is_service_registered_in_openwebui("svc-a", engine)


def test_add_and_remove_send_the_engine_port_to_openwebui(captured_docker_exec):
    """Every call site, not just the table: the URL reaching Open WebUI is the one the
    container answers on, for the engine being registered."""
    for engine, url in (
        ("ik_llamacpp", "http://svc-a:8080/v1"),
        ("tabbyapi", "http://svc-a:8000/v1"),
    ):
        assert openwebui_integration.add_service_to_openwebui(
            "svc-a", 3399, "key-x", engine
        )
        assert openwebui_integration.remove_service_from_openwebui("svc-a", engine)
        assert url in captured_docker_exec[-2]
        assert url in captured_docker_exec[-1]

    assert len(captured_docker_exec) == 4
