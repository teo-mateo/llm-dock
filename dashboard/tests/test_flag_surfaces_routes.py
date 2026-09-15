"""Level-2 guard: service create/update warn (never reject) on unknown flags.

The typo trap is that render_cli_flag passes any dash-prefixed string through to
the container verbatim, so a typo or an upstream-removed flag fails at container
startup, not at config time. These tests pin the advisory behaviour: the write
still succeeds (the passthrough is deliberate), and the response carries a
`warnings` list naming the unknown flags. env: keys are not flags and never warn.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import flag_surfaces

TEST_TOKEN = "test-token-surface"

COMPOSE_TEMPLATE = """services:
  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: open-webui
    restart: unless-stopped
    ports:
      - "3300:8080"
    volumes:
      - open-webui-data:/app/data
    networks:
      - llm-network

  # <<<<<<< BEGIN DYNAMIC

  # >>>>>>> END DYNAMIC

volumes:
  open-webui-data:

networks:
  llm-network:
    driver: bridge
"""


@pytest.fixture
def api(tmp_path, monkeypatch):
    os.environ["DASHBOARD_TOKEN"] = TEST_TOKEN
    compose_path = tmp_path / "docker-compose.yml"
    compose_path.write_text(COMPOSE_TEMPLATE)
    (tmp_path / "services.json").write_text("{}")

    from app import create_app
    import routes.services as services_routes

    monkeypatch.setattr(services_routes, "COMPOSE_FILE", str(compose_path))
    app = create_app(config={"TESTING": True, "DASHBOARD_TOKEN": TEST_TOKEN})
    return app.test_client()


def _headers():
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


def _warned_flags(body):
    """Flag names from the response's warnings (format: 'Unknown <engine> flag: <flag> (…)')."""
    return [w.split("flag: ", 1)[1].split(" (", 1)[0] for w in body.get("warnings", [])]


def _vllm_cfg(**extra):
    cfg = {"port": 3351, "model_name": "org/model", "alias": "surf-vllm",
           "api_key": "k", "template_type": "vllm", "params": {}}
    cfg.update(extra)
    return cfg


def _llamacpp_cfg(**extra):
    cfg = {"port": 3352, "model_path": "/models/m.gguf", "alias": "surf-llama",
           "api_key": "k", "template_type": "llamacpp", "params": {}}
    cfg.update(extra)
    return cfg


# -- pure module -----------------------------------------------------------


def test_unknown_service_params_flags_only_dash_keys():
    assert flag_surfaces.unknown_service_params(
        "vllm", {"--gpu-mem": "1", "env:FOO": "1", "alias": "x"}) == ["--gpu-mem"]


def test_known_flags_produce_no_unknowns():
    assert flag_surfaces.unknown_service_params(
        "vllm", {"--max-model-len": "4096", "--enforce-eager": ""}) == []


def test_unmapped_engine_and_missing_surface_return_empty():
    assert flag_surfaces.unknown_service_params("does-not-exist", {"-x": "1"}) == []
    assert flag_surfaces.unknown_service_params("vllm", {}) == []


def test_stale_removed_flag_is_reported_unknown():
    # --swap-space was removed upstream; the surface has no record of it, so a
    # service created with it is exactly the typo trap this guard exists for.
    assert flag_surfaces.unknown_service_params("vllm", {"--swap-space": "4"}) == ["--swap-space"]


# -- create (POST) ---------------------------------------------------------


def test_create_with_typo_flag_succeeds_and_warns(api):
    resp = api.post("/api/services",
                    json=_vllm_cfg(params={"--gpu-mem": "1", "--max-model-len": "4096"}),
                    headers=_headers())
    assert resp.status_code == 201, resp.get_json()
    assert _warned_flags(resp.get_json()) == ["--gpu-mem"], resp.get_json()


def test_create_with_known_flags_carries_no_warnings_key(api):
    resp = api.post("/api/services",
                    json=_vllm_cfg(params={"--max-model-len": "4096"}),
                    headers=_headers())
    assert resp.status_code == 201
    assert "warnings" not in resp.get_json()


def test_create_with_env_key_does_not_warn(api):
    resp = api.post("/api/services",
                    json=_vllm_cfg(params={"env:VLLM_PLE_CPU_OFFLOAD": "1"}),
                    headers=_headers())
    assert resp.status_code == 201
    assert "warnings" not in resp.get_json()


def test_create_with_removed_flag_warns(api):
    resp = api.post("/api/services",
                    json=_vllm_cfg(params={"--swap-space": "4"}),
                    headers=_headers())
    assert resp.status_code == 201, resp.get_json()
    assert _warned_flags(resp.get_json()) == ["--swap-space"]


# -- update (PUT) ----------------------------------------------------------


def test_put_warns_on_a_newly_added_typo(api):
    assert api.post("/api/services", json=_llamacpp_cfg(), headers=_headers()).status_code == 201
    resp = api.put("/api/services/llamacpp-surf-llama",
                   json=_llamacpp_cfg(params={"-ngl": "99", "--ngl": "99"}),
                   headers=_headers())
    assert resp.status_code == 200, resp.get_json()
    # -ngl is the real short form (in the surface); --ngl is a typo (the long
    # form is --n-gpu-layers), and the substring '-ngl' inside '--ngl' must not
    # count as the short form being warned about.
    assert _warned_flags(resp.get_json()) == ["--ngl"], resp.get_json()


def test_put_without_params_does_not_warn(api):
    assert api.post("/api/services", json=_llamacpp_cfg(), headers=_headers()).status_code == 201
    resp = api.put("/api/services/llamacpp-surf-llama",
                   json={"port": 3353, "alias": "surf-llama", "api_key": "k",
                         "model_path": "/models/m.gguf", "template_type": "llamacpp"},
                   headers=_headers())
    assert resp.status_code == 200
    assert "warnings" not in resp.get_json()


def test_put_warns_on_a_typo_stored_before_the_check(api):
    # A typo stored on create keeps surfacing on the next touch (merge semantics),
    # so an old bad flag is not only warned about once.
    assert api.post("/api/services",
                    json=_vllm_cfg(params={"--gpu-mem": "1"}), headers=_headers()
                    ).status_code == 201
    resp = api.put("/api/services/vllm-surf-vllm",
                   json={"port": 3354, "alias": "surf-vllm", "api_key": "k",
                         "model_name": "org/model", "template_type": "vllm"},
                   headers=_headers())
    assert resp.status_code == 200, resp.get_json()
    assert _warned_flags(resp.get_json()) == ["--gpu-mem"]
