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


def test_rotate_rolls_back_services_json_on_compose_failure(compose_manager, monkeypatch):
    """If the compose rebuild fails, services.json must be restored and the
    exception propagated — no half-rotated state."""
    def boom():
        raise RuntimeError("compose validation failed")

    monkeypatch.setattr(compose_manager, "rebuild_compose_file", boom)

    with pytest.raises(RuntimeError, match="compose validation failed"):
        rotate_keys_in_db(compose_manager, "new-shared-key")

    db = compose_manager.list_services_in_db()
    assert all(cfg["api_key"] == "old-key" for cfg in db.values()), (
        "services.json should be rolled back to the pre-rotation key"
    )


def test_route_does_not_commit_env_before_services_and_compose(tmp_path, monkeypatch):
    """Route-level: a compose failure must NOT have touched .env /
    GLOBAL_API_KEY, and services.json must be unchanged (codex iter 1)."""
    import config
    from compose_manager import ComposeManager
    import routes.services as svc

    compose_path = tmp_path / "docker-compose.yml"
    compose_path.write_text(
        "services:\n  # <<<<<<< BEGIN DYNAMIC\n  # >>>>>>> END DYNAMIC\n"
        "\nnetworks:\n  llm-network:\n    driver: bridge\n"
    )
    services_path = tmp_path / "services.json"
    services_path.write_text(
        json.dumps({"svc-a": {"template_type": "vllm", "port": 3301,
                              "model_name": "o/m", "api_key": "old-key",
                              "params": {}}})
    )

    monkeypatch.setattr(config, "GLOBAL_API_KEY", "old-key")
    monkeypatch.setattr(
        svc, "_affected_services_state", lambda: (["svc-a"], [], [])
    )
    monkeypatch.setattr(
        svc, "ComposeManager",
        lambda *_a, **_k: ComposeManager(str(compose_path), services_db_file=str(services_path)),
    )
    # Force the compose rebuild to fail mid-rotation.
    monkeypatch.setattr(
        ComposeManager, "rebuild_compose_file",
        lambda self: (_ for _ in ()).throw(RuntimeError("rebuild failed")),
    )
    # Guard: .env writer must never run in this failure path.
    monkeypatch.setattr(
        config, "set_global_api_key",
        lambda *a, **k: pytest.fail("set_global_api_key called before services/compose committed"),
    )

    os.environ["DASHBOARD_TOKEN"] = "test-token"
    from app import create_app
    app = create_app(config={"TESTING": True, "DASHBOARD_TOKEN": "test-token"})
    client = app.test_client()

    resp = client.post(
        "/api/default-api-key/rotate",
        headers={"Authorization": "Bearer test-token"},
    )

    assert resp.status_code == 500
    assert config.GLOBAL_API_KEY == "old-key"
    db = json.loads(services_path.read_text())
    assert db["svc-a"]["api_key"] == "old-key"


def test_save_services_db_atomic_on_write_failure(compose_manager, monkeypatch):
    """A failed services.json write must leave the original file intact
    (codex iter 2: truncate-then-write would corrupt the rotation commit)."""
    import os as _os

    original_bytes = compose_manager.services_db_path.read_bytes()

    # Temp file is written, but the atomic os.replace fails.
    monkeypatch.setattr(
        "compose_manager.os.replace",
        lambda *a, **k: (_ for _ in ()).throw(OSError("replace failed")),
    )

    with pytest.raises(OSError, match="replace failed"):
        compose_manager.save_services_db({"corrupt": {"api_key": "x"}})

    assert compose_manager.services_db_path.read_bytes() == original_bytes
    # No leftover temp files in the directory.
    leftovers = [
        p for p in compose_manager.services_db_path.parent.iterdir()
        if p.name.startswith(".services.") and p.name.endswith(".json.tmp")
    ]
    assert leftovers == [], f"temp files not cleaned up: {leftovers}"


def test_concurrent_rotations_keep_stores_consistent(tmp_path, monkeypatch):
    """Two concurrent rotate requests must not interleave their
    services.json/compose vs .env writes (codex iter 2)."""
    import threading
    import time
    import config
    from compose_manager import ComposeManager
    import routes.services as svc

    compose_path = tmp_path / "docker-compose.yml"
    compose_path.write_text(
        "services:\n  # <<<<<<< BEGIN DYNAMIC\n  # >>>>>>> END DYNAMIC\n"
        "\nnetworks:\n  llm-network:\n    driver: bridge\n"
    )
    services_path = tmp_path / "services.json"
    services_path.write_text(
        json.dumps({"svc-a": {"template_type": "vllm", "alias": "a",
                              "port": 3301, "model_name": "o/m",
                              "api_key": "old-key", "params": {}}})
    )
    env_path = tmp_path / ".env"
    env_path.write_text("LLM_DOCK_API_KEY=old-key\n")

    monkeypatch.setattr(config, "GLOBAL_API_KEY", "old-key")
    monkeypatch.setattr(svc, "_affected_services_state", lambda: (["svc-a"], [], []))
    monkeypatch.setattr(
        svc, "ComposeManager",
        lambda *_a, **_k: ComposeManager(str(compose_path), services_db_file=str(services_path)),
    )

    def fake_set_global(new_key, dotenv_path=None):
        # Widen the interleave window between the services/compose commit
        # and the .env commit; serialized access keeps stores consistent.
        time.sleep(0.05)
        config.GLOBAL_API_KEY = new_key
        env_path.write_text(f"LLM_DOCK_API_KEY={new_key}\n")

    monkeypatch.setattr(config, "set_global_api_key", fake_set_global)

    os.environ["DASHBOARD_TOKEN"] = "test-token"
    from app import create_app
    app = create_app(config={"TESTING": True, "DASHBOARD_TOKEN": "test-token"})

    results = {}

    def rotate(tag):
        c = app.test_client()
        r = c.post("/api/default-api-key/rotate",
                   headers={"Authorization": "Bearer test-token"})
        results[tag] = (r.status_code, r.get_data(as_text=True))

    t1 = threading.Thread(target=rotate, args=("a",))
    t2 = threading.Thread(target=rotate, args=("b",))
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert results["a"][0] == 200, results["a"]
    assert results["b"][0] == 200, results["b"]

    # Invariant: whatever the final key, every store agrees on it.
    final_db_key = json.loads(services_path.read_text())["svc-a"]["api_key"]
    final_env = env_path.read_text().strip().split("=", 1)[1]
    assert final_db_key == config.GLOBAL_API_KEY == final_env


def test_set_global_api_key_persists_and_updates_in_process(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("LLM_DOCK_API_KEY=old-key\nOTHER=keepme\n")

    monkeypatch.setattr(config, "GLOBAL_API_KEY", "old-key")
    config.set_global_api_key("rotated-key", dotenv_path=str(env_path))

    assert config.GLOBAL_API_KEY == "rotated-key"
    contents = env_path.read_text()
    assert "LLM_DOCK_API_KEY='rotated-key'" in contents or 'LLM_DOCK_API_KEY="rotated-key"' in contents or "LLM_DOCK_API_KEY=rotated-key" in contents
    assert "OTHER=keepme" in contents
