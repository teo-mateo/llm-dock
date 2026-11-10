import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flag_metadata import (
    ENGINE_IMAGES,
    ENGINE_INTERNAL_PORTS,
    FLAG_METADATA_BY_TYPE,
    LLAMACPP_LLAMA_SERVER_FLAGS,
    MANDATORY_FIELDS,
    flag_metadata_types_message,
    get_flag_metadata,
)

TOKEN = "test-token-flag-metadata-table"
BENCH = "llamacpp_bench"
PREVIOUS_MESSAGE = (
    'template_type must be "llamacpp", "ik_llamacpp", "llamacpp_bench", "vllm", '
    '"ds4", "tabbyapi", "ninfer", "sglang", or "maya"'
)


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
