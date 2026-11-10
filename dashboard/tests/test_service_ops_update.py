import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from port_conflicts import PortOwner
from service_ops import update
from service_ops.deps import Infra
from service_ops.errors import ErrorKind, OpError, service_not_found
from service_ops.hooks import Cause, ServiceHook
from service_ops.subsystems import InspectorHook, KeyFileHook
from service_ops.update import PortInUse, Updated, UpdateDeps, ValidationFailed

OLD, NEW = "llm-dock-llamacpp", "custom:1"


def _svc(port=3302, **extra):
    config = {
        "template_type": "llamacpp", "alias": "a", "port": port, "api_key": "k",
        "model_path": "/m.gguf", "params": {},
    }
    config.update(extra)
    return config


class Container:
    def __init__(self, status, image=OLD):
        self.status = status
        self.attrs = {"Config": {"Image": image}}


class Harness:
    def __init__(self):
        self.log = []
        self.fail = {}
        self.services = {"a": _svc(favorite=True, inspect_upstream_port=34005), "b": _svc(3303)}
        self.container = None
        self.recreate_result = {"restarted": False}
        self.settles = True
        self.missing_image = False
        self.hooks = None

    def step(self, name, *args, result=None):
        self.log.append((name, *args))
        if name in self.fail:
            raise self.fail[name]
        return result

    def names(self):
        return [entry[0] for entry in self.log]

    def deps(self):
        harness = self

        class Compose:
            def get_service_from_db(self, name):
                found = harness.services.get(name)
                return dict(found) if found else None

            def list_services_in_db(self):
                return harness.services

            def get_used_ports(self):
                return set()

            def update_service_in_db(self, name, config):
                harness.step("db_update", name)
                harness.services[name] = dict(config)

            def rebuild_compose_file(self):
                harness.step("rebuild")

        def recreate(name, status, finish):
            harness.step("recreate", name, status)
            if harness.settles:
                finish()
            return harness.recreate_result

        hooks = harness.hooks if harness.hooks is not None else [
            InspectorHook(lambda old, new: None, lambda: harness.step("sync")),
            KeyFileHook(lambda name: harness.step("key_removed", name)),
        ]
        infra = Infra(
            compose=lambda: Compose(),
            get_container=lambda name: harness.container,
            remove_container=lambda name: None,
            emit=lambda event: harness.step("emit", event),
            now=lambda: 42.0,
            hooks=hooks,
        )
        return UpdateDeps(
            infra,
            image_presence_warnings=lambda image: [f"missing {image}"] if harness.missing_image else [],
            recreate_for_image=recreate,
            reported_image=lambda container_image, configured: container_image or configured,
        )


def _metadata(harness):
    return harness.log[-1][1]["metadata"]


def test_an_unknown_service_is_not_found_and_touches_nothing():
    harness = Harness()

    assert update(harness.deps(), "ghost", _svc()) == service_not_found("ghost")
    assert harness.log == []


def test_the_engine_cannot_change():
    harness = Harness()

    outcome = update(harness.deps(), "a", _svc(template_type="vllm"))

    assert outcome == OpError(ErrorKind.INVALID, "Cannot change template_type of existing service")
    assert harness.log == []


def test_an_invalid_config_is_reported_with_its_details():
    harness = Harness()

    outcome = update(harness.deps(), "a", _svc(reasoning_levels="Not Valid!"))

    assert isinstance(outcome, ValidationFailed) and outcome.details
    assert harness.log == []


def test_a_port_another_service_holds_is_refused_with_its_owner():
    harness = Harness()

    outcome = update(harness.deps(), "a", _svc(3303))

    assert outcome == PortInUse(3303, PortOwner("b", "port"))
    assert harness.log == []


