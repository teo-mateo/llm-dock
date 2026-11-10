import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from port_conflicts import PortOwner
from service_ops import create
from service_ops.config_checks import PortInUse, ValidationFailed, port_conflict, unknown_flag_warnings, validate
from service_ops.create import Created, CreateDeps
from service_ops.deps import Infra
from service_ops.errors import ErrorKind, OpError


def _body(port=3305, **extra):
    body = {
        "template_type": "llamacpp", "alias": "new", "port": port, "api_key": "k",
        "model_path": "/m.gguf", "params": {},
    }
    body.update(extra)
    return body


class Harness:
    def __init__(self):
        self.log = []
        self.fail = {}
        self.services = {"llamacpp-old": {**_body(3302), "alias": "old", "inspect_upstream_port": 34001}}
        self.missing_image = False

    def step(self, name, *args, result=None):
        self.log.append((name, *args))
        if name in self.fail:
            raise self.fail[name]
        return result

    def names(self):
        return [entry[0] for entry in self.log]

    def compose(self):
        harness = self

        class Compose:
            def get_service_from_db(self, name):
                return harness.services.get(name)

            def list_services_in_db(self):
                return harness.services

            def get_used_ports(self):
                return {3300}

            def add_service_to_db(self, name, config):
                harness.step("db_add", name)
                harness.services[name] = dict(config)

            def rebuild_compose_file(self):
                harness.step("rebuild")

        return Compose()

    def deps(self):
        infra = Infra(
            compose=self.compose,
            get_container=lambda name: None,
            remove_container=lambda name: None,
            emit=lambda event: self.step("emit", event),
            now=lambda: 0.0,
            hooks=[],
        )
        return CreateDeps(
            infra,
            generate_key=lambda: "key-generated",
            image_presence_warnings=lambda image: [f"missing {image}"] if image and self.missing_image else [],
        )


def test_a_missing_engine_is_refused():
    harness = Harness()
    body = _body()
    del body["template_type"]

    assert create(harness.deps(), body) == OpError(ErrorKind.INVALID, "template_type is required")
    assert harness.log == []


def test_an_unknown_engine_is_refused():
    outcome = create(Harness().deps(), _body(template_type="nope"))

    assert isinstance(outcome, OpError) and outcome.kind is ErrorKind.INVALID and "llamacpp" in outcome.message


def test_an_invalid_config_is_reported_with_its_details():
    harness = Harness()

    outcome = create(harness.deps(), _body(reasoning_levels="Not Valid!"))

    assert isinstance(outcome, ValidationFailed) and outcome.details
    assert harness.log == []


def test_an_existing_name_is_a_conflict_checked_before_the_port():
    harness = Harness()

    outcome = create(harness.deps(), _body(3302, alias="old"))

    assert outcome == OpError(ErrorKind.CONFLICT, 'Service "llamacpp-old" already exists')
    assert harness.log == []


def test_a_claimed_port_is_refused_with_its_owner():
    harness = Harness()

    assert create(harness.deps(), _body(3302)) == PortInUse(3302, PortOwner("llamacpp-old", "port"))
    assert isinstance(create(harness.deps(), _body(34001)), PortInUse)
    assert isinstance(create(harness.deps(), _body(3300)), PortInUse)
    assert harness.log == []


def test_a_valid_service_is_stored_then_the_compose_file_rebuilt_and_nothing_emitted():
    harness = Harness()

    outcome = create(harness.deps(), _body(favorite=True))

    assert harness.log == [("db_add", "llamacpp-new"), ("rebuild",)]
    assert outcome == Created("llamacpp-new", 3305, "k", "llm-dock-llamacpp")
    assert harness.services["llamacpp-new"] == _body(favorite=True)


@pytest.mark.parametrize("key", [None, ""])
def test_a_missing_or_empty_key_is_generated(key):
    harness = Harness()
    body = _body()
    if key is None:
        del body["api_key"]
    else:
        body["api_key"] = key

    outcome = create(harness.deps(), body)

    assert outcome.api_key == "key-generated"
    assert harness.services["llamacpp-new"]["api_key"] == "key-generated"


def test_a_client_upstream_port_is_dropped():
    harness = Harness()

    create(harness.deps(), _body(inspect_upstream_port=34999))

    assert "inspect_upstream_port" not in harness.services["llamacpp-new"]


def test_a_string_port_becomes_an_int_in_the_outcome():
    assert create(Harness().deps(), _body("3306")).port == 3306


def test_flag_warnings_come_before_the_image_warning():
    harness = Harness()
    harness.missing_image = True

    outcome = create(harness.deps(), _body(image="custom:1", params={"--definitely-not-a-flag": "1"}))

    assert outcome.configured_image == "custom:1"
    assert len(outcome.warnings) == 2 and outcome.warnings[1] == "missing custom:1"
    assert "--definitely-not-a-flag" in outcome.warnings[0]


@pytest.mark.parametrize("step,reached", [("db_add", ["db_add"]), ("rebuild", ["db_add", "rebuild"])])
def test_a_failing_step_propagates(step, reached):
    harness = Harness()
    harness.fail[step] = RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        create(harness.deps(), _body())

    assert harness.names() == reached


def test_the_shared_checks_answer_none_when_there_is_nothing_to_refuse():
    compose = Harness().compose()

    assert validate("llamacpp", _body()) is None
    assert port_conflict(compose, 3305) is None
    assert port_conflict(compose, 3302, exclude="llamacpp-old") is None
    assert unknown_flag_warnings("llamacpp", {}) == []
