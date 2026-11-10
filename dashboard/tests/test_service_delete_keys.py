import json
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import routes.services as services_route
import tabby_keys
from compose_manager import ComposeManager
from inspector.supervisor import proxy_supervisor

TOKEN = "test-token-delete-keys"


def _svc(engine, **extra):
    config = {"template_type": engine, "alias": "a", "port": 3345, "api_key": "k", "params": {}}
    config["model_name" if engine == "vllm" else "model_path"] = "org/m" if engine == "vllm" else "/m"
    config.update(extra)
    return config


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHBOARD_TOKEN", TOKEN)
    monkeypatch.setenv("LLM_DOCK_TABBY_KEYS_DIR", str(tmp_path / "keys"))
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services: {}\n")
    (tmp_path / "services.json").write_text(json.dumps({
        "vllm-a": _svc("vllm"),
        "exl3-b": _svc("tabbyapi", port=3346),
    }))
    monkeypatch.setattr(services_route, "COMPOSE_FILE", str(compose))
    monkeypatch.setattr(ComposeManager, "rebuild_compose_file", lambda self: None)
    monkeypatch.setattr(proxy_supervisor, "sync", lambda: None)
    monkeypatch.setattr(services_route.subprocess, "run", MagicMock())
    from app import create_app

    app = create_app(config={"TESTING": True, "DASHBOARD_TOKEN": TOKEN})
    return app.test_client()


def _delete(api, name):
    return api.delete(f"/api/services/{name}", headers={"Authorization": f"Bearer {TOKEN}"})


def test_deleting_a_service_that_never_had_a_key_file_succeeds(api):
    assert _delete(api, "vllm-a").status_code == 200


def test_deleting_a_non_tabby_service_leaves_another_services_key_file_alone(api):
    key_file = tabby_keys.ensure("exl3-b", "secret")

    assert _delete(api, "vllm-a").status_code == 200

    assert key_file.is_file()


def test_deleting_a_tabby_service_removes_its_key_file(api):
    key_file = tabby_keys.ensure("exl3-b", "secret")

    assert _delete(api, "exl3-b").status_code == 200

    assert not key_file.exists()


def test_a_failing_key_removal_does_not_fail_the_delete(api, monkeypatch):
    def boom(name):
        raise OSError("disk on fire")

    monkeypatch.setattr(tabby_keys, "remove", boom)

    assert _delete(api, "exl3-b").status_code == 200
