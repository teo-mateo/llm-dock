"""Pins what POST /api/services does today: status codes, bodies, what is
stored and the order of its side effects. Nothing here may change when the
operation moves out of the route module."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import docker_utils
import routes.services as services_route
from compose_manager import ComposeManager
from inspector.supervisor import proxy_supervisor
from services import event_manager

TOKEN = "test-token-create"


def _body(port=3305, **extra):
    body = {
        "template_type": "llamacpp", "alias": "new", "port": port, "api_key": "k",
        "model_path": "/m.gguf", "params": {},
    }
    body.update(extra)
    return body


class Seams:
    def __init__(self):
        self.log = []
        self.fail = {}
        self.image_exists = True

    def step(self, name, *args, result=None):
        self.log.append((name, *args))
        if name in self.fail:
            raise self.fail[name]
        return result

    def names(self):
        return [entry[0] for entry in self.log]


def patch_key_generator(monkeypatch):
    """The one place that knows where create gets a generated key from."""
    monkeypatch.setattr(services_route, "generate_api_key", lambda: "key-generated")


@pytest.fixture
def seams(tmp_path, monkeypatch):
    seams = Seams()
    monkeypatch.setenv("DASHBOARD_TOKEN", TOKEN)
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services: {}\n")
    seams.services_path = tmp_path / "services.json"
    seams.services_path.write_text(json.dumps({
        "llamacpp-old": {**_body(3302), "alias": "old", "inspect_upstream_port": 34001},
    }))
    monkeypatch.setattr(services_route, "COMPOSE_FILE", str(compose))
    patch_key_generator(monkeypatch)

    real_add = ComposeManager.add_service_to_db

    def add(self, name, config):
        seams.step("db_add", name)
        return real_add(self, name, config)

    monkeypatch.setattr(ComposeManager, "add_service_to_db", add)
    monkeypatch.setattr(ComposeManager, "rebuild_compose_file", lambda self: seams.step("rebuild"))
    monkeypatch.setattr(ComposeManager, "get_used_ports", lambda self: {3300})
    monkeypatch.setattr(proxy_supervisor, "sync", lambda: seams.step("sync"))
    monkeypatch.setattr(event_manager, "emit", lambda event: seams.step("emit", event))
    monkeypatch.setattr(docker_utils, "get_image_info", lambda n: {"exists": seams.image_exists})

    from app import create_app

    seams.client = create_app(config={"TESTING": True, "DASHBOARD_TOKEN": TOKEN}).test_client()
    seams.log.clear()
    return seams


def _post(seams, body):
    return seams.client.post("/api/services", json=body, headers={"Authorization": f"Bearer {TOKEN}"})


def _stored(seams):
    return json.loads(seams.services_path.read_text())


def test_an_empty_body_is_a_400(seams):
    response = _post(seams, {})

    assert (response.status_code, response.get_json()) == (400, {"error": "Request body is required"})
    assert seams.log == []


def test_a_missing_engine_is_a_400(seams):
    body = _body()
    del body["template_type"]

    response = _post(seams, body)

    assert (response.status_code, response.get_json()) == (400, {"error": "template_type is required"})


def test_an_unknown_engine_is_a_400_that_lists_the_engines(seams):
    response = _post(seams, _body(template_type="nope"))

    assert response.status_code == 400
    assert "llamacpp" in response.get_json()["error"]
    assert seams.log == []


def test_an_invalid_config_is_a_400_with_details(seams):
    response = _post(seams, _body(reasoning_levels="Not Valid!"))

    body = response.get_json()
    assert response.status_code == 400
    assert body["error"] == "Validation failed" and body["details"]
    assert seams.log == []


def test_an_existing_name_is_a_409(seams):
    response = _post(seams, _body(alias="old"))

    assert (response.status_code, response.get_json()) == (409, {"error": 'Service "llamacpp-old" already exists'})
    assert seams.log == []


def test_an_existing_name_wins_over_a_port_conflict(seams):
    assert _post(seams, _body(3302, alias="old")).status_code == 409


@pytest.mark.parametrize("port", [3302, 34001, 3300])
def test_a_port_already_claimed_is_a_400_with_the_conflict_code(seams, port):
    response = _post(seams, _body(port))

    body = response.get_json()
    assert (response.status_code, body["code"]) == (400, "port_in_use")
    assert seams.log == []


def test_a_valid_service_is_stored_and_the_compose_file_rebuilt_without_events(seams):
    response = _post(seams, _body(favorite=True))

    assert response.status_code == 201
    assert response.get_json() == {
        "success": True, "service_name": "llamacpp-new", "port": 3305, "api_key": "k",
        "configured_image": "llm-dock-llamacpp",
        "message": 'Service "llamacpp-new" created successfully',
    }
    assert seams.log == [("db_add", "llamacpp-new"), ("rebuild",)]
    assert _stored(seams)["llamacpp-new"] == _body(favorite=True)


def test_a_missing_key_is_generated_and_returned(seams):
    body = _body()
    del body["api_key"]

    response = _post(seams, body)

    assert response.get_json()["api_key"] == "key-generated"
    assert _stored(seams)["llamacpp-new"]["api_key"] == "key-generated"


def test_an_empty_key_counts_as_missing(seams):
    assert _post(seams, _body(api_key="")).get_json()["api_key"] == "key-generated"


def test_the_body_cannot_set_the_inspector_upstream_port(seams):
    _post(seams, _body(inspect_upstream_port=34999))

    assert "inspect_upstream_port" not in _stored(seams)["llamacpp-new"]


def test_a_string_port_is_reported_as_an_int(seams):
    response = _post(seams, _body("3306"))

    assert (response.status_code, response.get_json()["port"]) == (201, 3306)


def test_an_unknown_flag_warns_but_the_service_is_created(seams):
    response = _post(seams, _body(params={"--definitely-not-a-flag": "1"}))

    body = response.get_json()
    assert response.status_code == 201
    assert len(body["warnings"]) == 1 and "--definitely-not-a-flag" in body["warnings"][0]


def test_a_missing_image_warns_after_the_flag_warnings(seams):
    seams.image_exists = False

    body = _post(seams, _body(image="custom:1", params={"--definitely-not-a-flag": "1"})).get_json()

    assert body["configured_image"] == "custom:1"
    assert len(body["warnings"]) == 2
    assert body["warnings"][1] == (
        "Image 'custom:1' is not present locally; it will be pulled when the container starts"
    )


def test_no_image_override_means_no_image_lookup(seams):
    seams.image_exists = False

    assert "warnings" not in _post(seams, _body()).get_json()


def test_a_failing_db_write_is_a_500_before_any_rebuild(seams):
    seams.fail["db_add"] = RuntimeError("disk full")

    response = _post(seams, _body())

    assert (response.status_code, response.get_json()) == (500, {"error": "disk full"})
    assert seams.names() == ["db_add"]


def test_a_failing_rebuild_is_a_500_and_the_entry_stays_stored(seams):
    seams.fail["rebuild"] = RuntimeError("compose invalid")

    response = _post(seams, _body())

    assert (response.status_code, response.get_json()) == (500, {"error": "compose invalid"})
    assert "llamacpp-new" in _stored(seams)
