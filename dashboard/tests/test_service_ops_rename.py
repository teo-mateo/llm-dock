import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from service_ops import rename
from service_ops.deps import ServiceOpsDeps
from service_ops.outcomes import OpError, Renamed
from service_ops.subsystems import BenchmarkHook, InspectorHook, KeyFileHook, OpenWebUIHook

CONFIG = {"template_type": "llamacpp", "port": 3301, "api_key": "k"}


class Harness:
    def __init__(self, config=CONFIG, container=None, registered=True):
        self.log = []
        self.fail = {}
        self.config = config
        self.container = container
        self.registered = registered
        self.rename_error = None

    def step(self, name, *args, result=None):
        self.log.append((name, *args))
        if name in self.fail:
            raise self.fail[name]
        return result

    def deps(self):
        harness = self

        class Compose:
            def get_service_from_db(self, name):
                return harness.config

            def rename_service(self, old, new):
                harness.step("db_rename", old, new)
                if harness.rename_error:
                    raise harness.rename_error

        return ServiceOpsDeps(
            compose=lambda: Compose(),
            get_container=lambda name: self.container,
            stop_container=lambda name: self.step("stop", name),
            remove_container=lambda name: self.step("rm", name),
            hooks=[
                InspectorHook(lambda o, n: self.step("proxy_rename", o, n), lambda: self.step("proxy_sync")),
                BenchmarkHook(lambda o, n: self.step("bench_rename", o, n, result=1)),
                KeyFileHook(lambda name: self.step("key_remove", name)),
                OpenWebUIHook(
                    lambda n, e: self.step("owu_check", n, e, result=self.registered),
                    lambda n, e: self.step("owu_unregister", n, e),
                    lambda n, p, k, e: self.step("owu_register", n, p, k, e),
                ),
            ],
            emit=lambda event: self.step("emit", event),
            now=lambda: 0.0,
        )

    def names(self):
        return [entry[0] for entry in self.log]


def test_the_full_rename_order_through_the_hook_list():
    harness = Harness(container=SimpleNamespace(status="exited"))

    outcome = rename(harness.deps(), "old", "new")

    assert outcome == Renamed("old", "new")
    assert harness.log == [
        ("owu_check", "old", "llamacpp"),
        ("owu_unregister", "old", "llamacpp"),
        ("rm", "old"),
        ("db_rename", "old", "new"),
        ("proxy_rename", "old", "new"),
        ("proxy_sync",),
        ("bench_rename", "old", "new"),
        ("owu_register", "new", 3301, "k", "llamacpp"),
    ]


def test_an_unknown_service_is_a_404_before_anything_runs():
    harness = Harness(config=None)

    assert rename(harness.deps(), "old", "new") == OpError(404, 'Service "old" not found')
    assert harness.log == []


def test_a_running_service_is_a_409_before_anything_runs():
    harness = Harness(container=SimpleNamespace(status="running"))

    assert rename(harness.deps(), "old", "new") == OpError(409, "Service must be stopped before renaming")
    assert harness.log == []


def test_no_container_means_no_removal():
    harness = Harness(registered=False)

    rename(harness.deps(), "old", "new")

    assert "rm" not in harness.names()


@pytest.mark.parametrize("failing", ["owu_unregister", "rm", "bench_rename", "owu_register"])
def test_a_best_effort_failure_does_not_stop_the_rename(failing):
    harness = Harness(container=SimpleNamespace(status="exited"))
    harness.fail[failing] = RuntimeError("boom")

    outcome = rename(harness.deps(), "old", "new")

    assert outcome == Renamed("old", "new")
    assert harness.names()[-1] == "owu_register"


def test_a_taken_or_invalid_name_is_a_400_with_the_compose_dbs_text_and_no_after_steps():
    harness = Harness(registered=False)
    harness.rename_error = ValueError("already exists")

    outcome = rename(harness.deps(), "old", "new")

    assert outcome == OpError(400, "already exists")
    assert harness.names() == ["owu_check", "db_rename"]


def test_any_other_compose_failure_propagates_for_the_route_to_turn_into_a_500():
    harness = Harness()
    harness.rename_error = RuntimeError("disk full")

    with pytest.raises(RuntimeError, match="disk full"):
        rename(harness.deps(), "old", "new")


def test_the_inspector_failing_aborts_after_the_db_rename_and_skips_later_hooks():
    harness = Harness()
    harness.fail["proxy_rename"] = RuntimeError("inspector down")

    with pytest.raises(RuntimeError, match="inspector down"):
        rename(harness.deps(), "old", "new")

    assert harness.names() == ["owu_check", "owu_unregister", "db_rename", "proxy_rename"]
