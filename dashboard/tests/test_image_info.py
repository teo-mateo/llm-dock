"""Image provenance info: built or pulled, timestamps, size.

The pure helpers own classification (build label vs name convention vs
registry reference), get_image_info is the single owner of the inspect read,
and the endpoint test proves the service payload's image name is what gets
inspected.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import docker
from docker_utils import _image_registry, _image_source, get_image_info


# -- _image_source -----------------------------------------------------


def test_build_label_wins_over_name():
    assert _image_source("weird-name", {"org.llm-dock.build.date": "2026-01-01"}) == "built"


def test_llm_dock_name_without_labels_is_built():
    assert _image_source("llm-dock-vllm:cu129-580", {}) == "built"


def test_registry_reference_is_pulled():
    assert _image_source("ghcr.io/open-webui/open-webui:main", {}) == "pulled"


def test_docker_hub_path_is_pulled():
    assert _image_source("vllm/vllm-openai:qwen38", {}) == "pulled"


# -- _image_registry ---------------------------------------------------


@pytest.mark.parametrize("name, registry", [
    ("ghcr.io/open-webui/open-webui:main", "ghcr.io"),
    ("registry.example.com:5000/foo/bar", "registry.example.com:5000"),
    ("localhost/foo", "localhost"),
    ("vllm/vllm-openai:tag", "docker.io"),
    ("llm-dock-vllm", None),
    ("llm-dock-vllm:cu129-580", None),
])
def test_registry_extraction(name, registry):
    assert _image_registry(name) == registry


# -- get_image_info ----------------------------------------------------


class _FakeImage:
    def __init__(self, attrs):
        self.attrs = attrs


class _FakeImages:
    def __init__(self, image):
        self._image = image

    def get(self, name):
        if self._image is None:
            raise docker.errors.ImageNotFound(name)
        return self._image


class _FakeClient:
    def __init__(self, image):
        self.images = _FakeImages(image)


def _inspect(monkeypatch, attrs):
    image = None if attrs is None else _FakeImage(attrs)
    monkeypatch.setattr(docker, "from_env", lambda: _FakeClient(image))


def test_built_image_with_labels(monkeypatch):
    _inspect(monkeypatch, {
        "Created": "2026-09-15T23:44:42Z",
        "Size": 4_800_000_000,
        "Config": {"Labels": {
            "org.llm-dock.build.date": "2026-09-15T21:39:13Z",
            "org.llm-dock.build.commit": "eddd3197f1811590ca75530bc820be2a024d5f13",
        }},
    })
    info = get_image_info("llm-dock-ninfer")
    assert info["exists"] is True
    assert info["source"] == "built"
    assert info["build_date"] == "2026-09-15T21:39:13Z"
    assert info["build_commit"].startswith("eddd3197")
    assert info["registry"] is None
    assert info["size"] == 4_800_000_000


def test_pulled_image_exposes_registry_and_upstream(monkeypatch):
    _inspect(monkeypatch, {
        "Created": "2025-10-20T03:49:23Z",
        "Size": 4_500_000_000,
        "Config": {"Labels": {
            "org.opencontainers.image.source": "https://github.com/open-webui/open-webui",
            "org.opencontainers.image.version": "main",
        }},
    })
    info = get_image_info("ghcr.io/open-webui/open-webui:main")
    assert info["source"] == "pulled"
    assert info["registry"] == "ghcr.io"
    assert info["upstream_url"] == "https://github.com/open-webui/open-webui"
    assert info["upstream_version"] == "main"
    assert info["build_date"] is None


def test_missing_image_reports_absent(monkeypatch):
    _inspect(monkeypatch, None)
    info = get_image_info("llm-dock-gone")
    assert info["exists"] is False
    assert info["source"] is None


# -- endpoint ----------------------------------------------------------


@pytest.fixture
def app(tmp_path):
    from app import create_app

    compose_path = tmp_path / "docker-compose.yml"
    compose_path.write_text(
        "services:\n"
        "  # <<<<<<< BEGIN DYNAMIC\n"
        "  # >>>>>>> END DYNAMIC\n"
    )
    return create_app(
        config={
            "TESTING": True,
            "COMPOSE_FILE": str(compose_path),
            "BENCHMARK_DB_PATH": str(tmp_path / "benchmarks.db"),
            "DASHBOARD_TOKEN": "test-token",
        }
    )


AUTH = {"Authorization": "Bearer test-token"}


def test_image_endpoint_inspects_the_payloads_image(app, monkeypatch):
    import routes.services as services_routes

    monkeypatch.setattr(
        services_routes, "get_docker_services",
        lambda: [{"name": "svc-a", "image": "llm-dock-vllm:cu129-580"}],
    )
    seen = {}

    def fake_info(name):
        seen["name"] = name
        return {"name": name, "exists": True, "source": "built"}

    monkeypatch.setattr(services_routes, "get_image_info", fake_info)

    resp = app.test_client().get("/api/services/svc-a/image", headers=AUTH)
    assert resp.status_code == 200
    assert resp.get_json()["source"] == "built"
    assert seen["name"] == "llm-dock-vllm:cu129-580"


def test_image_endpoint_404s_unknown_service(app, monkeypatch):
    import routes.services as services_routes

    monkeypatch.setattr(services_routes, "get_docker_services", lambda: [])
    resp = app.test_client().get("/api/services/nope/image", headers=AUTH)
    assert resp.status_code == 404
