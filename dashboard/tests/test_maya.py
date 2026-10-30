"""Project Maya service: compose render, launcher config, validation and chat mapping."""
import importlib.util
import os
from pathlib import Path

import pytest
import yaml

from compose_manager import ComposeManager, maya_state_dir
from flag_metadata import MAYA_FLAGS, validate_service_config
from chat.llm_proxy import request_model
from model_discovery import resolve_host_path
from reasoning_levels import request_fields

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("maya_launcher", ROOT / "maya/launcher.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)

PACK = os.path.expanduser("~/.cache/maya/DeepSeek-V4.1-2.25/pack-vision-dspark")

DSPARK_PARAMS = {
    "--max-context": "524288",
    "--tp": "1",
    "--threads": "on",
    "--mmap-experts": "on",
    "--dspark": "on",
    "--multi": "2",
    "--reserve-mib": "1536",
    "--sampling-temperature": "1.0",
    "--sampling-top-p": "1.0",
    "--reasoning-effort": "high",
    "--engine-ready-s": "3600",
    "env:MAYA_DS4_SLOT_KEEP": "1",
    "env:MAYA_DS4_SLOT_GB": "8",
}


def config(**extra):
    return {"template_type": "maya", "port": 3345, "alias": "maya-deepseek",
            "model_path": PACK, "api_key": "key-test", "params": {}, **extra}


@pytest.fixture
def manager(tmp_path):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services: {}\n  # <<<<<<< BEGIN DYNAMIC\n  # >>>>>>> END DYNAMIC\n"
                       "networks:\n  llm-network:\n    driver: bridge\n")
    return ComposeManager(str(compose))


def render(manager, cfg, name="maya-deepseek"):
    return yaml.safe_load(manager._render_service(name, cfg))[name]


def test_render_hands_the_launcher_its_argv_and_env(manager):
    rendered = render(manager, config(params=DSPARK_PARAMS))
    command = rendered["command"]
    assert command[:6] == ["--pack", PACK, "--model-name", "maya-deepseek", "--api-key", "key-test"]
    for flag, value in (("--max-context", "524288"), ("--multi", "2"), ("--reserve-mib", "1536"),
                        ("--reasoning-effort", "high")):
        assert command[command.index(flag) + 1] == value
    assert not any(arg.startswith("env:") for arg in command)
    assert "MAYA_DS4_SLOT_KEEP=1" in rendered["environment"]
    assert "MAYA_DS4_SLOT_GB=8" in rendered["environment"]


def test_render_runs_as_the_host_user_with_unlimited_memlock(manager):
    rendered = render(manager, config())
    assert rendered["user"] == f"{os.getuid()}:{os.getgid()}"
    assert rendered["ulimits"]["memlock"] == {"soft": -1, "hard": -1}
    assert rendered["stop_grace_period"] == "150s"
    assert rendered["init"] is True
    assert rendered["ports"] == ["3345:8080"]


def test_render_mounts_hf_cache_and_packs_at_their_host_paths(manager):
    volumes = render(manager, config())["volumes"]
    assert "${HOME}/.cache/huggingface:${HOME}/.cache/huggingface:ro" in volumes
    assert "${HOME}/.cache/maya:${HOME}/.cache/maya" in volumes


def test_render_creates_the_state_dir_before_compose_can(manager):
    state = maya_state_dir("maya-deepseek")
    assert not str(state).startswith(str(Path.home() / ".cache"))
    volumes = render(manager, config())["volumes"]
    assert f"{state}:/maya-state" in volumes
    assert state.is_dir()


def test_inspected_service_binds_loopback(manager):
    rendered = render(manager, config(inspect=True, inspect_upstream_port=34007))
    assert rendered["ports"] == ["127.0.0.1:34007:8080"]


@pytest.fixture
def ds4_pack(tmp_path):
    pack = tmp_path / "pack-vision-dspark"
    (pack / "tokenizer").mkdir(parents=True)
    (pack / "ds4.txt").write_text("format gguf\n")
    return pack


@pytest.fixture
def glm_pack(tmp_path):
    pack = tmp_path / "glm-pack"
    pack.mkdir()
    (pack / "index.txt").write_text("")
    return pack


def build(pack, *extra, state=Path("/maya-state")):
    return launcher.build_config(["--pack", str(pack), "--model-name", "svc", "--api-key", "k", *extra],
                                 state_dir=state, maya_root=Path("/opt/maya"))


