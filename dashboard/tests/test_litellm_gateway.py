import os
import stat
import sys

import pytest
import yaml

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import litellm_gateway
from litellm_gateway import check_and_resolve, render_config, render_env, resolve_routes, validate_routes
from litellm_gateway_fixtures import NO_PROVIDERS, SERVICES_DB, gateway_config, providers

MISTRAL = providers(mistral=("https://api.mistral.ai/v1", "prov-key"))


@pytest.fixture(autouse=True)
def routes_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_DOCK_LITELLM_DIR", str(tmp_path / "gateway"))
    return tmp_path / "gateway"


class TestValidateRoutes:
    def test_valid_dock_and_provider_routes(self):
        assert validate_routes([
            {"model": "a", "service": "vllm-model-a"},
            {"model": "b", "provider": "mistral", "upstream_model": "x", "params": {"supports_reasoning": False}},
        ]) == []

    def test_empty_routes_rejected(self):
        assert validate_routes([])

    def test_route_needs_exactly_one_target(self):
        assert any("exactly one" in e for e in validate_routes([{"model": "a", "service": "s", "provider": "p"}]))
        assert any("exactly one" in e for e in validate_routes([{"model": "a"}]))

    def test_provider_route_needs_upstream_model(self):
        assert any("upstream_model" in e for e in validate_routes([{"model": "a", "provider": "mistral"}]))

    def test_duplicate_model_names_rejected(self):
        errors = validate_routes([{"model": "a", "service": "s1"}, {"model": "a", "service": "s2"}])
        assert any("duplicate" in e for e in errors)

    @pytest.mark.parametrize("key", ["api_key", "api_base", "model", "extra_headers", "aws_secret_access_key"])
    def test_params_outside_the_allowlist_are_rejected(self, key):
        errors = validate_routes([{"model": "a", "service": "s", "params": {key: "x"}}])
        assert errors == [f"routes[0] ('a'): unsupported params: {key}"]

    def test_allowed_params_reject_nested_values(self):
        errors = validate_routes([{"model": "a", "service": "s", "params": {"timeout": {"Authorization": "Bearer x"}}}])
        assert errors == ["routes[0] ('a'): params.timeout must be a scalar or a list of strings"]

    def test_params_must_be_an_object(self):
        assert validate_routes([{"model": "a", "service": "s", "params": ["x"]}])


class TestResolveRoutes:
    def test_dock_route_uses_container_network(self):
        resolved, warnings = resolve_routes([{"model": "a", "service": "vllm-model-a"}], SERVICES_DB, NO_PROVIDERS)
        assert warnings == []
        assert resolved[0].api_base == "http://vllm-model-a:8000/v1"
        assert resolved[0].key == "key-upstream-a"
        assert resolved[0].upstream_model == "model-a"

    def test_llamacpp_route_uses_8080(self):
        resolved, _ = resolve_routes([{"model": "b", "service": "llamacpp-model-b"}], SERVICES_DB, NO_PROVIDERS)
        assert resolved[0].api_base == "http://llamacpp-model-b:8080/v1"

    @pytest.mark.parametrize("service, reason", [
        ("gone", "not defined"),
        ("litellm-gateway", "itself a gateway"),
        ("ds4-nokey", "no api_key"),
        ("vllm-embeddings", "embedding model"),
    ])
    def test_unroutable_services_are_skipped_with_a_reason(self, service, reason):
        resolved, warnings = resolve_routes([{"model": "x", "service": service}], SERVICES_DB, NO_PROVIDERS)
        assert resolved == []
        assert len(warnings) == 1 and reason in warnings[0]

    def test_provider_route_resolved_through_the_lookup(self):
        resolved, warnings = resolve_routes(
            [{"model": "m", "provider": "mistral", "upstream_model": "glm"}], SERVICES_DB, MISTRAL
        )
        assert warnings == []
        assert (resolved[0].key, resolved[0].api_base) == ("prov-key", "https://api.mistral.ai/v1")

    def test_unknown_and_keyless_providers_are_skipped(self):
        lookup = providers(nokey=("https://x", ""))
        resolved, warnings = resolve_routes(
            [
                {"model": "a", "provider": "gone", "upstream_model": "m"},
                {"model": "b", "provider": "nokey", "upstream_model": "m"},
            ],
            SERVICES_DB,
            lookup,
        )
        assert resolved == []
        assert "not configured" in warnings[0] and "no api key" in warnings[1]

    def test_bad_grammar_becomes_warnings_not_an_exception(self):
        resolved, warnings = check_and_resolve([{"model": "a"}], SERVICES_DB, NO_PROVIDERS)
        assert resolved == []
        assert warnings and warnings[0].startswith("routes not rendered:")


class TestRender:
    def test_config_references_env_keys_only(self):
        resolved, _ = resolve_routes([{"model": "a", "service": "vllm-model-a"}], SERVICES_DB, NO_PROVIDERS)
        body = yaml.safe_load(render_config(resolved))
        assert body["litellm_settings"] == {
            "drop_params": True,
            "use_chat_completions_url_for_anthropic_messages": True,
        }
        assert body["general_settings"]["master_key"] == "os.environ/LITELLM_MASTER_KEY"
        assert body["model_list"][0]["litellm_params"] == {
            "api_key": "os.environ/UPSTREAM_0_KEY",
            "model": "openai/model-a",
            "api_base": "http://vllm-model-a:8000/v1",
        }
        assert render_env("key-master", resolved) == "LITELLM_MASTER_KEY=key-master\nUPSTREAM_0_KEY=key-upstream-a\n"

    def test_mistral_route_uses_native_prefix_and_route_params(self):
        resolved, _ = resolve_routes(
            [{"model": "ds", "provider": "mistral", "upstream_model": "ds-v4", "params": {"supports_reasoning": False}}],
            SERVICES_DB,
            MISTRAL,
        )
        params = yaml.safe_load(render_config(resolved))["model_list"][0]["litellm_params"]
        assert params == {"supports_reasoning": False, "api_key": "os.environ/UPSTREAM_0_KEY", "model": "mistral/ds-v4"}


class TestEnsure:
    def test_writes_secret_free_config_and_0600_env(self, routes_dir):
        cfg, env, warnings = litellm_gateway.ensure(
            "litellm-gateway", gateway_config([{"model": "a", "service": "vllm-model-a"}]), SERVICES_DB, NO_PROVIDERS
        )
        assert warnings == []
        assert cfg == routes_dir / "litellm-gateway" / "config.yaml"
        assert "key-upstream-a" not in cfg.read_text() and "key-master" not in cfg.read_text()
        assert stat.S_IMODE(env.stat().st_mode) == 0o600
        assert stat.S_IMODE(cfg.stat().st_mode) == 0o644

    def test_bad_routes_render_an_empty_model_list(self):
        cfg, env, warnings = litellm_gateway.ensure(
            "litellm-gateway", gateway_config("garbage"), SERVICES_DB, NO_PROVIDERS
        )
        assert yaml.safe_load(cfg.read_text())["model_list"] == []
        assert env.read_text() == "LITELLM_MASTER_KEY=key-master\n"
        assert warnings

    def test_remove(self, routes_dir):
        litellm_gateway.ensure(
            "litellm-gateway", gateway_config([{"model": "a", "service": "vllm-model-a"}]), SERVICES_DB, NO_PROVIDERS
        )
        assert litellm_gateway.remove("litellm-gateway") == routes_dir / "litellm-gateway"
        assert not (routes_dir / "litellm-gateway").exists()
        assert litellm_gateway.remove("litellm-gateway") is None


def test_rename_routed_service_rewrites_only_matching_routes():
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
