"""Pennyroyal service, recipe handoff, chat identity and metrics contracts."""
import importlib.util
import json
from pathlib import Path

import pytest
import yaml
from flask import Flask

from compose_manager import ComposeManager
from flag_metadata import validate_service_config
from chat.llm_proxy import request_model
from reasoning_levels import request_fields
from routes.metrics import _parse_metrics

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("sglang_launcher", ROOT / "sglang/launcher.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def config(**extra):
    return {"template_type": "sglang", "port": 3341, "alias": "qwen-next",
            "model_path": "/local-models/flash-next", "api_key": "key-test",
            "params": {}, **extra}


@pytest.fixture
def manager(tmp_path):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services: {}\n  # <<<<<<< BEGIN DYNAMIC\n  # >>>>>>> END DYNAMIC\n"
                       "networks:\n  llm-network:\n    driver: bridge\n")
    return ComposeManager(str(compose))


def test_render_preserves_profile_cache_mounts_and_auth(manager):
    cfg = config(params={"--profile": "27b", "--draft-model-path": "/hf-cache/draft",
                         "env:PENNY_HICACHE_SIZE_GB": "16"}, image="pennyroyal:custom")
    rendered = yaml.safe_load(manager._render_service("sglang-qwen-next", cfg))["sglang-qwen-next"]
    assert rendered["image"] == "pennyroyal:custom"
    assert rendered["ports"] == ["3341:8001"]
    command = rendered["command"]
    for flag, value in (("--model-path", "/local-models/flash-next"),
                        ("--served-model-name", "qwen-next"), ("--api-key", "key-test"),
                        ("--profile", "27b"), ("--draft-model-path", "/hf-cache/draft")):
        assert command[command.index(flag) + 1] == value
    assert not any(arg.startswith("env:") for arg in command)
    assert "PENNY_HICACHE_SIZE_GB=16" in rendered["environment"]
    assert any("/sglang/sglang-qwen-next/compiler:/cache" in v for v in rendered["volumes"])
    assert any("/sglang/sglang-qwen-next/nixl:/nixl" in v for v in rendered["volumes"])
    assert "seccomp=unconfined" in rendered["security_opt"]


@pytest.mark.parametrize("params,valid", [
    ({}, True),
    ({"--profile": "next-plain"}, True),
    ({"--profile": "27b", "--draft-model-path": "/hf-cache/draft"}, True),
    ({"--profile": "27b"}, False),
    ({"--profile": "unknown"}, False),
    ({"--context-length": "8192"}, False),
    ({"--api-key": "override"}, False),
    ({"env:PENNY_HICACHE_SIZE_GB": "0"}, False),
    ({"env:PENNY_CONTEXT_LENGTH": "200000", "env:PENNY_MEM_FRACTION_STATIC": "0.925"}, True),
    ({"env:PENNY_CONTEXT_LENGTH": "524289"}, False),
    ({"env:PENNY_MEM_FRACTION_STATIC": "nan"}, False),
    ({"env:MAX_RUNNING_REQUESTS": "0"}, False),
])
def test_profile_validation(params, valid):
    accepted, errors = validate_service_config("sglang", config(params=params))
    assert accepted is valid, errors


def test_profile_handoff_overwrites_stale_identity_and_keeps_upstream_recipe():
    env = {"TARGET_MODEL": "stale", launcher.MANAGED_ARGS_ENV: '["--api-key","stale"]'}
    command = launcher.profile_command([
        "--profile", "27b", "--model-path", "/models/target with spaces",
        "--draft-model-path", "/models/draft", "--served-model-name", "alias",
        "--api-key", "new-key",
    ], env)
    assert command == ["/usr/local/bin/pennyroyal", "27b"]
    assert env["TARGET_MODEL"] == "/models/target with spaces"
    assert env["DRAFT_MODEL"] == "/models/draft"
    recipe_args = ["serve", "--model-path", env["TARGET_MODEL"],
                   "--hicache-size", "16", "--served-model-name", "pennyroyal"]
    final = launcher.recipe_command(recipe_args, env)
    assert final[1:1 + len(recipe_args)] == recipe_args
    assert final[-4:] == ["--served-model-name", "alias", "--api-key", "new-key"]
    assert final[0] == "/opt/pennyroyal/.venv/bin/sglang-runtime"


def test_missing_draft_and_unmanaged_cli_rejected_at_launch():
    args = ["--model-path", "/models/target", "--served-model-name", "a", "--api-key", "k"]
    with pytest.raises(SystemExit):
        launcher.profile_command([*args, "--profile", "27b"], {})
    with pytest.raises(SystemExit):
        launcher.profile_command([*args, "--context-length", "8192"], {})


@pytest.mark.parametrize("method,expected", [("modelopt", "modelopt_fp4"),
                                             ("compressed-tensors", "compressed-tensors")])
def test_next_uses_checkpoint_quantization_before_namespace(tmp_path, method, expected):
    (tmp_path / "config.json").write_text(json.dumps({"quantization_config": {"quant_method": method}}))
    env = {"PENNY_CONTEXT_LENGTH": "200000", "MAX_RUNNING_REQUESTS": "5"}
    launcher.profile_command(["--model-path", str(tmp_path), "--served-model-name", "alias",
                              "--api-key", "key-test"], env)
    assert env["LLM_DOCK_TARGET_QUANTIZATION"] == expected
    assert env["PENNY_CONTEXT_LENGTH"] == "200000"


