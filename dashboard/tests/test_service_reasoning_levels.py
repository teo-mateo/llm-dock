"""Config-write validation and payload exposure for `reasoning_levels` (R1-R3).

Two layers here: validate_service_config owns rejection on every write path,
and get_docker_services owns exposure (which feeds GET /api/services, the SSE
snapshot and therefore the chat picker). The compose round trip proves the key
survives being stored, and the PUT cases prove that clearing works without the
merge eating an unrelated field.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flag_metadata import validate_service_config
import reasoning_levels as rl

TEST_TOKEN = "test-token-rl"


def _llamacpp_cfg(**extra):
    cfg = {
        "port": 3345,
        "model_path": "/models/qwen3.8-27b-q4.gguf",
        "alias": "llamacpp-qwen38",
        "api_key": "k",
        "template_type": "llamacpp",
        "params": {"-ngl": "99"},
    }
    cfg.update(extra)
    return cfg


def _vllm_cfg(**extra):
    cfg = {"port": 3346, "model_name": "Qwen/Qwen3.8-27B", "alias": "qwen38",
           "api_key": "k", "template_type": "vllm", "params": {}}
    cfg.update(extra)
    return cfg


# -- validate_service_config ---------------------------------------------


@pytest.mark.parametrize("raw", ["off", "off,low,medium,xhigh", "off, low, medium"])
def test_valid_declaration_accepted_by_every_template(raw):
    for template_type, cfg in (("llamacpp", _llamacpp_cfg()), ("vllm", _vllm_cfg()),
                              ("tabbyapi", _llamacpp_cfg(model_path="/exl3/foo"))):
        cfg["reasoning_levels"] = raw
        valid, errors = validate_service_config(template_type, cfg)
        assert valid, (template_type, raw, errors)


def test_absent_declaration_is_valid():
    valid, errors = validate_service_config("llamacpp", _llamacpp_cfg())
    assert valid and errors == []


def test_empty_declaration_is_a_valid_clear():
    valid, errors = validate_service_config("llamacpp", _llamacpp_cfg(reasoning_levels=""))
    assert valid and errors == []


def test_malformed_declaration_is_rejected_naming_the_field():
    valid, errors = validate_service_config("llamacpp", _llamacpp_cfg(reasoning_levels="low:512"))
    assert not valid
    assert any("reasoning_levels" in e for e in errors)
    assert any("budget" in e for e in errors)


def test_one_violation_produces_exactly_one_error():
    """One bad declaration, one error — a duplicate used to double the details."""
    for raw in ("low:512", "Ultra", "a,b,c,d,e,f,g,h,i"):
        valid, errors = validate_service_config("llamacpp", _llamacpp_cfg(reasoning_levels=raw))
        assert not valid, raw
        level_errors = [e for e in errors if "reasoning_levels" in e]
        assert len(level_errors) == 1, (raw, errors)


def test_bogus_declaration_is_rejected_for_vllm_too():
    valid, errors = validate_service_config("vllm", _vllm_cfg(reasoning_levels="Ultra"))
    assert not valid
    assert any("reasoning_levels" in e for e in errors)


def test_a_bad_declaration_does_not_hide_other_errors():
    cfg = _llamacpp_cfg(port=99, reasoning_levels="low:512", params={"nope": "x"})
    valid, errors = validate_service_config("llamacpp", cfg)
    assert not valid
    assert any("port" in e.lower() for e in errors)
    assert any("reasoning_levels" in e for e in errors)


# -- storage round trip ---------------------------------------------------


def test_declaration_survives_a_compose_manager_round_trip(tmp_path):
    from compose_manager import ComposeManager

    compose_path = tmp_path / "docker-compose.yml"
    compose_path.write_text(
        "services:\n  # <<<<<<< BEGIN DYNAMIC\n  # >>>>>>> END DYNAMIC\n\n"
        "networks:\n  llm-network:\n    driver: bridge\n"
    )
    services_path = tmp_path / "services.json"
    services_path.write_text("{}")

    mgr = ComposeManager(str(compose_path), str(services_path))
    mgr.add_service_to_db("llamacpp-qwen38", _llamacpp_cfg(reasoning_levels="off,low,medium,xhigh"))
    mgr.rebuild_compose_file()

    stored = mgr.get_service_from_db("llamacpp-qwen38")
    assert stored["reasoning_levels"] == "off,low,medium,xhigh"
    # Chat-side metadata, not a container flag.
    assert "reasoning" not in compose_path.read_text()


# -- exposure on the service payload -------------------------------------


class _FakeComposeMgr:
    """Stand-in for ComposeManager reading entries straight from a dict."""

    def __init__(self, entries):
        self._entries = entries

    def get_service_from_db(self, name):
        return self._entries.get(name)


class _FakeContainer:
    """One running container, so the container-exists branch is exercised too."""

    def __init__(self, service_name):
        self.labels = {"com.docker.compose.service": service_name}
        self.status = "running"
        self.id = "deadbeefcafe"
        self.attrs = {"Created": "2026-01-01T00:00:00Z", "State": {"ExitCode": 0}}
        self.ports = {"8000/tcp": [{"HostPort": "3301"}]}


class _FakeContainerList:
    def __init__(self, containers):
        self._containers = containers

    def list(self, **kwargs):
        return list(self._containers)


class _FakeClient:
    def __init__(self, containers=None):
        self.containers = _FakeContainerList(containers or [])


def _payload_for(monkeypatch, entries, names, running=None):
    """Build the get_docker_services payload with no Docker and no files.

    `running` names get a container, so both payload branches can be read.
    """
    import docker
    import docker_utils

    monkeypatch.setattr(docker, "from_env",
                        lambda: _FakeClient([_FakeContainer(n) for n in (running or [])]))
    monkeypatch.setattr(docker_utils, "get_compose_services", lambda: names)
    monkeypatch.setattr(docker_utils, "get_compose_service_ports",
                        lambda: {n: 3300 + i for i, n in enumerate(names)})
    monkeypatch.setattr(docker_utils, "get_openwebui_registered_urls", lambda: [])
    monkeypatch.setattr(docker_utils, "compute_model_size", lambda *a, **k: (None, None))
    monkeypatch.setattr(docker_utils, "ComposeManager", lambda *a, **k: _FakeComposeMgr(entries))
    return {s["name"]: s for s in docker_utils.get_docker_services()}


def test_payload_carries_parsed_levels_in_both_branches(monkeypatch):
    entries = {
        "vllm-a": {"api_key": "k", "template_type": "vllm", "reasoning_levels": "off,low,medium"},
        "llamacpp-b": {"api_key": "k", "template_type": "llamacpp"},
    }
    services = _payload_for(monkeypatch, entries, ["vllm-a", "llamacpp-b"])
    assert services["vllm-a"]["reasoning_levels"] == [
        {"id": "off", "effort": "off"},
        {"id": "low", "effort": "low"},
        {"id": "medium", "effort": "medium"},
    ]
    assert services["llamacpp-b"]["reasoning_levels"] == []
    assert all(s["status"] == "not-created" for s in services.values())


def test_garbage_stored_value_degrades_to_empty_and_warns_once(monkeypatch, caplog):
    entries = {"vllm-a": {"api_key": "k", "template_type": "vllm", "reasoning_levels": "low:512"}}
    import docker_utils

    monkeypatch.setattr(docker_utils, "_level_warned", set())
    with caplog.at_level("WARNING"):
        services = _payload_for(monkeypatch, entries, ["vllm-a"])
        assert services["vllm-a"]["reasoning_levels"] == []
        assert any("vllm-a" in r.getMessage() and "reasoning_levels" in r.getMessage()
                   for r in caplog.records)
        # One read per request and per reconnect: warn once, not every time.
        caplog.clear()
        _payload_for(monkeypatch, entries, ["vllm-a"])
        _payload_for(monkeypatch, entries, ["vllm-a"])
        assert [r for r in caplog.records if "reasoning_levels" in r.getMessage()] == []


def test_resolve_service_exposes_engine_and_levels(monkeypatch):
    from chat import llm_proxy

    def _fake_services():
        return [{
            "name": "vllm-a", "status": "running", "host_port": 3301, "api_key": "k",
            "template_type": "vllm", "reasoning_levels": [{"id": "low", "effort": "low"}],
        }]

    import docker_utils
    monkeypatch.setattr(docker_utils, "get_docker_services", _fake_services)
    svc = llm_proxy.resolve_service("vllm-a")
    assert svc["template_type"] == "vllm"
    assert svc["reasoning_levels"] == [{"id": "low", "effort": "low"}]


# -- through the config API (R2) -----------------------------------------


COMPOSE_TEMPLATE = """services:
  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: open-webui
    restart: unless-stopped
    ports:
      - "3300:8080"
    volumes:
      - open-webui-data:/app/backend/data
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
    """Client whose compose/services paths point at a throwaway directory.

    ComposeManager derives services.json from the compose file's parent, so
    patching the module global isolates both.
    """
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


