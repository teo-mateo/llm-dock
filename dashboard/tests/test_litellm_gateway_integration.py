import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import service_ops
from compose_manager import ComposeManager
from litellm_gateway_fixtures import SERVICES_DB, gateway_config
from service_ops import wiring
from service_ops.config_checks import validate
from service_ops.create_wiring import create_deps

COMPOSE = "services:\n  # <<<<<<< BEGIN DYNAMIC\n  # >>>>>>> END DYNAMIC\n\nnetworks:\n  llm-network:\n    driver: bridge\n"


@pytest.fixture
def gateway_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_DOCK_LITELLM_DIR", str(tmp_path / "gateway"))
    return tmp_path / "gateway"


@pytest.fixture
def stack(tmp_path, gateway_dir):
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text(COMPOSE)
    manager = ComposeManager(str(compose_file), services_db_file=str(tmp_path / "services.json"))
    services = {k: dict(v) for k, v in SERVICES_DB.items() if k != "litellm-gateway"}
    services["litellm-gateway"] = gateway_config([{"model": "a", "service": "vllm-model-a"}])
    manager.save_services_db(services)
    manager.rebuild_compose_file()
    return str(compose_file), manager


def _gateway_yaml(gateway_dir, name="litellm-gateway"):
    return yaml.safe_load((gateway_dir / name / "config.yaml").read_text())


def _rename(compose_file, old, new):
    deps = wiring.rename_deps(
        compose_file,
        get_container=lambda name: None,
        emit=lambda event: None,
        hooks=[wiring.gateway_files_hook(compose_file)],
    )
    return service_ops.rename(deps, old, new)


def test_rendered_compose_carries_no_keys_for_the_gateway(stack):
    compose_file, _ = stack
    block = open(compose_file).read().split("litellm-gateway:", 1)[1]
    assert "key-master" not in block and "key-upstream-a" not in block
    assert "env_file:" in block


def test_renaming_a_routed_service_follows_the_route(stack, gateway_dir):
    compose_file, manager = stack

    _rename(compose_file, "vllm-model-a", "vllm-model-a2")

    assert manager.get_service_from_db("litellm-gateway")["routes"][0]["service"] == "vllm-model-a2"
    api_base = _gateway_yaml(gateway_dir)["model_list"][0]["litellm_params"]["api_base"]
    assert api_base == "http://vllm-model-a2:8000/v1"


def test_renaming_the_gateway_moves_its_generated_dir(stack, gateway_dir):
    compose_file, _ = stack

    _rename(compose_file, "litellm-gateway", "litellm-gw2")

    assert not (gateway_dir / "litellm-gateway").exists()
    assert (gateway_dir / "litellm-gw2" / "gateway.env").exists()


def test_deleting_the_only_upstream_still_rebuilds(stack, gateway_dir):
    _, manager = stack

    manager.remove_service_from_db("vllm-model-a")
    manager.rebuild_compose_file()

    assert _gateway_yaml(gateway_dir)["model_list"] == []


def test_a_hand_broken_route_list_does_not_block_rebuilds(stack, gateway_dir):
    _, manager = stack
    db = manager.list_services_in_db()
    db["litellm-gateway"]["routes"] = [{"model": "a"}]
    manager.save_services_db(db)

    manager.rebuild_compose_file()

    assert _gateway_yaml(gateway_dir)["model_list"] == []


def test_create_returns_skipped_route_warnings(stack):
    compose_file, _ = stack
    deps = create_deps(compose_file, emit=lambda event: None)
    deps = type(deps)(deps.infra, deps.generate_key, lambda image: [], deps.route_warnings)
    body = gateway_config([{"model": "x", "service": "gone"}, {"model": "y", "service": "vllm-model-a"}])
    body.update(alias="gw2", port=3378)

    created = service_ops.create(deps, body)

    assert created.warnings == ["skipped route 'x': service 'gone' is not defined"]


class TestWriteValidation:
    def test_bad_route_grammar_is_a_validation_failure(self):
        failed = validate("litellm", gateway_config([{"model": "a"}]))
        assert failed and any("exactly one of 'service' or 'provider'" in e for e in failed.details)

    def test_routes_are_mandatory(self):
        failed = validate("litellm", gateway_config([]))
        assert failed and failed.details == ["Missing mandatory field: routes"]

    def test_params_are_rejected(self):
        config = gateway_config([{"model": "a", "service": "x"}])
        config["params"] = {"--num_workers": "4"}
        assert validate("litellm", config).details == ["litellm services take no params"]

    def test_reserved_route_params_are_rejected(self):
        failed = validate("litellm", gateway_config([{"model": "a", "service": "x", "params": {"api_key": "k"}}]))
        assert failed.details == ["routes[0] ('a'): unsupported params: api_key"]

    def test_valid_gateway_passes(self):
        assert validate("litellm", gateway_config([{"model": "a", "service": "x"}])) is None
