"""Basalt service: compose render, validation and chat mapping."""
import pytest
import yaml

from compose_manager import ComposeManager, basalt_state_dir
from chat.llm_proxy import request_model
from flag_metadata import (
    BASALT_FLAGS,
    BASALT_RESERVED_FLAGS,
    effective_image,
    engine_internal_port,
    generate_service_name,
    validate_service_config,
)
from reasoning_levels import request_fields

PACK = ("/hf-cache/hub/models--jesdga--Inkling-2-Mini-Basalt/snapshots/"
        "426fea7456c37c102be8a30d16e4f6bf0dcd892d/Inkling-2-Mini-NVFP4-q8.basalt")


def config(**extra):
    return {"template_type": "basalt", "port": 3340, "alias": "inkling-2-mini",
            "model_path": PACK, "api_key": "key-test", "params": {}, **extra}


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_DOCK_BASALT_STATE_DIR", str(tmp_path / "state"))
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services: {}\n  # <<<<<<< BEGIN DYNAMIC\n  # >>>>>>> END DYNAMIC\n"
                       "networks:\n  llm-network:\n    driver: bridge\n")
    return ComposeManager(str(compose))


def render(manager, cfg, name="basalt-inkling-2-mini"):
    return yaml.safe_load(manager._render_service(name, cfg))[name]


def test_render_serves_the_pack_on_argv_with_the_service_identity(manager):
    rendered = render(manager, config())
    assert rendered["entrypoint"] == ["basalt", "serve"]
    assert rendered["command"] == [
        PACK, "--host", "0.0.0.0", "--port", "8080", "--alias", "inkling-2-mini",
        "--api-key", "key-test", "--allowed-host", "*",
    ]
    assert rendered["image"] == "llm-dock-basalt"
    assert rendered["ports"] == ["3340:8080"]
    assert rendered["ulimits"]["memlock"] == {"soft": -1, "hard": -1}


def test_params_follow_in_order_and_switches_render_bare(manager):
    params = {"--max-context": "262144", "--kv": "fp8", "--fit-max-tokens": "",
              "--vision": "dynamic", "env:BASALT_X": "1"}
    rendered = render(manager, config(params=params))
    assert rendered["command"][11:] == ["--max-context", "262144", "--kv", "fp8",
                                        "--fit-max-tokens", "--vision", "dynamic"]
    assert "BASALT_X=1" in rendered["environment"]


def test_state_dir_exists_before_compose_and_is_home(manager, tmp_path):
    rendered = render(manager, config())
    state = basalt_state_dir("basalt-inkling-2-mini")
    assert state.is_dir()
    assert f"{state}:/data" in rendered["volumes"]
    assert "HOME=/data" in rendered["environment"]
    assert "${HOME}/.cache/huggingface:/hf-cache:ro" in rendered["volumes"]


def test_image_override_is_honoured(manager):
    assert render(manager, config(image="llm-dock-basalt-next"))["image"] == "llm-dock-basalt-next"
    assert effective_image("basalt", {}) == "llm-dock-basalt"


@pytest.mark.parametrize("flag", BASALT_RESERVED_FLAGS)
def test_service_fields_cannot_be_overridden_by_params(flag):
    ok, errors = validate_service_config("basalt", config(params={flag: "x"}))
    assert not ok
    assert any(flag in e for e in errors)


def test_a_plain_config_validates():
    ok, errors = validate_service_config("basalt", config(params={"--kv": "fp8"}))
    assert ok, errors


def test_identity_tables():
    assert engine_internal_port("basalt") == 8080
    assert generate_service_name("basalt", "inkling-2-mini") == "basalt-inkling-2-mini"
    assert all(meta["cli"].startswith("--") for meta in BASALT_FLAGS.values())
    assert not set(BASALT_RESERVED_FLAGS) & {m["cli"] for m in BASALT_FLAGS.values()}


def test_chat_sends_the_alias_and_maps_off_to_none():
    assert request_model({"template_type": "basalt", "alias": "inkling-2-mini"}) == "inkling-2-mini"
    assert request_fields("off", "basalt") == {"reasoning_effort": "none"}
    assert request_fields("high", "basalt") == {"reasoning_effort": "high"}