def test_post_accepts_a_declared_ladder(api):
    import routes.services as services_routes

    resp = api.post("/api/services",
                    json=dict(_vllm_cfg(reasoning_levels="off,low,medium,xhigh")),
                    headers=_headers())
    assert resp.status_code == 201, resp.get_json()
    mgr = services_routes.ComposeManager(services_routes.COMPOSE_FILE)
    assert mgr.get_service_from_db("vllm-qwen38")["reasoning_levels"] == "off,low,medium,xhigh"


@pytest.mark.parametrize("bad", ["low:512", "Ultra", "off,off", ",,"])
def test_post_rejects_malformed_and_stores_nothing(api, bad):
    import routes.services as services_routes

    resp = api.post("/api/services", json=dict(_vllm_cfg(reasoning_levels=bad)), headers=_headers())
    assert resp.status_code == 400, resp.get_json()
    body = resp.get_json()
    assert body["error"] == "Validation failed"
    assert any("reasoning_levels" in d for d in body["details"])
    assert services_routes.ComposeManager(services_routes.COMPOSE_FILE) \
        .get_service_from_db("vllm-qwen38") is None


def test_put_omitting_the_key_keeps_it_and_empty_string_clears(api):
    import routes.services as services_routes

    # PUT validates the whole body, so these send complete configs; only
    # reasoning_levels varies.
    assert api.post("/api/services", json=_vllm_cfg(reasoning_levels="off,low", favorite=True),
                    headers=_headers()).status_code == 201
    mgr = services_routes.ComposeManager(services_routes.COMPOSE_FILE)

    resp = api.put("/api/services/vllm-qwen38", json=_vllm_cfg(), headers=_headers())
    assert resp.status_code == 200, resp.get_json()
    assert mgr.get_service_from_db("vllm-qwen38")["reasoning_levels"] == "off,low"
    assert mgr.get_service_from_db("vllm-qwen38")["favorite"] is True

    resp = api.put("/api/services/vllm-qwen38", json=_vllm_cfg(reasoning_levels=""),
                   headers=_headers())
    assert resp.status_code == 200, resp.get_json()
    stored = mgr.get_service_from_db("vllm-qwen38")
    assert stored["reasoning_levels"] == ""
    # The merge preserves what the PUT body didn't mention.
    assert stored["favorite"] is True


