import os
import stat
import sys

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import litellm_gateway


@pytest.fixture(autouse=True)
def routes_dir(tmp_path, monkeypatch):
    """Point the gateway directory at a temp dir so tests never touch the repo."""
    monkeypatch.setenv("LLM_DOCK_LITELLM_DIR", str(tmp_path / "gateway"))
    return tmp_path / "gateway"


SERVICES_DB = {
    "vllm-model-a": {
        "template_type": "vllm",
        "port": 3302,
        "model_name": "model-a",
        "alias": "model-a",
        "api_key": "key-upstream-a",
    },
    "llamacpp-model-b": {
        "template_type": "llamacpp",
        "port": 3309,
        "model_path": "/models/b.gguf",
        "alias": "model-b",
        "api_key": "key-upstream-b",
    },
    "vllm-embeddings": {
        "template_type": "vllm",
        "port": 3370,
        "model_name": "bge-m3",
        "alias": "bge-m3",
        "api_key": "key-embed",
        "params": {"--runner": "pooling"},
    },
    "litellm-gateway": {
        "template_type": "litellm",
        "port": 3377,
        "alias": "gateway",
        "api_key": "key-master",
    },
    "ds4-nokey": {
        "template_type": "ds4",
        "port": 3311,
        "model_path": "/models/ds4",
        "alias": "ds4",
        "api_key": "",
    },
}


def gateway_config(routes, api_key="key-master"):
    return {
        "template_type": "litellm",
        "port": 3377,
        "alias": "gateway",
        "api_key": api_key,
        "routes": routes,
    }


class TestValidateRoutes:
    def test_valid_dock_and_provider_routes(self):
        errors = litellm_gateway.validate_routes(
            [
                {"model": "a", "service": "vllm-model-a"},
                {"model": "b", "provider": "mistral", "upstream_model": "x"},
            ]
        )
        assert errors == []

    def test_empty_routes_rejected(self):
        assert litellm_gateway.validate_routes([])

    def test_route_needs_exactly_one_target(self):
        errors = litellm_gateway.validate_routes(
            [{"model": "a", "service": "s", "provider": "p"}]
        )
        assert any("exactly one" in e for e in errors)
        errors = litellm_gateway.validate_routes([{"model": "a"}])
        assert any("exactly one" in e for e in errors)

    def test_provider_route_needs_upstream_model(self):
        errors = litellm_gateway.validate_routes(
            [{"model": "a", "provider": "mistral"}]
        )
        assert any("upstream_model" in e for e in errors)

    def test_duplicate_model_names_rejected(self):
        errors = litellm_gateway.validate_routes(
            [
                {"model": "a", "service": "s1"},
                {"model": "a", "service": "s2"},
            ]
        )
        assert any("duplicate" in e for e in errors)


class TestResolveRoutes:
    def test_dock_route_uses_container_network(self):
        resolved, warnings = litellm_gateway.resolve_routes(
            [{"model": "a", "service": "vllm-model-a"}], SERVICES_DB
        )
        assert warnings == []
        assert len(resolved) == 1
        # Container name + ENGINE INTERNAL port, never the host port.
        assert resolved[0]["api_base"] == "http://vllm-model-a:8000/v1"
        assert resolved[0]["key"] == "key-upstream-a"
        assert resolved[0]["upstream_model"] == "model-a"

    def test_llamacpp_route_uses_8080(self):
        resolved, _ = litellm_gateway.resolve_routes(
            [{"model": "b", "service": "llamacpp-model-b"}], SERVICES_DB
        )
        assert resolved[0]["api_base"] == "http://llamacpp-model-b:8080/v1"

    def test_missing_service_skipped_with_warning(self):
        resolved, warnings = litellm_gateway.resolve_routes(
            [{"model": "a", "service": "gone"}], SERVICES_DB
        )
        assert resolved == []
        assert any("not defined" in w for w in warnings)

    def test_gateway_and_keyless_services_skipped(self):
        resolved, warnings = litellm_gateway.resolve_routes(
            [
                {"model": "loop", "service": "litellm-gateway"},
                {"model": "nokey", "service": "ds4-nokey"},
            ],
            SERVICES_DB,
        )
        assert resolved == []
        assert any("itself a gateway" in w for w in warnings)
        assert any("no api_key" in w for w in warnings)

    def test_stopped_but_defined_service_is_not_skipped(self):
        # Start/stop state is not in services.json: a defined service renders
        # whether or not its container runs.
        resolved, warnings = litellm_gateway.resolve_routes(
            [{"model": "a", "service": "vllm-model-a"}], SERVICES_DB
        )
        assert len(resolved) == 1

    def test_provider_route_resolved_via_providers_json(self, monkeypatch):
        import chat.providers as chat_providers

        monkeypatch.setattr(
            chat_providers,
            "get_provider",
            lambda pid: {
                "base_url": "https://api.example.com/v1",
                "api_key": "prov-key",
            },
        )
        resolved, warnings = litellm_gateway.resolve_routes(
            [{"model": "m", "provider": "mistral", "upstream_model": "glm"}],
            SERVICES_DB,
        )
        assert warnings == []
        assert resolved[0]["key"] == "prov-key"
        assert resolved[0]["api_base"] == "https://api.example.com/v1"

    def test_provider_without_key_skipped(self, monkeypatch):
        import chat.providers as chat_providers

        monkeypatch.setattr(
            chat_providers, "get_provider", lambda pid: {"base_url": "x"}
        )
        monkeypatch.setattr(chat_providers, "api_key", lambda entry: None)
        resolved, warnings = litellm_gateway.resolve_routes(
            [{"model": "m", "provider": "mistral", "upstream_model": "glm"}],
            SERVICES_DB,
        )
        assert resolved == []
        assert any("no api key" in w for w in warnings)


