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


def test_rotation_does_not_drop_concurrent_create(tmp_path, monkeypatch):
    """A service created while a rotation is in flight must not be silently
    dropped by rotation's wholesale snapshot write (codex iter 3)."""
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
        json.dumps({"vllm-existing": {"template_type": "vllm", "alias": "existing",
                                      "port": 3301, "model_name": "o/m",
                                      "api_key": "old-key", "params": {}}})
    )
    env_path = tmp_path / ".env"
    env_path.write_text("LLM_DOCK_API_KEY=old-key\n")

    monkeypatch.setattr(config, "GLOBAL_API_KEY", "old-key")
    monkeypatch.setattr(svc, "_affected_services_state", lambda: (["vllm-existing"], [], []))
    monkeypatch.setattr(
        svc, "ComposeManager",
        lambda *_a, **_k: ComposeManager(str(compose_path), services_db_file=str(services_path)),
    )

    def fake_set_global(new_key, dotenv_path=None):
        # Hold the rotation critical section open long enough that the
        # concurrent create would interleave if it weren't serialized.
        time.sleep(0.1)
        config.GLOBAL_API_KEY = new_key
        env_path.write_text(f"LLM_DOCK_API_KEY={new_key}\n")

    monkeypatch.setattr(config, "set_global_api_key", fake_set_global)

    os.environ["DASHBOARD_TOKEN"] = "test-token"
    from app import create_app
    app = create_app(config={"TESTING": True, "DASHBOARD_TOKEN": "test-token"})
    hdr = {"Authorization": "Bearer test-token"}
    results = {}

    def do_rotate():
        results["rotate"] = app.test_client().post(
            "/api/default-api-key/rotate", headers=hdr).status_code

    def do_create():
        results["create"] = app.test_client().post(
            "/api/services",
            headers=hdr,
            json={"template_type": "vllm", "port": 3302,
                  "model_name": "o/new", "alias": "created", "params": {}},
        ).status_code

    tr = threading.Thread(target=do_rotate)
    tc = threading.Thread(target=do_create)
    tr.start()
    time.sleep(0.02)  # let rotation enter its critical section first
    tc.start()
    tr.join(); tc.join()

    assert results["rotate"] == 200, results
    assert results["create"] == 201, results

    db = json.loads(services_path.read_text())
    # Both the rotated pre-existing service AND the concurrently-created one
    # must survive — rotation must not clobber the create.
    assert "vllm-existing" in db
    assert "vllm-created" in db
    assert db["vllm-existing"]["api_key"] == config.GLOBAL_API_KEY


def test_shared_lock_is_one_object_across_blueprints():
    """services routes, benchmarking routes, and db_lock must all serialize
    on the *same* lock object (codex iter 4)."""
    import db_lock
    import routes.services as svc
    import benchmarking.routes as bench

    assert svc._SERVICES_DB_LOCK is db_lock.SERVICES_DB_LOCK
    assert svc._serialize_db is db_lock.serialize_db
    # apply_benchmark is wrapped by serialize_db (shares the lock).
    assert hasattr(bench.apply_benchmark, "__wrapped__")