def _captured_events(monkeypatch):
    """Collect what the routes broadcast on the services SSE stream."""
    import services as services_pkg

    events = []
    monkeypatch.setattr(services_pkg.event_manager, "emit", events.append)
    return events


def test_put_broadcasts_the_ladder_to_every_sse_consumer(api, monkeypatch):
    """A ladder edit must reach other consumers, not just this browser."""
    events = _captured_events(monkeypatch)
    assert api.post("/api/services", json=_vllm_cfg(reasoning_levels="off,low"),
                    headers=_headers()).status_code == 201
    events.clear()

    assert api.put("/api/services/vllm-qwen38", json=_vllm_cfg(reasoning_levels="off,low,xhigh"),
                   headers=_headers()).status_code == 200
    deltas = [e for e in events if e.get("action") == "metadata-changed"]
    assert len(deltas) == 1
    # Payload shape, not the raw string, so it merges into the snapshot copy.
    assert deltas[0]["metadata"]["reasoning_levels"] == [
        {"id": "off", "effort": "off"},
        {"id": "low", "effort": "low"},
        {"id": "xhigh", "effort": "xhigh"},
    ]
    # A metadata delta must not disturb the status a consumer already holds.
    assert deltas[0]["status"] is None


def test_put_broadcasts_an_empty_ladder_when_the_declaration_is_cleared(api, monkeypatch):
    events = _captured_events(monkeypatch)
    assert api.post("/api/services", json=_vllm_cfg(reasoning_levels="off,low"),
                    headers=_headers()).status_code == 201
    events.clear()

    assert api.put("/api/services/vllm-qwen38", json=_vllm_cfg(reasoning_levels=""),
                   headers=_headers()).status_code == 200
    deltas = [e for e in events if e.get("action") == "metadata-changed"]
    assert [d["metadata"]["reasoning_levels"] for d in deltas] == [[]]


