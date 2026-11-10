import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import docker_utils
import routes.services as services_route
from compose_manager import ComposeManager
from flag_metadata import (
    ENGINE_IMAGES,
    IMAGE_OVERRIDE_ENGINES,
    effective_image,
    validate_service_config,
)
from inspector.supervisor import proxy_supervisor
from service_recreate import IMAGE_CHANGE_TIMEOUT_S

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
FIXED_ENGINES = sorted(set(ENGINE_IMAGES) - IMAGE_OVERRIDE_ENGINES)
OVERRIDE_ENGINES = sorted(IMAGE_OVERRIDE_ENGINES)
TOKEN = "test-token-image"

COMPOSE_TEMPLATE = """services:
  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: open-webui
    restart: unless-stopped
    ports:
      - "3300:8080"
    networks:
      - llm-network

  # <<<<<<< BEGIN DYNAMIC

  # >>>>>>> END DYNAMIC

networks:
  llm-network:
    driver: bridge
"""


def _cfg(engine, **extra):
    cfg = {"port": 3345, "alias": "svc", "api_key": "k", "template_type": engine, "params": {}}
    if engine == "vllm":
        cfg["model_name"] = "org/model"
    else:
        cfg["model_path"] = "/models/m.gguf"
    cfg.update(extra)
    return cfg


def test_override_engines_are_exactly_the_templates_that_render_an_image_variable():
    rendering = {
        t.stem for t in TEMPLATES.glob("*.j2") if re.search(r"image:\s*{{\s*image\s*}}", t.read_text())
    }

    assert rendering == IMAGE_OVERRIDE_ENGINES


@pytest.mark.parametrize("engine", OVERRIDE_ENGINES)
def test_effective_image_honours_an_override_and_treats_empty_as_default(engine):
    assert effective_image(engine, {"image": "mine:1"}) == "mine:1"
    assert effective_image(engine, {"image": ""}) == ENGINE_IMAGES[engine]
    assert effective_image(engine, {}) == ENGINE_IMAGES[engine]


@pytest.mark.parametrize("engine", FIXED_ENGINES)
def test_effective_image_ignores_an_override_on_a_fixed_image_engine(engine):
    assert effective_image(engine, {"image": "mine:1"}) == ENGINE_IMAGES[engine]


@pytest.mark.parametrize("engine", OVERRIDE_ENGINES)
def test_compose_renders_the_effective_image(tmp_path, engine):
    (tmp_path / "docker-compose.yml").write_text(COMPOSE_TEMPLATE)
    (tmp_path / "services.json").write_text("{}")
    manager = ComposeManager(str(tmp_path / "docker-compose.yml"))
    for label, image in (("empty", ""), ("pinned", "mine:1"), ("absent", None)):
        config = _cfg(engine) if image is None else _cfg(engine, image=image)
        rendered = manager._render_service(f"{engine}-{label}", config)
        expected = effective_image(engine, config)
        assert re.search(rf"^\s+image:\s*{re.escape(expected)}\s*$", rendered, re.MULTILINE), rendered


@pytest.mark.parametrize("engine", OVERRIDE_ENGINES)
def test_validation_accepts_empty_and_a_normal_override(engine):
    for image in ("", "my-build:tag", "registry.example.org/team/img@sha256:abc"):
        valid, errors = validate_service_config(engine, _cfg(engine, image=image))
        assert valid, errors


@pytest.mark.parametrize("engine", FIXED_ENGINES)
def test_validation_rejects_a_nonempty_override_on_a_fixed_image_engine(engine):
    valid, errors = validate_service_config(engine, _cfg(engine, image="mine:1"))

    assert not valid
    assert any("can only be overridden for" in e and "vllm" in e for e in errors)


@pytest.mark.parametrize("engine", FIXED_ENGINES)
def test_validation_accepts_an_empty_image_on_a_fixed_image_engine(engine):
    valid, errors = validate_service_config(engine, _cfg(engine, image=""))

    assert valid, errors


def test_validation_rejects_a_non_string_and_whitespace():
    _, errors = validate_service_config("llamacpp", _cfg("llamacpp", image=42))
    assert any("image must be a string" in e for e in errors)

    _, errors = validate_service_config("llamacpp", _cfg("llamacpp", image="a b"))
    assert any("whitespace" in e for e in errors)


