import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import openwebui_integration
from flag_metadata import ENGINE_INTERNAL_PORTS, engine_internal_port

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
    ],
)
def test_table_pins_each_engine(template_type, port):
    assert engine_internal_port(template_type) == port


def test_unknown_engine_defaults_to_8000():
    assert engine_internal_port("not-an-engine") == 8000


def test_table_matches_what_the_templates_publish():
    """The port Open WebUI dials has to be the port the compose file publishes."""
    published = {}
    for template in sorted(TEMPLATES_DIR.glob("*.j2")):
        match = PUBLISHED_PORT.search(template.read_text())
        assert match, f"{template.name} publishes no container port"
        published[template.stem] = int(match.group(1))

    assert published == ENGINE_INTERNAL_PORTS


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
