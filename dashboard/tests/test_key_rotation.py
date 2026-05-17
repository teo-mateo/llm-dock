import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from compose_manager import ComposeManager
from key_rotation import rotate_keys_in_db


@pytest.fixture(autouse=True)
def set_env_vars():
    os.environ["DASHBOARD_TOKEN"] = "test-token"


@pytest.fixture
def compose_manager(tmp_path):
    compose_path = tmp_path / "docker-compose.yml"
    compose_path.write_text(
        "services:\n"
        "  # <<<<<<< BEGIN DYNAMIC\n"
        "  svc-a:\n"
        "    image: test\n"
        "  # >>>>>>> END DYNAMIC\n"
        "\nnetworks:\n  llm-network:\n    driver: bridge\n"
    )
    services_path = tmp_path / "services.json"
    services_path.write_text(
        json.dumps(
            {
                "svc-a": {
                    "template_type": "llamacpp",
                    "alias": "a",
                    "port": 3301,
                    "model_path": "/models/a.gguf",
                    "api_key": "old-key",
                    "params": {},
                },
                "svc-b": {
                    "template_type": "vllm",
                    "alias": "b",
                    "port": 3302,
                    "model_name": "org/b",
                    "api_key": "old-key",
                    "params": {},
                },
            }
        )
    )
    return ComposeManager(str(compose_path), services_db_file=str(services_path))


def test_rotate_updates_every_service(compose_manager):
    result = rotate_keys_in_db(compose_manager, "new-shared-key")

    assert result["new_key"] == "new-shared-key"
    assert sorted(result["updated"]) == ["svc-a", "svc-b"]

    db = compose_manager.list_services_in_db()
    assert all(cfg["api_key"] == "new-shared-key" for cfg in db.values())


def test_rotate_generates_key_when_omitted(compose_manager):
    result = rotate_keys_in_db(compose_manager)

    assert result["new_key"].startswith("key-")
    db = compose_manager.list_services_in_db()
    assert all(cfg["api_key"] == result["new_key"] for cfg in db.values())


def test_rotate_is_idempotent(compose_manager):
    rotate_keys_in_db(compose_manager, "same-key")
    second = rotate_keys_in_db(compose_manager, "same-key")

    # Nothing changed the second time, but every service still carries the key.
    assert second["updated"] == []
    db = compose_manager.list_services_in_db()
    assert all(cfg["api_key"] == "same-key" for cfg in db.values())


def test_set_global_api_key_persists_and_updates_in_process(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("LLM_DOCK_API_KEY=old-key\nOTHER=keepme\n")

    monkeypatch.setattr(config, "GLOBAL_API_KEY", "old-key")
    config.set_global_api_key("rotated-key", dotenv_path=str(env_path))

    assert config.GLOBAL_API_KEY == "rotated-key"
    contents = env_path.read_text()
    assert "LLM_DOCK_API_KEY='rotated-key'" in contents or 'LLM_DOCK_API_KEY="rotated-key"' in contents or "LLM_DOCK_API_KEY=rotated-key" in contents
    assert "OTHER=keepme" in contents
