import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from service_ops import set_public_port
from service_ops.deps import Infra, SetPublicPortDeps
from service_ops.hooks import Phase, PublicPortContext, ServiceHook, run_phase
from service_ops.outcomes import AlreadyPublic, OpError, PublicPortSet
from service_ops.subsystems import InspectorHook

PUBLIC = 3301


class Harness:
    def __init__(self, services=None):
        self.log = []
        self.fail = {}
        self.services = services or {
            "a": {"port": 3302},
            "b": {"port": PUBLIC},
            "c": {"port": PUBLIC},
            "d": {"port": 3304},
        }
        self.free = iter(range(3310, 3320))
        self.restarts = {}

    def step(self, name, *args, result=None):
        self.log.append((name, *args))
        if name in self.fail:
            raise self.fail[name]
        return result

    def deps(self):
        harness = self

        class Compose:
            def get_service_from_db(self, name):
                return harness.services.get(name)

            def list_services_in_db(self):
                return harness.services

            def update_service_in_db(self, name, config):
                harness.step("db_update", name, config["port"])

            def get_used_ports(self):
                return {3300}

            def rebuild_compose_file(self):
                harness.step("rebuild")

        return SetPublicPortDeps(
            Infra(
                compose=lambda: Compose(),
                get_container=lambda name: None,
                remove_container=lambda name: None,
                emit=lambda event: harness.step("emit", event),
                now=lambda: 0.0,
                hooks=[InspectorHook(lambda o, n: None, lambda: harness.step("proxy_sync"))],
            ),
            next_free_port=lambda services, used: harness.step("next_free_port", sorted(used), result=next(harness.free)),
            recreate_if_running=lambda name: harness.step("recreate", name, result=harness.restarts.get(name, {"restarted": False})),
        )

    def names(self):
        return [entry[0] for entry in self.log]


def test_an_unknown_service_is_a_404_before_anything_runs():
    harness = Harness()

    assert set_public_port(harness.deps(), "ghost", PUBLIC) == OpError(404, 'Service "ghost" not found')
    assert harness.log == []


def test_a_service_already_on_the_public_port_changes_nothing():
    harness = Harness()

    assert set_public_port(harness.deps(), "b", PUBLIC) == AlreadyPublic("b", PUBLIC)
    assert harness.log == []


def test_every_holder_is_moved_before_the_service_takes_the_slot_and_the_order_is_pinned():
    harness = Harness()
    harness.restarts = {"a": {"restarted": True}}

    outcome = set_public_port(harness.deps(), "a", PUBLIC)

    assert outcome == PublicPortSet(
        "a", PUBLIC,
        updates=[
            {"service": "b", "old_port": PUBLIC, "new_port": 3310},
            {"service": "c", "old_port": PUBLIC, "new_port": 3311},
            {"service": "a", "old_port": 3302, "new_port": PUBLIC},
        ],
        restarts=[
            {"service": "a", "restarted": True},
            {"service": "b", "restarted": False},
            {"service": "c", "restarted": False},
        ],
    )
    assert harness.log == [
        ("next_free_port", [3300]),
        ("db_update", "b", 3310),
        ("next_free_port", [3300]),
        ("db_update", "c", 3311),
        ("db_update", "a", PUBLIC),
        ("rebuild",),
        ("recreate", "a"),
        ("recreate", "b"),
        ("recreate", "c"),
        ("proxy_sync",),
    ]


def test_a_move_with_nobody_displaced_never_asks_for_a_free_port():
    harness = Harness({"a": {"port": 3302}, "d": {"port": 3304}})

    outcome = set_public_port(harness.deps(), "a", PUBLIC)

    assert outcome.updates == [{"service": "a", "old_port": 3302, "new_port": PUBLIC}]
    assert harness.names() == ["db_update", "rebuild", "recreate", "proxy_sync"]


def test_a_failing_recreate_is_reported_for_that_service_and_the_rest_still_run():
    harness = Harness()
    harness.fail["recreate"] = RuntimeError("docker down")

    outcome = set_public_port(harness.deps(), "a", PUBLIC)

    assert [r["restarted"] for r in outcome.restarts] == [False, False, False]
    assert all(r["error"] == "docker down" for r in outcome.restarts)
    assert harness.names()[-1] == "proxy_sync"


@pytest.mark.parametrize("failing,reached", [
    ("next_free_port", ["next_free_port"]),
    ("db_update", ["next_free_port", "db_update"]),
    ("rebuild", ["next_free_port", "db_update", "next_free_port", "db_update", "db_update", "rebuild"]),
])
def test_a_fatal_failure_propagates_and_stops_the_later_steps(failing, reached):
    harness = Harness()
    harness.fail[failing] = RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        set_public_port(harness.deps(), "a", PUBLIC)

    assert harness.names() == reached


def test_the_inspector_failing_after_the_recreates_is_fatal_and_leaves_the_compose_written():
    harness = Harness()
    harness.fail["proxy_sync"] = RuntimeError("inspector down")

    with pytest.raises(RuntimeError, match="inspector down"):
        set_public_port(harness.deps(), "a", PUBLIC)

    assert harness.names().count("recreate") == 3 and "rebuild" in harness.names()


def test_the_public_port_phase_reaches_hooks_with_the_displaced_services():
    seen = []

    class Recording(ServiceHook):
        def after_public_port(self, ctx):
            seen.append((ctx.subject, list(ctx.displaced)))

    run_phase([Recording()], Phase.AFTER_PUBLIC_PORT, PublicPortContext("a", ["b", "c"]))

    assert seen == [("a", ["b", "c"])]