def test_recipe_patch_tracks_runtime_settings_in_namespace():
    recipe_spec = importlib.util.spec_from_file_location("patch_recipes", ROOT / "sglang/patch_recipes.py")
    patcher = importlib.util.module_from_spec(recipe_spec)
    recipe_spec.loader.exec_module(patcher)
    source = '''CONTEXT_LENGTH=524288
PREFILL_CHUNK_SIZE=4096
  --field "context_length=$CONTEXT_LENGTH" \\
  --field "max_mamba_cache_size=24" \\
  --field "chunked_prefill_size=$PREFILL_CHUNK_SIZE" \\
  --field "cuda_arch=12.0")
  --quantization modelopt_fp4 --mem-fraction-static 0.981
  --max-running-requests 4 --max-mamba-cache-size 24 --hicache-size 32
'''
    result = patcher.patch_recipe(source)
    assert 'CONTEXT_LENGTH="${PENNY_CONTEXT_LENGTH:-524288}"' in result
    assert 'target_quantization=$LLM_DOCK_TARGET_QUANTIZATION' in result
    assert '--quantization "$LLM_DOCK_TARGET_QUANTIZATION"' in result
    assert '--max-running-requests "${MAX_RUNNING_REQUESTS:-4}"' in result
    assert 'llm_dock_max_running_requests=${MAX_RUNNING_REQUESTS:-4}' in result
    assert 'max_mamba_cache_size=${MAX_MAMBA_CACHE_SIZE:-24}' in result
    with pytest.raises(ValueError, match="recipe changed"):
        patcher.patch_recipe(source.replace('CONTEXT_LENGTH=524288', 'CONTEXT_LENGTH=123'))


def test_service_create_accepts_sglang_and_rebuilds_in_isolation(manager, monkeypatch):
    from routes import services
    monkeypatch.setattr(services, "COMPOSE_FILE", str(manager.compose_path))
    monkeypatch.setattr(ComposeManager, "_validate_compose_file",
                        lambda *a: {"valid": True, "error": None})
    app = Flask(__name__)
    app.config["DASHBOARD_TOKEN"] = "token"
    app.register_blueprint(services.services_bp)
    response = app.test_client().post("/api/services", json=config(),
                                     headers={"Authorization": "Bearer token"})
    assert response.status_code == 201, response.get_json()
    assert response.get_json()["service_name"] == "sglang-qwen-next"
    assert manager.get_service_from_db("sglang-qwen-next")["template_type"] == "sglang"
    assert '"3341:8001"' in manager.compose_path.read_text()


def test_chat_model_and_reasoning_match_upstream_schema():
    assert request_model(config()) == "qwen-next"
    assert request_fields("off", "sglang") == {"reasoning_effort": "none"}
    assert request_fields("high", "sglang") == {"reasoning_effort": "high"}


def test_metrics_keep_counters_and_gauges_in_their_own_units():
    text = '''# TYPE sglang:prompt_tokens_total counter
sglang:prompt_tokens_total{model_name="alias"} 1000
sglang:prompt_tokens_created{model_name="alias"} 1234567890
# TYPE sglang:spec_accept_rate gauge
sglang:spec_accept_rate{model_name="alias"} 0.8
# TYPE sglang:cache_hit_rate gauge
sglang:cache_hit_rate 0.6
# TYPE sglang:uninteresting gauge
sglang:uninteresting 42
'''
    metrics = _parse_metrics(text, "sglang")
    assert metrics["sglang:prompt_tokens_total"]["model_name=alias"] == 1000
    assert metrics["sglang:spec_accept_rate"]["model_name=alias"] == 0.8
    assert metrics["sglang:cache_hit_rate"]["{}"] == 0.6
    assert "sglang:uninteresting" not in metrics


def test_scheduler_counters_and_pool_stats_survive_scrape_without_created_samples():
    text = '''# TYPE sglang:realtime_tokens_total counter
sglang:realtime_tokens_total{mode="decode",tp_rank="0"} 1234
sglang:realtime_tokens_created{mode="decode",tp_rank="0"} 1790000000
sglang:realtime_tokens_total{mode="prefill_compute",tp_rank="0"} 100
# TYPE sglang:kv_used_tokens gauge
sglang:kv_used_tokens 256
# TYPE sglang:kv_evictable_tokens gauge
sglang:kv_evictable_tokens 4096
# TYPE sglang:hicache_host_total_tokens gauge
sglang:hicache_host_total_tokens 679296
# TYPE sglang:mamba_used_tokens gauge
sglang:mamba_used_tokens 2
'''
    metrics = _parse_metrics(text, "sglang")
    assert metrics["sglang:realtime_tokens_total"] == {
        "mode=decode;tp_rank=0": 1234, "mode=prefill_compute;tp_rank=0": 100}
    assert metrics["sglang:kv_used_tokens"]["{}"] == 256
    assert metrics["sglang:kv_evictable_tokens"]["{}"] == 4096
    assert metrics["sglang:hicache_host_total_tokens"]["{}"] == 679296
    assert metrics["sglang:mamba_used_tokens"]["{}"] == 2


@pytest.mark.parametrize("driver,enabled", [("575.57.08", True), ("580.65.06", False), ("610.30.1", False)])
def test_compat_selection_is_container_only(monkeypatch, driver, enabled):
    from types import SimpleNamespace
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=driver))
    monkeypatch.setattr(Path, "is_file", lambda *a: True)
    env = {"LD_LIBRARY_PATH": "/existing"}
    launcher.configure_cuda_compat(env)
    assert env["LD_LIBRARY_PATH"] == (launcher.COMPAT_DIR + ":/existing" if enabled else "/existing")


def test_compat_can_be_disabled_without_a_driver_probe(monkeypatch):
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **k: pytest.fail("unexpected probe"))
    env = {"SGLANG_USE_CUDA_COMPAT": "0", "LD_LIBRARY_PATH": "/existing"}
    launcher.configure_cuda_compat(env)
    assert env["LD_LIBRARY_PATH"] == "/existing"
