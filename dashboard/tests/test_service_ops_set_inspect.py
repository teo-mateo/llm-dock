import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from service_ops import set_inspect
from service_ops.deps import Infra, SetInspectDeps
from service_ops.hooks import Cause, ServiceHook
from service_ops.outcomes import InspectSet, OpError
from service_ops.subsystems import InspectorHook


class Harness:
    def __init__(self, services=None):
        self.log = []
        self.fail = {}
        self.services = services if services is not None else {
            "off": {"port": 3302},
            "on": {"port": 3303, "inspect": True, "inspect_upstream_port": 34007},
        }
        self.restarted = False
        self.status = []
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
                return harness.services.get(name)

            def list_services_in_db(self):
                return harness.services

            def update_service_in_db(self, name, config):
                harness.step("db_update", name, config.get("inspect"), config.get("inspect_upstream_port"))

            def rebuild_compose_file(self):
                harness.step("rebuild")

        hooks = harness.hooks if harness.hooks is not None else [
            InspectorHook(lambda old, new: None, lambda: harness.step("sync"))
        ]
        infra = Infra(
            compose=lambda: Compose(),
            get_container=lambda name: None,
            remove_container=lambda name: None,
            emit=lambda event: harness.step("emit", event),
            now=lambda: 42.0,
            hooks=hooks,
        )
        return SetInspectDeps(
            infra,
            allocate_upstream_port=lambda services, name: harness.step("allocate", name, result=34000),
            recreate_if_running=lambda name: harness.step(
                "recreate", name, result={"restarted": harness.restarted}
            ),
            proxy_status=lambda: harness.status,
        )


def test_an_unknown_service_is_a_404_and_touches_nothing():
    harness = Harness()

    assert set_inspect(harness.deps(), "ghost", True) == OpError(404, 'Service "ghost" not found')
    assert harness.log == []


def test_enabling_allocates_writes_rebuilds_recreates_then_reconciles():
    harness = Harness()
    harness.restarted = True
    harness.status = [{"service": "off", "running": True, "error": None}]

    outcome = set_inspect(harness.deps(), "off", True)

    assert harness.names() == ["allocate", "db_update", "rebuild", "recreate", "sync", "emit"]
    assert harness.log[1] == ("db_update", "off", True, 34000)
    assert outcome == InspectSet("off", True, 3302, 34000, True, True, None)


def test_disabling_reconciles_before_the_container_takes_the_port_back():
    harness = Harness()

    outcome = set_inspect(harness.deps(), "on", False)

    assert harness.names() == ["db_update", "sync", "rebuild", "recreate", "emit"]
    assert harness.log[0] == ("db_update", "on", False, 34007)
    assert outcome == InspectSet("on", False, 3303, 34007, False, False, None)


def test_the_hooks_see_the_inspect_cause_and_the_service():
    harness = Harness()
    seen = []

    class Recording(ServiceHook):
        def after_container_swap(self, ctx):
            seen.append(("after", ctx.subject, ctx.cause, list(ctx.affected)))

        def before_container_swap(self, ctx):
            seen.append(("before", ctx.subject, ctx.cause, list(ctx.affected)))

    harness.hooks = [Recording()]

    set_inspect(harness.deps(), "off", True)
    set_inspect(harness.deps(), "on", False)

    assert seen == [
        ("after", "off", Cause.INSPECT, ["off"]),
        ("before", "on", Cause.INSPECT, ["on"]),
    ]


@pytest.mark.parametrize("name,enabled", [("on", True), ("off", False)])
def test_a_toggle_to_the_current_state_only_emits(name, enabled):
    harness = Harness()

    outcome = set_inspect(harness.deps(), name, enabled)

    assert harness.names() == ["emit"]
    assert outcome.restarted is False


def test_the_event_carries_the_new_state_and_the_injected_time():
    harness = Harness()

    set_inspect(harness.deps(), "off", True)

    assert harness.log[-1] == ("emit", {
        "service_name": "off", "action": "metadata-changed", "status": None,
        "container_id": None, "metadata": {"inspect": True}, "timestamp": 42.0,
    })


def test_a_status_row_for_another_service_does_not_count():
    harness = Harness()
    harness.status = [{"service": "other", "running": True, "error": "x"}]

    outcome = set_inspect(harness.deps(), "off", True)

    assert (outcome.proxy_running, outcome.error) == (False, None)


def test_a_bind_error_is_reported_in_the_outcome_not_raised():
    harness = Harness()
    harness.status = [{"service": "off", "running": False, "error": "address in use"}]

    outcome = set_inspect(harness.deps(), "off", True)

    assert (outcome.proxy_running, outcome.error) == (False, "address in use")


@pytest.mark.parametrize("step", ["db_update", "rebuild", "recreate", "sync"])
def test_a_failing_step_propagates_and_nothing_after_it_runs(step):
    harness = Harness()
    harness.fail[step] = RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        set_inspect(harness.deps(), "off", True)

    assert harness.names()[-1] == step and "emit" not in harness.names()


def test_a_best_effort_hook_failure_does_not_stop_the_toggle():
    harness = Harness()

    class Flaky(ServiceHook):
        def after_container_swap(self, ctx):
            raise RuntimeError("flaky")

    harness.hooks = [Flaky()]

    outcome = set_inspect(harness.deps(), "off", True)

    assert outcome.enabled is True and harness.names()[-1] == "emit"


def test_the_outcome_body_is_the_wire_shape():
    assert InspectSet("s", True, 1, 2, False, True, None).body() == {
        "service": "s", "enabled": True, "port": 1, "upstream_port": 2,
        "proxy_running": False, "restarted": True, "error": None,
    }
