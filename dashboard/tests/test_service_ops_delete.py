import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from service_ops import delete
from service_ops.delete import DeleteDeps, Deleted
from service_ops.deps import Infra
from service_ops.errors import service_not_found
from service_ops.subsystems import BenchmarkHook, InspectorHook, KeyFileHook, OpenWebUIHook


class Harness:
    def __init__(self, config=None):
        self.log = []
        self.fail = {}
        self.config = {"template_type": "llamacpp"} if config is None else config

    def step(self, name, *args, result=None):
        self.log.append((name, *args))
        if name in self.fail:
            raise self.fail[name]
        return result

    def deps(self):
        harness = self

        class Compose:
            def get_service_from_db(self, name):
                return harness.config or None

            def remove_service_from_db(self, name):
                harness.step("db_remove", name)

            def rebuild_compose_file(self):
                harness.step("rebuild")

        return DeleteDeps(Infra(
            compose=lambda: Compose(),
            get_container=lambda name: None,
            remove_container=lambda name: self.step("rm", name),
            hooks=[
                InspectorHook(lambda o, n: self.step("proxy_rename", o, n), lambda: self.step("proxy_sync")),
                BenchmarkHook(lambda o, n: self.step("bench_rename", o, n, result=1)),
                KeyFileHook(lambda name: self.step("key_remove", name)),
                OpenWebUIHook(
                    lambda n, e: self.step("owu_check", n, e, result=True),
                    lambda n, e: self.step("owu_unregister", n, e),
                    lambda n, p, k, e: self.step("owu_register", n, p, k, e),
                ),
            ],
            emit=lambda event: self.step("emit", event),
            now=lambda: 1234.5,
        ), stop_container=lambda name: self.step("stop", name))

    def names(self):
        return [entry[0] for entry in self.log]


def test_the_full_delete_order_through_the_hook_list_ends_with_the_event():
    harness = Harness()

    outcome = delete(harness.deps(), "svc")

    assert outcome == Deleted("svc")
    assert harness.log == [
        ("stop", "svc"),
        ("rm", "svc"),
        ("db_remove", "svc"),
        ("rebuild",),
        ("proxy_sync",),
        ("key_remove", "svc"),
        ("emit", {
            "service_name": "svc", "action": "service-deleted", "status": "deleted",
            "container_id": "", "timestamp": 1234.5,
        }),
    ]


def test_an_unknown_service_is_a_404_before_anything_runs():
    harness = Harness(config={})

    assert delete(harness.deps(), "svc") == service_not_found("svc")
    assert harness.log == []


def test_a_failing_stop_skips_the_removal_but_not_the_delete():
    harness = Harness()
    harness.fail["stop"] = RuntimeError("docker down")

    outcome = delete(harness.deps(), "svc")

    assert outcome == Deleted("svc")
    assert harness.names() == ["stop", "db_remove", "rebuild", "proxy_sync", "key_remove", "emit"]


def test_a_failing_removal_does_not_stop_the_delete():
    harness = Harness()
    harness.fail["rm"] = RuntimeError("docker down")

    assert delete(harness.deps(), "svc") == Deleted("svc")
    assert harness.names()[-4:] == ["rebuild", "proxy_sync", "key_remove", "emit"]


def test_a_failing_key_removal_is_best_effort_and_the_event_still_goes_out():
    harness = Harness()
    harness.fail["key_remove"] = OSError("read-only")

    assert delete(harness.deps(), "svc") == Deleted("svc")
    assert harness.names()[-1] == "emit"


@pytest.mark.parametrize("failing,reached", [
    ("db_remove", ["stop", "rm", "db_remove"]),
    ("rebuild", ["stop", "rm", "db_remove", "rebuild"]),
    ("proxy_sync", ["stop", "rm", "db_remove", "rebuild", "proxy_sync"]),
])
def test_a_fatal_failure_propagates_and_announces_nothing(failing, reached):
    harness = Harness()
    harness.fail[failing] = RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        delete(harness.deps(), "svc")

    assert harness.names() == reached