class TestEnsure:
    def test_writes_config_and_env(self, routes_dir):
        config = gateway_config([{"model": "a", "service": "vllm-model-a"}])
        cfg, env, warnings = litellm_gateway.ensure(
            "litellm-gateway", config, SERVICES_DB
        )
        assert warnings == []
        assert cfg.name == "config.yaml"
        assert env.name == "gateway.env"
        assert cfg.parent == routes_dir / "litellm-gateway"

        body = yaml.safe_load(cfg.read_text())
        assert body["litellm_settings"]["drop_params"] is True
        assert body["general_settings"]["master_key"] == "os.environ/LITELLM_MASTER_KEY"
        entry = body["model_list"][0]
        assert entry["model_name"] == "a"
        assert entry["litellm_params"]["api_key"] == "os.environ/UPSTREAM_0_KEY"

        env_body = env.read_text()
        assert "LITELLM_MASTER_KEY=key-master" in env_body
        assert "UPSTREAM_0_KEY=key-upstream-a" in env_body

    def test_config_has_no_secrets_env_is_0600(self, routes_dir):
        config = gateway_config([{"model": "a", "service": "vllm-model-a"}])
        cfg, env, _ = litellm_gateway.ensure(
            "litellm-gateway", config, SERVICES_DB
        )
        config_body = cfg.read_text()
        assert "key-upstream-a" not in config_body
        assert "key-master" not in config_body
        assert stat.S_IMODE(env.stat().st_mode) == 0o600
        assert stat.S_IMODE(cfg.stat().st_mode) == 0o644

    def test_mistral_route_uses_native_prefix(self, monkeypatch, routes_dir):
        import chat.providers as chat_providers

        monkeypatch.setattr(
            chat_providers,
            "get_provider",
            lambda pid: {"base_url": "https://api.mistral.ai/v1", "api_key": "k"},
        )
        config = gateway_config(
            [{"model": "glm", "provider": "mistral", "upstream_model": "zai-glm-5-3"}]
        )
        cfg, _, _ = litellm_gateway.ensure("litellm-gateway", config, SERVICES_DB)
        body = yaml.safe_load(cfg.read_text())
        params = body["model_list"][0]["litellm_params"]
        assert params["model"] == "mistral/zai-glm-5-3"

    def test_invalid_routes_raise(self):
        config = gateway_config([{"model": "a"}])
        with pytest.raises(ValueError, match="exactly one"):
            litellm_gateway.ensure("litellm-gateway", config, SERVICES_DB)

    def test_all_routes_skipped_renders_empty_model_list(self):
        config = gateway_config([{"model": "a", "service": "gone"}])
        config_path, _, warnings = litellm_gateway.ensure("litellm-gateway", config, SERVICES_DB)
        assert yaml.safe_load(config_path.read_text())["model_list"] == []
        assert warnings

    def test_rename_routed_service_rewrites_only_matching_routes(self):
        db = {
            "llamacpp-x": {"template_type": "llamacpp"},
            "gw": gateway_config([
                {"model": "x", "service": "llamacpp-x"},
                {"model": "m", "provider": "mistral", "upstream_model": "m"},
            ]),
        }
        assert litellm_gateway.rename_routed_service(db, "llamacpp-x", "llamacpp-y") == ["gw"]
        assert db["gw"]["routes"][0]["service"] == "llamacpp-y"
        assert "service" not in db["gw"]["routes"][1]
        assert litellm_gateway.rename_routed_service(db, "nope", "other") == []

    def test_remove(self, routes_dir):
        config = gateway_config([{"model": "a", "service": "vllm-model-a"}])
        litellm_gateway.ensure("litellm-gateway", config, SERVICES_DB)
        removed = litellm_gateway.remove("litellm-gateway")
        assert removed == routes_dir / "litellm-gateway"
        assert not removed.exists()
        assert litellm_gateway.remove("litellm-gateway") is None


