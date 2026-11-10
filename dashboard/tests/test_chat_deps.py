import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chat import deps as deps_module
from chat.deps import ChatDeps, deps, deps_for, install, replace_deps
from tests.chat_support import chat_parts

CHAT_DIR = Path(__file__).resolve().parent.parent / "chat"


def test_install_stores_one_frozen_value_and_deps_reads_it():
    app = Flask(__name__)
    parts = chat_parts("db", project_files_dir="/p")

    installed = install(app, **parts)

    with app.app_context():
        assert deps() is installed
    assert deps_for(app) is installed
    assert (installed.db, installed.mcp, installed.bus) == ("db", parts["mcp"], parts["bus"])
    with pytest.raises(Exception):
        installed.db = "other"


@pytest.mark.parametrize("missing", ["db", "mcp", "run_manager", "bus", "services"])
def test_install_with_a_missing_required_part_fails_at_once(missing):
    app = Flask(__name__)
    parts = chat_parts("db")
    del parts[missing]

    with pytest.raises(TypeError, match=missing):
        install(app, **parts)

    assert "CHAT_DEPS" not in app.config


@pytest.mark.parametrize("none_part", ["db", "mcp", "run_manager", "bus", "services"])
def test_a_required_part_cannot_be_none(none_part):
    parts = chat_parts("db")
    parts[none_part] = None

    with pytest.raises(ValueError, match=none_part):
        install(Flask(__name__), **parts)


def test_the_project_files_dir_is_optional():
    assert ChatDeps(**chat_parts("db")).project_files_dir is None


def test_deps_outside_an_installed_app_fails_loudly():
    with Flask(__name__).app_context():
        with pytest.raises(LookupError):
            deps()


def test_replace_deps_swaps_one_collaborator_and_keeps_the_rest():
    app = Flask(__name__)
    install(app, **chat_parts("db"))

    replaced = replace_deps(app, mcp="other")

    assert (replaced.db, replaced.mcp) == ("db", "other")
    assert deps_for(app) is replaced


def test_replace_deps_cannot_blank_a_required_part():
    app = Flask(__name__)
    install(app, **chat_parts("db"))

    with pytest.raises(ValueError, match="mcp"):
        replace_deps(app, mcp=None)


def test_storage_root_prefers_the_configured_dir_and_falls_back_to_the_default(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_DOCK_PROJECT_FILES_DIR", str(tmp_path / "env"))

    assert ChatDeps(**chat_parts("db", project_files_dir="/explicit")).storage_root() == "/explicit"
    assert ChatDeps(**chat_parts("db")).storage_root() == str(tmp_path / "env")


def test_the_default_service_catalog_is_the_docker_one(monkeypatch):
    import docker_utils

    monkeypatch.setattr(docker_utils, "get_docker_services", lambda: [{"name": "x"}])

    assert ChatDeps(**{**chat_parts("db"), "services": deps_module.default_services}).services() == [{"name": "x"}]


def test_init_chat_builds_every_collaborator(tmp_path):
    from chat.bootstrap import init_chat

    app = Flask(__name__)
    init_chat(app, db_path=str(tmp_path / "chat.db"))

    built = deps_for(app)
    assert built.db is not None and built.mcp is not None
    assert built.run_manager is not None and built.bus is not None
    assert built.services is deps_module.default_services
    assert len(built.db.list_prompts()) == 3


def test_routes_still_re_export_init_chat():
    from chat.bootstrap import init_chat
    from chat.routes import init_chat as exported

    assert exported is init_chat


def test_the_policy_modules_import_without_docker_available():
    code = (
        "import sys\n"
        "sys.modules['docker_utils'] = None\n"
        "sys.path.insert(0, '.')\n"
        "import chat.run_config, chat.conversation_policy, chat.run_start\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", code], cwd=CHAT_DIR.parent, capture_output=True, text=True
    )

    assert result.returncode == 0, result.stderr


POLICY_AND_WIRING = (
    "run_config.py", "conversation_policy.py", "run_start.py", "routes.py",
    "bootstrap.py", "http.py", "outcomes.py",
)


def test_the_policy_and_wiring_modules_never_import_docker_utils():
    offenders = [
        name
        for name in POLICY_AND_WIRING
        if re.search(r"^\s*(from|import)\s+docker_utils", (CHAT_DIR / name).read_text(), re.M)
    ]

    assert offenders == []