def test_an_unchanged_image_writes_rebuilds_reconciles_then_emits():
    harness = Harness()

    outcome = update(harness.deps(), "a", _svc(reasoning_levels="off,low"))

    assert harness.names() == ["db_update", "rebuild", "sync", "emit"]
    assert outcome == Updated("a", OLD)
    assert harness.log[-1] == ("emit", {
        "service_name": "a", "action": "metadata-changed", "status": None, "container_id": None,
        "metadata": {"reasoning_levels": [{"id": "off", "effort": "off"}, {"id": "low", "effort": "low"}]},
        "timestamp": 42.0,
    })


def test_the_merge_keeps_unsent_fields_and_drops_a_client_upstream_port():
    harness = Harness()

    update(harness.deps(), "a", {"port": 3302, "alias": "a", "api_key": "k2", "model_path": "/m.gguf",
                                 "inspect_upstream_port": 1})

    stored = harness.services["a"]
    assert (stored["favorite"], stored["inspect_upstream_port"], stored["api_key"]) == (True, 34005, "k2")


def test_the_hooks_see_the_update_cause_and_only_those_that_follow_it_run():
    harness = Harness()
    seen = []

    class Recording(ServiceHook):
        def after_container_swap(self, ctx):
            seen.append((ctx.subject, ctx.cause, list(ctx.affected)))

    harness.hooks = [Recording(), KeyFileHook(lambda name: harness.step("key_removed", name))]

    update(harness.deps(), "a", _svc())

    assert seen == [("a", Cause.UPDATE, ["a"])]
    assert "key_removed" not in harness.names()


def test_unknown_flags_warn_over_the_merged_params():
    harness = Harness()
    harness.services["a"]["params"] = {"--definitely-not-a-flag": "1"}

    outcome = update(harness.deps(), "a", {"port": 3302, "alias": "a", "api_key": "k", "model_path": "/m.gguf"})

    assert len(outcome.warnings) == 1 and "--definitely-not-a-flag" in outcome.warnings[0]


@pytest.mark.parametrize(
    "container,result,restarted,error,reported",
    [
        (Container("running"), {"restarted": True}, True, None, NEW),
        (Container("running"), {"restarted": False, "error": "pull denied"}, False, "pull denied", OLD),
        (Container("exited"), {"restarted": False}, False, None, OLD),
        (None, {"restarted": False}, False, None, NEW),
    ],
    ids=["running-ok", "running-failed", "stopped-keeps-old", "no-container"],
)
def test_a_changed_image_recreates_and_reports_what_the_payload_will(container, result, restarted, error, reported):
    harness = Harness()
    harness.container = container
    harness.recreate_result = result

    outcome = update(harness.deps(), "a", _svc(image=NEW))

    status = container.status if container else "not-created"
    assert harness.log[:3] == [("db_update", "a"), ("recreate", "a", status), ("sync",)]
    assert "rebuild" not in harness.names()
    assert outcome == Updated("a", NEW, restarted, error)
    assert _metadata(harness)["image"] == reported


def test_a_recreate_that_never_settles_is_not_reconciled():
    harness = Harness()
    harness.container = Container("running")
    harness.settles = False
    harness.recreate_result = {"restarted": False, "error": "port taken"}

    outcome = update(harness.deps(), "a", _svc(image=NEW))

    assert harness.names() == ["db_update", "recreate", "emit"]
    assert outcome.recreate_error == "port taken"


def test_the_image_warning_is_added_only_when_the_image_changed():
    harness = Harness()
    harness.missing_image = True

    assert update(harness.deps(), "a", _svc()).warnings == []
    assert update(harness.deps(), "a", _svc(image=NEW)).warnings == [f"missing {NEW}"]


@pytest.mark.parametrize("step", ["db_update", "rebuild", "sync"])
def test_a_failing_step_propagates_and_nothing_is_emitted(step):
    harness = Harness()
    harness.fail[step] = RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        update(harness.deps(), "a", _svc())

    assert harness.names()[-1] == step


def test_a_raising_recreate_propagates_without_an_event():
    harness = Harness()
    harness.fail["recreate"] = ValueError("compose invalid")

    with pytest.raises(ValueError, match="compose invalid"):
        update(harness.deps(), "a", _svc(image=NEW))

    assert harness.names() == ["db_update", "recreate"]
