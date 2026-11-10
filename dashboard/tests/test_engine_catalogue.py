import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine_catalogue import ENGINE_PRESENTATION, build_catalogue
from flag_metadata import BENCHMARK_ENGINES, ENGINE_IMAGES, SERVICE_ENGINES, SERVICE_NAME_PREFIXES
from metrics_catalogue import CURATED_METRICS, METRICS_ENGINES

TOKEN = "test-token-engine-catalogue"
FIELDS = {
    "type", "label", "hint", "model_source", "placeholder", "gguf_picker",
    "metrics", "benchmark", "name_prefix",
}
COMPOSE = "services:\n  # <<<<<<< BEGIN DYNAMIC\n  # >>>>>>> END DYNAMIC\n\nnetworks:\n  llm-network:\n    driver: bridge\n"


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHBOARD_TOKEN", TOKEN)
    monkeypatch.setenv("COMPOSE_FILE", str(tmp_path / "docker-compose.yml"))
    (tmp_path / "docker-compose.yml").write_text(COMPOSE)
    (tmp_path / "services.json").write_text(json.dumps({
        "vllm-test": {"template_type": "vllm", "alias": "v", "port": 3302, "model_name": "org/m", "api_key": "k"},
    }))
    from app import create_app

    return create_app(config={"TESTING": True, "DASHBOARD_TOKEN": TOKEN, "COMPOSE_FILE": str(tmp_path / "docker-compose.yml")}).test_client()


def _get(api):
    return api.get("/api/engines", headers={"Authorization": f"Bearer {TOKEN}"})


def test_the_endpoint_requires_auth(api):
    assert api.get("/api/engines").status_code == 401


def test_the_endpoint_returns_every_engine_in_table_order_with_every_field(api):
    engines = _get(api).get_json()["engines"]

    assert [e["type"] for e in engines] == list(SERVICE_ENGINES)
    assert {e["type"] for e in engines} == set(ENGINE_IMAGES)
    assert all(set(e) == FIELDS for e in engines)
    assert engines[0]["type"] == "llamacpp"


def test_prefixes_come_from_the_naming_table_or_the_type():
    for entry in build_catalogue():
        assert entry["name_prefix"] == SERVICE_NAME_PREFIXES.get(entry["type"], entry["type"])


def test_metrics_capability_is_exactly_the_curated_metrics_keys():
    entries = {e["type"]: e for e in build_catalogue()}

    assert {t for t, e in entries.items() if e["metrics"]} == set(CURATED_METRICS) == set(METRICS_ENGINES)
    assert entries["ik_llamacpp"]["metrics"] is False


def test_benchmark_capability_is_exactly_benchmark_engines():
    entries = {e["type"]: e for e in build_catalogue()}

    assert {t for t, e in entries.items() if e["benchmark"]} == set(BENCHMARK_ENGINES) == {"llamacpp"}


def test_the_metrics_route_serves_exactly_the_catalogue_metrics_engines():
    import routes.metrics as metrics_route

    assert metrics_route.CURATED_METRICS is CURATED_METRICS
    assert {e["type"] for e in build_catalogue() if e["metrics"]} == set(CURATED_METRICS)


def test_the_presentation_table_has_one_row_per_service_engine():
    assert set(ENGINE_PRESENTATION) == set(SERVICE_ENGINES)


def test_model_sources_and_the_picker_are_consistent():
    for entry in build_catalogue():
        assert entry["model_source"] in {"file", "directory", "repo"}
        assert not entry["gguf_picker"] or entry["model_source"] == "file"
        assert entry["label"] and entry["hint"] and entry["placeholder"]


def test_the_benchmark_routes_read_the_engine_table(api, monkeypatch):
    import benchmarking.routes as bench_routes

    headers = {"Authorization": f"Bearer {TOKEN}"}
    rejected = api.get("/api/benchmarks/service-defaults/vllm-test", headers=headers)
    assert rejected.status_code == 400

    monkeypatch.setattr(bench_routes, "BENCHMARK_ENGINES", frozenset({"vllm"}))

    accepted = api.get("/api/benchmarks/service-defaults/vllm-test", headers=headers)
    assert accepted.status_code != 400


def test_the_catalogue_modules_are_pure():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    for name in ("engine_catalogue.py", "metrics_catalogue.py"):
        modules = []
        for node in ast.walk(ast.parse((root / name).read_text())):
            if isinstance(node, ast.Import):
                modules += [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules.append(node.module or "")
        assert not [m for m in modules if m.split(".")[0] in {"flask", "routes", "requests"}], name