class TestPresenceWarning:
    def test_no_override_means_no_warning(self):
        assert docker_utils.image_presence_warnings(None, lookup=lambda n: pytest.fail("looked up")) == []
        assert docker_utils.image_presence_warnings("", lookup=lambda n: pytest.fail("looked up")) == []

    def test_a_local_image_has_no_warning(self):
        assert docker_utils.image_presence_warnings("x:1", lookup=lambda n: {"exists": True}) == []

    def test_a_missing_image_is_named(self):
        (warning,) = docker_utils.image_presence_warnings("x:1", lookup=lambda n: {"exists": False})

        assert "x:1" in warning and "pulled" in warning

    def test_a_lookup_failure_adds_no_warning(self):
        assert docker_utils.image_presence_warnings(
            "x:1", lookup=lambda n: {"exists": False, "error": "daemon down"}
        ) == []


class Container:
    def __init__(self, status):
        self.status = status


@pytest.fixture
def api(tmp_path, monkeypatch):
    os.environ["DASHBOARD_TOKEN"] = TOKEN
    compose_path = tmp_path / "docker-compose.yml"
    compose_path.write_text(COMPOSE_TEMPLATE)
    services_path = tmp_path / "services.json"
    services_path.write_text("{}")

    from app import create_app

    monkeypatch.setattr(services_route, "COMPOSE_FILE", str(compose_path))
    monkeypatch.setattr(proxy_supervisor, "sync", lambda: None)
    monkeypatch.setattr(docker_utils, "get_image_info", lambda n: {"exists": True})
    state = {"container": None, "docker_calls": [], "docker_rc": 0, "docker_stderr": ""}
    monkeypatch.setattr(services_route, "get_service_container", lambda name: state["container"])

    real_run = subprocess.run

    def fake_run(command, *args, **kwargs):
        if isinstance(command, list) and "--force-recreate" in command:
            state["docker_calls"].append((command, kwargs.get("timeout")))
            return subprocess.CompletedProcess(command, state["docker_rc"], "", state["docker_stderr"])
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)

    app = create_app(config={"TESTING": True, "DASHBOARD_TOKEN": TOKEN})
    from services import event_manager

    deltas = []
    event_manager.register_callback(deltas.append)

    def stored():
        return json.loads(services_path.read_text())

    yield {"client": app.test_client(), "state": state, "deltas": deltas, "stored": stored,
           "compose": compose_path}
    event_manager.unregister_callback(deltas.append)
    proxy_supervisor.configure(compose_path=None, db_path=None)


def _h():
    return {"Authorization": f"Bearer {TOKEN}"}


def _create(api, engine="llamacpp", **extra):
    body = _cfg(engine, **extra)
    resp = api["client"].post("/api/services", json=body, headers=_h())
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["service_name"], resp


def _put(api, name, engine="llamacpp", **extra):
    base = _cfg(engine, **extra)
    base.pop("alias", None)
    base["alias"] = "svc"
    return api["client"].put(f"/api/services/{name}", json=base, headers=_h())


def _image_deltas(api):
    return [d for d in api["deltas"] if "image" in (d.get("metadata") or {})]


class TestCreate:
    def test_response_carries_the_effective_image(self, api):
        _, resp = _create(api, image="mine:1")

        assert resp.get_json()["image"] == "mine:1"

    def test_a_missing_local_image_warns_without_failing(self, api, monkeypatch):
        monkeypatch.setattr(docker_utils, "get_image_info", lambda n: {"exists": False})

        _, resp = _create(api, image="mine:1")

        assert any("mine:1" in w for w in resp.get_json()["warnings"])

    def test_a_fixed_image_engine_with_an_override_is_a_400(self, api):
        resp = api["client"].post("/api/services", json=_cfg("ds4", image="mine:1"), headers=_h())

        assert resp.status_code == 400
        assert any("can only be overridden" in d for d in resp.get_json()["details"])


