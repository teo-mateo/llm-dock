import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from service_ops.hooks import DeleteContext, RenameContext, ServiceHook, run_phase
from service_ops.outcomes import Deleted, OpError, Renamed
from service_ops.subsystems import BenchmarkHook, InspectorHook, KeyFileHook, OpenWebUIHook


class Recording(ServiceHook):
    def __init__(self, name, log, fail=None, best_effort=True):
        self.name = name
        self.log = log
        self.fail = fail
        self.best_effort = best_effort

    def after_rename(self, ctx):
        self.log.append(self.name)
        if self.fail:
            raise self.fail


def _ctx(**config):
    return RenameContext("old", "new", {"template_type": "llamacpp", "port": 3301, "api_key": "k", **config})


def test_hooks_run_in_registration_order():
    log = []

    run_phase([Recording("a", log), Recording("b", log), Recording("c", log)], "after_rename", _ctx())

    assert log == ["a", "b", "c"]


def test_a_best_effort_hook_failing_is_logged_and_the_rest_still_run():
    log = []
    hooks = [Recording("a", log, fail=RuntimeError("boom")), Recording("b", log)]

    run_phase(hooks, "after_rename", _ctx())

    assert log == ["a", "b"]


def test_a_hook_that_is_not_best_effort_aborts_with_its_exception():
    log = []
    hooks = [Recording("a", log, fail=RuntimeError("fatal"), best_effort=False), Recording("b", log)]

    with pytest.raises(RuntimeError, match="fatal"):
        run_phase(hooks, "after_rename", _ctx())

    assert log == ["a"]


def test_a_phase_a_hook_does_not_implement_is_a_no_op():
    run_phase([ServiceHook()], "before_rename", _ctx())
    run_phase([ServiceHook()], "after_delete", DeleteContext("old", {}))


def test_the_outcomes_are_plain_values():
    assert OpError(409, "busy").body() == {"error": "busy"}
    assert Renamed("a", "b") != Renamed("a", "c")
    assert Deleted("a") == Deleted("a")


class TestOpenWebUIHook:
    def make(self, registered=True, log=None):
        log = [] if log is None else log
        hook = OpenWebUIHook(
            is_registered=lambda name, engine: log.append(("check", name, engine)) or registered,
            unregister=lambda name, engine: log.append(("unregister", name, engine)),
            register=lambda name, port, key, engine: log.append(("register", name, port, key, engine)),
        )
        return hook, log

    def test_a_registered_service_is_unregistered_before_and_re_registered_after(self):
        hook, log = self.make()
        ctx = _ctx()

        hook.before_rename(ctx)
        hook.after_rename(ctx)

        assert log == [
            ("check", "old", "llamacpp"),
            ("unregister", "old", "llamacpp"),
            ("register", "new", 3301, "k", "llamacpp"),
        ]

    def test_an_unregistered_service_is_left_alone(self):
        hook, log = self.make(registered=False)
        ctx = _ctx()

        hook.before_rename(ctx)
        hook.after_rename(ctx)

        assert log == [("check", "old", "llamacpp")]

    def test_a_service_with_no_engine_never_touches_it(self):
        hook, log = self.make()
        ctx = RenameContext("old", "new", {"port": 1})

        hook.before_rename(ctx)
        hook.after_rename(ctx)

        assert log == []

    def test_a_failing_unregister_still_re_registers_after_the_rename(self):
        log = []
        hook = OpenWebUIHook(
            is_registered=lambda n, e: True,
            unregister=lambda n, e: (_ for _ in ()).throw(RuntimeError("owu down")),
            register=lambda *a: log.append(a),
        )
        ctx = _ctx()

        run_phase([hook], "before_rename", ctx)
        run_phase([hook], "after_rename", ctx)

        assert log == [("new", 3301, "k", "llamacpp")]


def test_the_inspector_hook_renames_captures_then_syncs_and_is_fatal():
    log = []
    hook = InspectorHook(lambda old, new: log.append(("rename", old, new)), lambda: log.append(("sync",)))

    hook.after_rename(_ctx())
    hook.after_delete(DeleteContext("old", {}))

    assert log == [("rename", "old", "new"), ("sync",), ("sync",)]
    assert hook.best_effort is False


def test_the_benchmark_hook_renames_the_rows():
    log = []

    BenchmarkHook(lambda old, new: log.append((old, new)) or 3).after_rename(_ctx())

    assert log == [("old", "new")]


def test_the_key_file_hook_removes_on_delete_only():
    log = []
    hook = KeyFileHook(log.append)

    hook.after_rename(_ctx())
    hook.after_delete(DeleteContext("svc", {}))

    assert log == ["svc"]
