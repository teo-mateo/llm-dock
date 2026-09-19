import atexit
import os
import shutil
import sys
import tempfile

import pytest

# Add dashboard directory to path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarking.db import BenchmarkDB

HERMETIC_COMPOSE = """services: {}
  # <<<<<<< BEGIN DYNAMIC
  # >>>>>>> END DYNAMIC

networks:
  llm-network:
    driver: bridge
"""

_hermetic_base = None


def _hermetic_base_dir() -> str:
    # tmpfs where available: every ChatDB/InspectorDB construction fsyncs its
    # schema, ~100x slower on the host disk than on tmpfs. /dev/shm is not
    # reaped by the OS, so the dir is removed at session end and at exit.
    base = os.environ.get("LLM_DOCK_TEST_TMPDIR")
    if not base and os.path.isdir("/dev/shm"):
        base = "/dev/shm"
    if not base:
        base = tempfile.gettempdir()
    return os.path.join(base, f"llm-dock-pytest-{os.getpid()}")


def pytest_configure(config):
    # Runs before any test module imports config/app, so the values below are
    # what the config module bakes at import time. Without this, a fixture
    # that forgets a COMPOSE_FILE/DB_PATH override silently reads and writes
    # this machine's real services.json, chat.db, benchmarks.db and
    # inspector.db (and the inspector supervisor binds real proxy ports).
    global _hermetic_base
    _hermetic_base = _hermetic_base_dir()
    storage = os.path.join(_hermetic_base, "storage")
    os.makedirs(storage, exist_ok=True)
    with open(os.path.join(storage, "docker-compose.yml"), "w") as f:
        f.write(HERMETIC_COMPOSE)
    with open(os.path.join(storage, "services.json"), "w") as f:
        f.write("{}")
    os.environ.setdefault("DASHBOARD_TOKEN", "test-token")
    os.environ.setdefault("COMPOSE_PROJECT_NAME", "llm-dock")
    os.environ["COMPOSE_FILE"] = os.path.join(storage, "docker-compose.yml")
    os.environ["LLM_DOCK_INSPECTOR_DB"] = os.path.join(storage, "inspector.db")
    os.environ["LLM_DOCK_CHAT_DB"] = os.path.join(storage, "chat.db")
    os.environ["LLM_DOCK_BENCHMARKS_DB"] = os.path.join(storage, "benchmarks.db")

    atexit.register(shutil.rmtree, _hermetic_base, ignore_errors=True)
    config.option.basetemp = os.path.join(_hermetic_base, "tmp")


def pytest_sessionfinish(session, exitstatus):
    global _hermetic_base
    if _hermetic_base and os.path.isdir(_hermetic_base):
        shutil.rmtree(_hermetic_base, ignore_errors=True)
        _hermetic_base = None


@pytest.fixture
def db():
    """Provide an in-memory BenchmarkDB for testing."""
    return BenchmarkDB(":memory:")


@pytest.fixture
def db_file(tmp_path):
    """Provide a file-backed BenchmarkDB for testing."""
    db_path = str(tmp_path / "test_benchmarks.db")
    return BenchmarkDB(db_path)