class TestComposeRendering:
    def test_rendered_compose_has_no_upstream_or_master_keys(self, routes_dir, tmp_path):
        from compose_manager import ComposeManager

        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(
            "services:\n"
            "  # <<<<<<< BEGIN DYNAMIC\n"
            "  # >>>>>>> END DYNAMIC\n"
            "\n"
            "networks:\n"
            "  llm-network:\n"
            "    driver: bridge\n"
        )
        services_path = tmp_path / "services.json"
        manager = ComposeManager(
            str(compose_path), services_db_file=str(services_path)
        )
        services = dict(SERVICES_DB)
        services["litellm-gateway"] = gateway_config(
            [
                {"model": "a", "service": "vllm-model-a"},
                {"model": "b", "service": "llamacpp-model-b"},
            ]
        )
        manager.save_services_db(services)
        manager.rebuild_compose_file()
        rendered = compose_path.read_text()
        # The guarantee is about the gateway's own block: model services put
        # their key in the rendered command line by design (pre-existing
        # behavior), but the gateway must reference only the env file.
        assert "litellm-gateway:" in rendered
        gateway_block = rendered.split("litellm-gateway:", 1)[1]
        assert "key-master" not in gateway_block
        assert "key-upstream-a" not in gateway_block
        assert "gateway.env" in gateway_block
        assert "3377:4000" in gateway_block


def _manager_with_gateway(tmp_path, routes):
    from compose_manager import ComposeManager

    compose_path = tmp_path / "compose.yml"
    compose_path.write_text(
        "services:\n"
        "  # <<<<<<< BEGIN DYNAMIC\n"
        "  # >>>>>>> END DYNAMIC\n"
        "\nnetworks:\n  llm-network:\n    driver: bridge\n"
    )
    manager = ComposeManager(str(compose_path), services_db_file=str(tmp_path / "services.json"))
    services = {k: dict(v) for k, v in SERVICES_DB.items() if k != "litellm-gateway"}
    services["litellm-gateway"] = gateway_config(routes)
    manager.save_services_db(services)
    manager.rebuild_compose_file()
    return manager


class TestRename:
    def test_renaming_the_only_upstream_follows_the_route(self, routes_dir, tmp_path):
        manager = _manager_with_gateway(tmp_path, [{"model": "a", "service": "vllm-model-a"}])

        manager.rename_service("vllm-model-a", "vllm-model-a2")

        route = manager.get_service_from_db("litellm-gateway")["routes"][0]
        assert route["service"] == "vllm-model-a2"
        config = yaml.safe_load((routes_dir / "litellm-gateway" / "config.yaml").read_text())
        assert config["model_list"][0]["litellm_params"]["api_base"].startswith("http://vllm-model-a2:")

    def test_renaming_the_gateway_moves_its_generated_dir(self, routes_dir, tmp_path):
        manager = _manager_with_gateway(tmp_path, [{"model": "a", "service": "vllm-model-a"}])

        manager.rename_service("litellm-gateway", "litellm-gw2")

        assert not (routes_dir / "litellm-gateway").exists()
        assert (routes_dir / "litellm-gw2" / "gateway.env").exists()

    def test_deleting_the_only_upstream_still_rebuilds(self, routes_dir, tmp_path):
        manager = _manager_with_gateway(tmp_path, [{"model": "a", "service": "vllm-model-a"}])

        manager.remove_service_from_db("vllm-model-a")
        manager.rebuild_compose_file()

        config = yaml.safe_load((routes_dir / "litellm-gateway" / "config.yaml").read_text())
        assert config["model_list"] == []


class TestWriteValidation:
    def test_create_rejects_bad_route_grammar(self):
        from service_ops.config_checks import validate

        failed = validate("litellm", gateway_config([{"model": "a"}]))

        assert failed and any("exactly one of 'service' or 'provider'" in e for e in failed.details)

    def test_create_requires_routes(self):
        from service_ops.config_checks import validate

        config = gateway_config([])
        failed = validate("litellm", config)

        assert failed and "Missing mandatory field: routes" in failed.details

    def test_params_are_rejected(self):
        from service_ops.config_checks import validate

        config = gateway_config([{"model": "a", "service": "x"}])
        config["params"] = {"--num_workers": "4"}

        assert validate("litellm", config).details == ["litellm services take no params"]

    def test_valid_gateway_passes(self):
        from service_ops.config_checks import validate

        assert validate("litellm", gateway_config([{"model": "a", "service": "x"}])) is None
