import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chat.llm_proxy import request_model
from engine_catalogue import ENGINE_PRESENTATION, build_catalogue
from flag_metadata import (
    ENGINE_IMAGES,
    MODEL_FIELD_ENGINES,
    SERVICE_ENGINES,
    WEB_UI_ENGINES,
)
from metrics_catalogue import SLOTS_ENGINES

TOKEN = "test-token-engine-rules"
ENGINES = sorted(ENGINE_IMAGES)


@pytest.mark.parametrize("engine", ENGINES)
def test_request_model_sends_the_alias_only_to_engines_that_need_a_model_field(engine):
    sent = request_model({"template_type": engine, "alias": "served-id"})

    assert sent == ("served-id" if engine in {"ninfer", "sglang"} else None)


def test_request_model_rules_are_unchanged_for_the_edge_cases():
    assert request_model({"template_type": "sglang"}) is None
    assert request_model({"template_type": "sglang", "alias": ""}) is None
    assert request_model({"template_type": "vllm", "alias": "x", "model": "provider/model"}) == "provider/model"
    assert request_model({"template_type": "maya", "alias": "maya-x"}) is None
    assert request_model({}) is None


@pytest.fixture
def metrics_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHBOARD_TOKEN", TOKEN)
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    (tmp_path / "services.json").write_text("{}")
    from app import create_app

    app = create_app(config={"TESTING": True, "DASHBOARD_TOKEN": TOKEN, "COMPOSE_FILE": str(tmp_path / "docker-compose.yml")})
    return app.test_client()


@pytest.mark.parametrize("engine", ENGINES)
def test_the_slots_route_serves_only_the_slots_engines(metrics_client, engine):
    import routes.metrics as metrics

    config = {"template_type": engine, "port": 3304, "api_key": "k"}
    with patch.object(metrics, "_get_service_config", lambda name: config), \
            patch.object(metrics, "_fetch_slots", lambda port, key="": []):
        response = metrics_client.get("/api/services/svc/slots", headers={"Authorization": f"Bearer {TOKEN}"})

    assert response.status_code == (200 if engine == "llamacpp" else 400)


def test_the_capability_tables_are_exactly_the_recorded_engines():
    assert SLOTS_ENGINES == {"llamacpp"}
    assert MODEL_FIELD_ENGINES == {"ninfer", "sglang"}
    assert WEB_UI_ENGINES == {"llamacpp"}


@pytest.mark.parametrize("table", [SLOTS_ENGINES, MODEL_FIELD_ENGINES, WEB_UI_ENGINES], ids=["slots", "model", "web_ui"])
def test_every_capability_table_names_only_real_engines(table):
    assert set(table) <= set(SERVICE_ENGINES)


def test_the_catalogue_exposes_slots_and_web_ui_from_those_tables():
    entries = {e["type"]: e for e in build_catalogue()}

    assert {t for t, e in entries.items() if e["slots"]} == set(SLOTS_ENGINES)
    assert {t for t, e in entries.items() if e["web_ui"]} == set(WEB_UI_ENGINES)


def test_the_catalogue_does_not_expose_the_model_field_rule():
    assert all("model_field" not in e and "sends_model" not in e for e in build_catalogue())


def test_every_engine_has_a_badge_label_and_it_is_what_the_badges_show_today():
    labels = {e["type"]: e["badge_label"] for e in build_catalogue()}

    assert labels == {
        "llamacpp": "llama.cpp", "ik_llamacpp": "ik_llama", "vllm": "vLLM", "ds4": "DS4",
        "tabbyapi": "EXL3", "ninfer": "NInfer", "sglang": "SGLang", "maya": "Maya",
    }
    assert all(row["badge_label"] for row in ENGINE_PRESENTATION.values())
