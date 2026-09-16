"""The service payload's image field: what a service runs with.

ENGINE_IMAGES pins one image per engine; the template guard keeps the table in
step with templates/*.j2; the payload tests cover both branches of
get_docker_services — the running container's creation-time image and the
not-created default (honouring the services.json override where the engine
allows one).
"""
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flag_metadata import ENGINE_IMAGES, default_engine_image

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

IMAGE_LINE = re.compile(r"^\s+image:\s*(.+?)\s*$", re.MULTILINE)


class _FakeContainer:
    def __init__(self, service_name, image):
        self.labels = {"com.docker.compose.service": service_name}
        self.status = "running"
        self.id = "deadbeefcafe"
        self.attrs = {
            "Created": "2026-01-01T00:00:00Z",
            "State": {"ExitCode": 0},
            "Config": {"Image": image},
        }
        self.ports = {}


class _FakeContainerList:
    def __init__(self, containers):
        self._containers = containers

    def list(self, **kwargs):
        return list(self._containers)


class _FakeClient:
    def __init__(self, containers=None):
        self.containers = _FakeContainerList(containers or [])


class _FakeComposeMgr:
    def __init__(self, entries):
        self._entries = entries

    def get_service_from_db(self, name):
        return self._entries.get(name)


def _payload(monkeypatch, engine, config=None, container_image=None):
    import docker
    import docker_utils

    name = "svc-a"
    config = config or {"api_key": "k", "template_type": engine}
    containers = [_FakeContainer(name, container_image)] if container_image else []
    monkeypatch.setattr(docker, "from_env", lambda: _FakeClient(containers))
    monkeypatch.setattr(docker_utils, "get_compose_services", lambda: [name])
    monkeypatch.setattr(docker_utils, "get_compose_service_ports", lambda: {name: 3301})
    monkeypatch.setattr(docker_utils, "get_openwebui_registered_urls", lambda: [])
    monkeypatch.setattr(docker_utils, "compute_model_size", lambda *a, **k: (None, None))
    monkeypatch.setattr(
        docker_utils, "ComposeManager",
        lambda *a, **k: _FakeComposeMgr({name: config}),
    )
    return {s["name"]: s for s in docker_utils.get_docker_services()}[name]


def test_table_matches_the_templates():
    """The image the payload reports for a not-created service is the one the
    compose template renders — verbatim for the fixed engines, and the
    {{ image }} default the table owns for the override-capable ones."""
    rendered = {}
    for template in sorted(TEMPLATES_DIR.glob("*.j2")):
        matches = IMAGE_LINE.findall(template.read_text())
        assert len(matches) == 1, f"{template.name} has {len(matches)} image lines"
        rendered[template.stem] = matches[0]

    assert sorted(rendered) == sorted(ENGINE_IMAGES)
    for engine, image in ENGINE_IMAGES.items():
        assert rendered[engine] in ("{{ image }}", image), (
            f"{engine}: template renders {rendered[engine]!r}, table pins {image!r}"
        )


@pytest.mark.parametrize("engine", sorted(ENGINE_IMAGES))
def test_not_created_payload_reports_the_default_image(monkeypatch, engine):
    assert _payload(monkeypatch, engine)["image"] == ENGINE_IMAGES[engine]


def test_unknown_engine_reports_no_image(monkeypatch):
    assert default_engine_image("not-an-engine") == ""
    assert _payload(monkeypatch, "not-an-engine")["image"] == ""


@pytest.mark.parametrize("engine", ["llamacpp", "ik_llamacpp", "vllm"])
def test_not_created_payload_honours_the_services_json_override(monkeypatch, engine):
    config = {"api_key": "k", "template_type": engine, "image": "my-pinned:build"}
    assert _payload(monkeypatch, engine, config)["image"] == "my-pinned:build"


def test_running_payload_reports_the_creation_time_image(monkeypatch):
    """The container's creation-time image is what runs, even when services.json
    names a different image after the fact."""
    config = {"api_key": "k", "template_type": "vllm", "image": "llm-dock-vllm"}
    payload = _payload(monkeypatch, "vllm", config, container_image="llm-dock-vllm:old")
    assert payload["image"] == "llm-dock-vllm:old"
