import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flag_metadata import (
    ENGINE_IMAGES,
    ENGINE_INTERNAL_PORTS,
    FLAG_METADATA_BY_TYPE,
    LLAMACPP_LLAMA_SERVER_FLAGS,
    MANDATORY_FIELDS,
    SERVICE_ENGINES,
    flag_metadata_types_message,
    service_engines_message,
    get_flag_metadata,
)

TOKEN = "test-token-flag-metadata-table"
BENCH = "llamacpp_bench"
PREVIOUS_MESSAGE = (
    'template_type must be "llamacpp", "ik_llamacpp", "llamacpp_bench", "vllm", '
    '"ds4", "tabbyapi", "ninfer", "sglang", or "maya"'
)


PREVIOUS_CREATE_MESSAGE = (
    'template_type must be "llamacpp", "ik_llamacpp", "vllm", "ds4", "tabbyapi", '
    '"ninfer", "sglang", or "maya"'
)
TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DASHBOARD_TOKEN", TOKEN)
    from app import create_app

    return create_app(config={"TESTING": True, "DASHBOARD_TOKEN": TOKEN}).test_client()


def _get(client, template_type):
    return client.get(f"/api/flag-metadata/{template_type}", headers={"Authorization": f"Bearer {TOKEN}"})


@pytest.mark.parametrize("engine", sorted(ENGINE_IMAGES) + [BENCH])
def test_every_engine_and_the_bench_type_get_their_flag_metadata(client, engine):
    response = _get(client, engine)

    assert response.status_code == 200
    body = response.get_json()
    assert body["template_type"] == engine
    assert body["optional_flags"]
    assert body["mandatory_fields"] == MANDATORY_FIELDS.get(engine, [])


def test_an_unknown_type_is_a_400_naming_every_allowed_type(client):
    response = _get(client, "not-an-engine")

    assert response.status_code == 400
    message = response.get_json()["error"]
    assert all(f'"{name}"' in message for name in FLAG_METADATA_BY_TYPE)


def test_the_message_wording_is_unchanged():
    assert flag_metadata_types_message() == PREVIOUS_MESSAGE


def test_the_route_requires_auth(client):
    assert client.get("/api/flag-metadata/vllm").status_code == 401


def test_an_unknown_type_has_no_metadata_and_the_llamacpp_family_shares_one_table():
    assert get_flag_metadata("not-an-engine") == {}
    assert get_flag_metadata("llamacpp") is get_flag_metadata("ik_llamacpp") is LLAMACPP_LLAMA_SERVER_FLAGS


def test_the_engine_tables_agree_on_which_engines_exist():
    engines = set(ENGINE_IMAGES)
    tables = {
        "FLAG_METADATA_BY_TYPE": set(FLAG_METADATA_BY_TYPE) - {BENCH},
        "MANDATORY_FIELDS": set(MANDATORY_FIELDS),
        "ENGINE_INTERNAL_PORTS": set(ENGINE_INTERNAL_PORTS),
    }

    gaps = {
        name: {"missing": sorted(engines - keys), "extra": sorted(keys - engines)}
        for name, keys in tables.items()
        if keys != engines
    }

    assert gaps == {}


def _post(client, body):
    return client.post("/api/services", json=body, headers={"Authorization": f"Bearer {TOKEN}"})


def test_service_engines_are_the_metadata_types_without_the_bench_type():
    assert set(SERVICE_ENGINES) == set(ENGINE_IMAGES)
    assert BENCH not in SERVICE_ENGINES


def test_create_rejects_an_unknown_type_naming_every_engine(client):
    response = _post(client, {"template_type": "not-an-engine"})

    assert response.status_code == 400
    message = response.get_json()["error"]
    assert all(f'"{name}"' in message for name in SERVICE_ENGINES)
    assert BENCH not in message


def test_the_create_message_wording_is_unchanged():
    assert service_engines_message() == PREVIOUS_CREATE_MESSAGE


def test_create_rejects_the_bench_type_it_does_not_serve(client):
    assert _post(client, {"template_type": BENCH}).status_code == 400


@pytest.mark.parametrize("engine", sorted(ENGINE_IMAGES))
def test_create_gets_every_engine_past_the_type_check(client, engine):
    response = _post(client, {"template_type": engine})

    assert response.status_code == 400
    assert response.get_json()["error"] == "Validation failed"


@pytest.mark.parametrize("engine", sorted(ENGINE_IMAGES))
def test_every_engine_has_a_compose_template(engine):
    assert (TEMPLATES / f"{engine}.j2").is_file()


def _minimal_service(engine):
    config = {"template_type": engine, "port": 3399 - 1, "alias": "svc", "api_key": "k", "params": {}}
    if engine == "vllm":
        config["model_name"] = "org/model"
    elif engine == "tabbyapi":
        config["model_path"] = "/exl3/model"
    elif engine == "maya":
        config["model_path"] = "/tmp/maya-pack"
    else:
        config["model_path"] = "/models/model.gguf"
    return config


@pytest.mark.parametrize("engine", sorted(ENGINE_IMAGES))
def test_every_engine_renders_a_minimal_service(tmp_path, monkeypatch, engine):
    from compose_manager import ComposeManager

    monkeypatch.setenv("LLM_DOCK_TABBY_KEYS_DIR", str(tmp_path / "keys"))
    monkeypatch.setenv("LLM_DOCK_MAYA_STATE_DIR", str(tmp_path / "maya"))
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services: {}\n")
    (tmp_path / "services.json").write_text("{}")

    rendered = ComposeManager(str(compose))._render_service(f"{engine}-svc", _minimal_service(engine))

    image_lines = re.findall(r"^\s+image:\s*(\S+)\s*$", rendered, re.M)
    assert image_lines == [ENGINE_IMAGES[engine]]