class TestGetConfig:
    @pytest.mark.parametrize("engine,expected", [("llamacpp", True), ("vllm", True), ("ds4", False)])
    def test_reports_whether_the_engine_honours_an_image(self, api, engine, expected):
        name, _ = _create(api, engine)

        config = api["client"].get(f"/api/services/{name}", headers=_h()).get_json()["config"]

        assert config["image_override"] is expected


class TestUpdate:
    def test_a_stopped_service_stores_the_override_renders_it_and_does_not_recreate(self, api):
        name, _ = _create(api)

        resp = _put(api, name, image="mine:2")

        body = resp.get_json()
        assert resp.status_code == 200
        assert body["image"] == "mine:2" and body["restarted"] is False
        assert api["stored"]()[name]["image"] == "mine:2"
        assert "image: mine:2" in api["compose"].read_text()
        assert api["state"]["docker_calls"] == []

    def test_a_running_service_is_recreated_with_the_long_timeout_and_reports_the_image(self, api):
        name, _ = _create(api)
        api["state"]["container"] = Container("running")

        body = _put(api, name, image="mine:2").get_json()

        assert body["restarted"] is True and "recreate_error" not in body
        (command, timeout), = api["state"]["docker_calls"]
        assert command[-4:] == ["up", "-d", "--force-recreate", name]
        assert timeout == IMAGE_CHANGE_TIMEOUT_S
        assert _image_deltas(api)[-1]["metadata"]["image"] == "mine:2"

    def test_a_params_only_edit_does_not_recreate_or_announce_an_image(self, api):
        name, _ = _create(api, image="mine:2")
        api["state"]["container"] = Container("running")
        before = len(api["deltas"])

        body = _put(api, name, image="mine:2", params={"-c": "4096"}).get_json()

        assert body["restarted"] is False
        assert api["state"]["docker_calls"] == []
        assert not any("image" in (d.get("metadata") or {}) for d in api["deltas"][before:])

    def test_a_failed_recreate_is_reported_and_never_announced_as_the_running_image(self, api):
        name, _ = _create(api)
        api["state"]["container"] = Container("running")
        api["state"].update(docker_rc=1, docker_stderr="pull access denied for mine")
        before = len(api["deltas"])

        resp = _put(api, name, image="mine:2")

        body = resp.get_json()
        assert resp.status_code == 200
        assert body["restarted"] is False
        assert body["recreate_error"] == "pull access denied for mine"
        assert api["stored"]()[name]["image"] == "mine:2"
        assert not any("image" in (d.get("metadata") or {}) for d in api["deltas"][before:])

    def test_an_existing_stopped_container_keeps_its_creation_time_image_in_the_payload(self, api):
        name, _ = _create(api)
        api["state"]["container"] = Container("exited")

        body = _put(api, name, image="mine:2").get_json()

        assert body["restarted"] is False
        assert api["state"]["docker_calls"] == []
        assert _image_deltas(api) == []

    def test_a_service_with_no_container_announces_the_new_image(self, api):
        name, _ = _create(api)

        _put(api, name, image="mine:2")

        assert _image_deltas(api)[-1]["metadata"]["image"] == "mine:2"

    def test_an_empty_image_resets_to_the_engine_default(self, api):
        name, _ = _create(api, image="mine:2")

        body = _put(api, name, image="").get_json()

        assert body["image"] == ENGINE_IMAGES["llamacpp"]
        assert f"image: {ENGINE_IMAGES['llamacpp']}" in api["compose"].read_text()
        assert "image: \n" not in api["compose"].read_text()

    def test_a_non_empty_image_on_a_fixed_image_engine_is_a_400_and_stores_nothing(self, api):
        name, _ = _create(api, "ds4")

        resp = _put(api, name, "ds4", image="mine:2")

        assert resp.status_code == 400
        assert "image" not in api["stored"]()[name]

    def test_a_missing_local_image_warns_but_the_write_succeeds(self, api, monkeypatch):
        name, _ = _create(api)
        monkeypatch.setattr(docker_utils, "get_image_info", lambda n: {"exists": False})

        resp = _put(api, name, image="mine:2")

        assert resp.status_code == 200
        assert any("mine:2" in w for w in resp.get_json()["warnings"])
