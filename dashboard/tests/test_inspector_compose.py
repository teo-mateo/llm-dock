import json

import pytest

import docker_utils
from compose_manager import ComposeManager

INTERNAL_PORTS = {
    "llamacpp": 8080,
    "ik_llamacpp": 8080,
    "vllm": 8000,
    "ds4": 8000,
    "tabbyapi": 8000,
    "ninfer": 8080,
}

TEMPLATE_TYPES = list(INTERNAL_PORTS)


def _config_for(template_type: str, port: int = 3301) -> dict:
    if template_type in ("llamacpp", "ik_llamacpp"):
        return {
            "template_type": template_type,
            "alias": "a",
            "port": port,
            "model_path": "/models/a.gguf",
            "api_key": "key-test",
            "params": {},
        }
    if template_type == "vllm":
        return {
            "template_type": template_type,
            "alias": "a",
            "port": port,
            "model_name": "org/model",
            "api_key": "key-test",
            "params": {},
        }
    if template_type == "ds4":
        return {
            "template_type": template_type,
            "alias": "a",
            "port": port,
            "model_path": "/models/a",
            "api_key": "key-test",
            "params": {},
        }
    if template_type == "tabbyapi":
        return {
            "template_type": template_type,
            "alias": "a",
            "port": port,
            "model_path": "/models/exl3/inner-model",
            "api_key": "key-test",
            "params": {},
        }
    return {
        "template_type": "ninfer",
        "alias": "a",
        "port": port,
        "model_path": "/models/a.ninfer",
        "api_key": "key-test",
        "params": {},
    }


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_DOCK_TABBY_KEYS_DIR", str(tmp_path / "keys"))
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services:\n")
    services = tmp_path / "services.json"
    return ComposeManager(str(compose), services_db_file=str(services))


@pytest.mark.parametrize("template_type", TEMPLATE_TYPES)
def test_inspect_relocates_port_mapping_for_every_template(manager, tmp_path, template_type):
    cfg = _config_for(template_type, port=3301)
    cfg["inspect"] = True
    cfg["inspect_upstream_port"] = 34001
    (tmp_path / "services.json").write_text(json.dumps({"svc-a": cfg}))

    rendered = manager.preview_service("svc-a")

    internal = INTERNAL_PORTS[template_type]
    assert f'"127.0.0.1:34001:{internal}"' in rendered
    assert f'"3301:{internal}"' not in rendered


@pytest.mark.parametrize("template_type", TEMPLATE_TYPES)
def test_absent_inspect_is_byte_identical_to_no_key(manager, tmp_path, template_type):
    base = _config_for(template_type, port=3301)
    (tmp_path / "services.json").write_text(json.dumps({"svc-a": base}))
    plain = manager.preview_service("svc-a")

    base["inspect"] = False
    (tmp_path / "services.json").write_text(json.dumps({"svc-a": base}))
    with_false = manager.preview_service("svc-a")

    assert plain == with_false


def test_inspect_true_without_upstream_port_renders_plain_mapping(manager, tmp_path):
    cfg = _config_for("llamacpp", port=3301)
    cfg["inspect"] = True
    (tmp_path / "services.json").write_text(json.dumps({"svc-a": cfg}))

    rendered = manager.preview_service("svc-a")

    assert '"3301:8080"' in rendered
    assert "127.0.0.1" not in rendered


def _write_compose(tmp_path, body: str):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(body)
    return compose


@pytest.fixture
def ports_env(tmp_path, monkeypatch):
    compose = _write_compose(
        tmp_path,
        "services:\n"
        "  svc-plain:\n"
        "    ports:\n"
        '      - "3302:8080"\n'
        "  svc-inspected:\n"
        "    ports:\n"
        '      - "127.0.0.1:34001:8080"\n'
        "  svc-noports:\n"
        "    image: test\n",
    )
    monkeypatch.setattr(docker_utils, "COMPOSE_FILE", str(compose))
    return tmp_path


def test_get_compose_service_ports_parses_inspected_mapping(ports_env):
    port_map = docker_utils.get_compose_service_ports()
    assert port_map["svc-plain"] == 3302
    assert port_map["svc-inspected"] == 34001
    assert port_map["svc-noports"] == 9999


def test_get_compose_service_ports_survives_inspected_service(ports_env):
    # The historical bug: int("127.0.0.1") raised and took out the whole map.
    port_map = docker_utils.get_compose_service_ports()
    assert set(port_map) == {"svc-plain", "svc-inspected", "svc-noports"}