def test_rejected_put_broadcasts_nothing(api, monkeypatch):
    events = _captured_events(monkeypatch)
    assert api.post("/api/services", json=_vllm_cfg(reasoning_levels="off,low"),
                    headers=_headers()).status_code == 201
    events.clear()

    assert api.put("/api/services/vllm-qwen38", json=_vllm_cfg(reasoning_levels="low:512"),
                   headers=_headers()).status_code == 400
    assert [e for e in events if e.get("action") == "metadata-changed"] == []


def test_put_rejects_malformed_without_touching_the_stored_value(api):
    import routes.services as services_routes

    assert api.post("/api/services", json=_vllm_cfg(reasoning_levels="off,low"),
                    headers=_headers()).status_code == 201
    resp = api.put("/api/services/vllm-qwen38", json=_vllm_cfg(reasoning_levels="low:512"),
                   headers=_headers())
    assert resp.status_code == 400
    assert any("reasoning_levels" in d for d in resp.get_json()["details"])
    mgr = services_routes.ComposeManager(services_routes.COMPOSE_FILE)
    assert mgr.get_service_from_db("vllm-qwen38")["reasoning_levels"] == "off,low"


def test_openrouter_resolution_carries_no_engine_fields(monkeypatch):
    # Exclusion by construction: no template_type means request_fields is never
    # reached with an engine, so no reasoning key can be added for OpenRouter.
    from chat import llm_proxy

    monkeypatch.setattr(llm_proxy, "resolve_service",
                        lambda name: {"base_url": "https://openrouter.ai/api/v1",
                                      "api_key": "k", "model": "x", "extra_headers": {}})
    svc = llm_proxy.resolve_service("openrouter:x")
    assert "template_type" not in svc
    assert "reasoning_levels" not in svc
    assert rl.request_fields(rl.find_level(svc.get("reasoning_levels"), "low"),
                            svc.get("template_type")) == {}


# -- the seam that actually broke (regression) ---------------------------


def test_engine_survives_the_real_payload_into_request_fields(monkeypatch):
    """Regression: template_type was never a payload field, so every declared
    level was dropped as an unmapped engine with nothing logged. Asserted against
    the payload the real builder produces — a hand-written dict carrying
    template_type hides this bug, and did.
    """
    entries = {"vllm-a": {"api_key": "k", "template_type": "vllm",
                         "reasoning_levels": "off,low,medium,xhigh"}}

    for running in (["vllm-a"], []):  # both payload branches
        svc = _payload_for(monkeypatch, entries, ["vllm-a"], running=running)["vllm-a"]
        assert svc["template_type"] == "vllm"
        # The exact expressions llm_proxy.stream_chat_completion uses.
        fields = rl.request_fields(rl.find_level(svc["reasoning_levels"], "off"),
                                   svc["template_type"])
        assert fields == {"reasoning_effort": "none"}
        assert rl.request_fields(rl.find_level(svc["reasoning_levels"], "medium"),
                                 svc["template_type"]) == {"reasoning_effort": "medium"}