def test_launcher_reproduces_the_native_dspark_config(ds4_pack):
    argv = [a for kv in DSPARK_PARAMS.items() if not kv[0].startswith("env:") for a in kv]
    cfg, api_key = build(ds4_pack, *argv)
    assert api_key == "k"
    assert cfg["exe"] == "/opt/maya/build/maya-ds4"
    assert cfg["args"] == ["--pack", str(ds4_pack), "--max-context", "524288", "--tp", "1",
                           "--threads", "on", "--mmap-experts", "on", "--dspark", "on",
                           "--multi", "2", "--reserve-mib", "1536"]
    assert cfg["tokenizer"] == str(ds4_pack / "tokenizer")
    assert cfg["model_name"] == "svc"
    assert cfg["gpu"] == [0]
    assert cfg["sampling"] == {"temperature": 1.0, "top_p": 1.0}
    assert cfg["reasoning_effort"] == "high"
    assert cfg["engine_ready_s"] == 3600
    assert cfg["host"] == "0.0.0.0"
    assert cfg["port"] == 8080
    assert cfg["lib_dirs"] == []
    assert cfg["log"] == "/maya-state/engine.log"
    assert "thinking_budget" not in cfg and "idle_unload_s" not in cfg


def test_launcher_picks_the_glm_engine_and_its_defaults(glm_pack):
    cfg, _ = build(glm_pack, "--max-context", "131072", "--expert-cache", "auto")
    assert cfg["exe"] == "/opt/maya/build/maya"
    assert cfg["args"][:2] == ["--glm-pack", str(glm_pack)]
    assert cfg["sampling"]["top_p"] == 0.95


def test_launcher_keeps_engine_flags_that_share_a_prefix_with_its_own(ds4_pack):
    cfg, _ = build(ds4_pack, "--temperature", "0.7", "--model", "x")
    assert cfg["args"][2:] == ["--temperature", "0.7", "--model", "x"]
    assert cfg["sampling"]["temperature"] == 1.0
    assert cfg["model_name"] == "svc"


def test_launcher_optional_server_knobs(ds4_pack):
    cfg, _ = build(ds4_pack, "--thinking-budget", "0", "--idle-unload", "600",
                   "--reasoning-effort", "40", "--gpu", "0,1")
    assert cfg["thinking_budget"] == 0
    assert cfg["idle_unload_s"] == 600.0
    assert cfg["reasoning_effort"] == 40
    assert cfg["gpu"] == [0, 1]


def test_launcher_refuses_a_second_pack_flag(ds4_pack):
    with pytest.raises(SystemExit):
        build(ds4_pack, "--glm-pack", "/elsewhere")


def test_launcher_refuses_a_directory_that_is_not_a_pack(tmp_path):
    with pytest.raises(SystemExit):
        build(tmp_path)


def test_launcher_server_argv_carries_no_api_key():
    argv = launcher.server_argv(Path("/maya-state/maya.json"), 8080, maya_root=Path("/opt/maya"))
    assert argv[1:] == ["/opt/maya/serve/server.py", "--engine", "strata", "--config",
                        "/maya-state/maya.json", "--host", "0.0.0.0", "--port", "8080"]


@pytest.mark.parametrize("params,valid", [
    ({}, True),
    (DSPARK_PARAMS, True),
    ({"--pack": "/other"}, False),
    ({"--glm-pack": "/other"}, False),
    ({"--api-key": "override"}, False),
    ({"--model-name": "other"}, False),
    ({"--port": "9000"}, False),
])
def test_validation_keeps_launcher_fields_out_of_params(params, valid):
    accepted, errors = validate_service_config("maya", config(params=params))
    assert accepted is valid, errors


def test_flag_metadata_defaults_are_the_dspark_run():
    by_cli = {meta["cli"]: meta.get("default") for meta in MAYA_FLAGS.values()}
    for flag, value in DSPARK_PARAMS.items():
        if not flag.startswith("env:"):
            assert by_cli[flag] == value, flag


def test_chat_sends_no_model_and_maps_reasoning_effort():
    assert request_model({"template_type": "maya", "alias": "maya-deepseek"}) is None
    assert request_fields("off", "maya") == {"reasoning_effort": "none"}
    assert request_fields("max", "maya") == {"reasoning_effort": "max"}


def test_pack_paths_resolve_to_themselves():
    assert resolve_host_path(PACK) == PACK


def test_an_uncreatable_state_dir_does_not_fail_the_render(manager, monkeypatch, tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir(mode=0o500)
    monkeypatch.setenv("LLM_DOCK_MAYA_STATE_DIR", str(locked / "maya"))
    volumes = render(manager, config())["volumes"]
    assert f"{locked}/maya/maya-deepseek:/maya-state" in volumes