def test_rotation_not_reverted_by_concurrent_benchmark_apply(tmp_path, monkeypatch):
    """A benchmark apply running concurrently with a rotation must not write
    its stale full service config back and revert the api_key (codex iter 4)."""
    import threading
    import time
    import config
    from compose_manager import ComposeManager
    from benchmarking.models import BenchmarkRun
    import routes.services as svc
    import benchmarking.routes as bench

    compose_path = tmp_path / "docker-compose.yml"
    compose_path.write_text(
        "services:\n  # <<<<<<< BEGIN DYNAMIC\n  # >>>>>>> END DYNAMIC\n"
        "\nnetworks:\n  llm-network:\n    driver: bridge\n"
    )
    services_path = tmp_path / "services.json"
    services_path.write_text(
        json.dumps({"vllm-existing": {"template_type": "vllm", "alias": "existing",
                                      "port": 3301, "model_name": "o/m",
                                      "api_key": "old-key", "params": {}}})
    )
    env_path = tmp_path / ".env"
    env_path.write_text("LLM_DOCK_API_KEY=old-key\n")

    def cm(*_a, **_k):
        return ComposeManager(str(compose_path), services_db_file=str(services_path))

    monkeypatch.setattr(config, "GLOBAL_API_KEY", "old-key")
    monkeypatch.setattr(svc, "_affected_services_state", lambda: (["vllm-existing"], [], []))
    monkeypatch.setattr(svc, "ComposeManager", cm)
    monkeypatch.setattr(bench, "_get_compose_manager", cm)

    def fake_set_global(new_key, dotenv_path=None):
        time.sleep(0.1)
        config.GLOBAL_API_KEY = new_key
        env_path.write_text(f"LLM_DOCK_API_KEY={new_key}\n")

    monkeypatch.setattr(config, "set_global_api_key", fake_set_global)

    os.environ["DASHBOARD_TOKEN"] = "test-token"
    from app import create_app
    app = create_app(config={
        "TESTING": True,
        "DASHBOARD_TOKEN": "test-token",
        "BENCHMARK_DB_PATH": str(tmp_path / "bench.db"),
    })
    db = app.config["BENCHMARK_DB"]
    db.create_run(BenchmarkRun(
        id="run-1", service_name="vllm-existing", model_path="",
        status="completed", params_json={"--gpu-memory-utilization": "0.5"},
    ))

    hdr = {"Authorization": "Bearer test-token"}
    results = {}

    def do_rotate():
        results["rotate"] = app.test_client().post(
            "/api/default-api-key/rotate", headers=hdr).status_code

    def do_apply():
        results["apply"] = app.test_client().put(
            "/api/benchmarks/run-1/apply", headers=hdr).status_code

    tr = threading.Thread(target=do_rotate)
    ta = threading.Thread(target=do_apply)
    tr.start()
    time.sleep(0.02)
    ta.start()
    tr.join(); ta.join()

    assert results["rotate"] == 200, results
    assert results["apply"] == 200, results

    cfg = json.loads(services_path.read_text())["vllm-existing"]
    # Apply must not have reverted the rotated key...
    assert cfg["api_key"] == config.GLOBAL_API_KEY
    # ...and the applied benchmark param must still be present.
    assert cfg["params"].get("--gpu-memory-utilization") == "0.5"


def test_rotate_partial_failure_when_container_stop_fails(tmp_path, monkeypatch):
    """If a running affected container can't be stopped, the response must
    NOT report unqualified success (codex iter 4)."""
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
        json.dumps({"vllm-x": {"template_type": "vllm", "alias": "x",
                               "port": 3301, "model_name": "o/m",
                               "api_key": "old-key", "params": {}}})
    )

    monkeypatch.setattr(config, "GLOBAL_API_KEY", "old-key")
    monkeypatch.setattr(svc, "_affected_services_state", lambda: (["vllm-x"], ["vllm-x"], []))
    monkeypatch.setattr(
        svc, "ComposeManager",
        lambda *_a, **_k: ComposeManager(str(compose_path), services_db_file=str(services_path)),
    )
    monkeypatch.setattr(config, "set_global_api_key",
                        lambda *a, **k: setattr(config, "GLOBAL_API_KEY", a[0]))
    monkeypatch.setattr(
        svc, "control_service",
        lambda name, action: {"success": False, "error": "docker daemon unreachable"},
    )

    os.environ["DASHBOARD_TOKEN"] = "test-token"
    from app import create_app
    app = create_app(config={"TESTING": True, "DASHBOARD_TOKEN": "test-token"})
    resp = app.test_client().post(
        "/api/default-api-key/rotate", headers={"Authorization": "Bearer test-token"})

    body = resp.get_json()
    assert resp.status_code == 207
    assert body["success"] is False
    assert body["partial"] is True
    assert "vllm-x" in body["stop_errors"]
    # Key still rotated in files (that part succeeded) and returned.
    assert body["new_api_key"] == config.GLOBAL_API_KEY


def test_set_global_api_key_persists_and_updates_in_process(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("LLM_DOCK_API_KEY=old-key\nOTHER=keepme\n")

    monkeypatch.setattr(config, "GLOBAL_API_KEY", "old-key")
    config.set_global_api_key("rotated-key", dotenv_path=str(env_path))

    assert config.GLOBAL_API_KEY == "rotated-key"
    contents = env_path.read_text()
    assert "LLM_DOCK_API_KEY='rotated-key'" in contents or 'LLM_DOCK_API_KEY="rotated-key"' in contents or "LLM_DOCK_API_KEY=rotated-key" in contents
    assert "OTHER=keepme" in contents
