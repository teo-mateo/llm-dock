import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from service_ops import rotate_key
from service_ops.affected import AffectedState
from service_ops.deps import Infra
from service_ops.rotate_key import KeyRotated, RotateKeyDeps


class Harness:
    def __init__(self, running=(), registered=(), updated=("a", "b")):
        self.log = []
        self.fail = {}
        self.running = list(running)
        self.registered = list(registered)
        self.updated = list(updated)
        self.stop_results = {}

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
            def list_services_in_db(self):
                return {"a": {"api_key": "old"}}

            def save_services_db(self, services):
                harness.step("undo_save", dict(services))

            def rebuild_compose_file(self):
                harness.step("undo_rebuild")

        infra = Infra(
            compose=lambda: Compose(),
            get_container=lambda name: None,
            remove_container=lambda name: None,
            emit=lambda event: harness.step("emit", event),
            now=lambda: 0.0,
            hooks=[],
        )
        return RotateKeyDeps(
            infra,
            affected_state=lambda: AffectedState(["a", "b"], harness.running, harness.registered),
            generate_key=lambda: "new",
            rotate_in_db=lambda compose, key: harness.step(
                "rotate_in_db", key, result={"new_key": key, "updated": harness.updated}
            ),
            commit_key=lambda key: harness.step("commit_key", key),
            stop_service=lambda name: harness.step("stop", name, result=harness.stop_results.get(name, {"success": True})),
        )


def test_the_files_commit_first_then_the_key_then_the_stops():
    harness = Harness(running=["b", "a"], registered=["a"])

    outcome = rotate_key(harness.deps())

    assert harness.log == [("rotate_in_db", "new"), ("commit_key", "new"), ("stop", "b"), ("stop", "a")]
    assert outcome == KeyRotated("new", ["a", "b"], 2, ["b", "a"], {}, ["a"])


def test_a_failing_files_commit_never_reaches_the_key_or_the_containers():
    harness = Harness(running=["a"])
    harness.fail["rotate_in_db"] = RuntimeError("compose invalid")

    with pytest.raises(RuntimeError, match="compose invalid"):
        rotate_key(harness.deps())

    assert harness.names() == ["rotate_in_db"]


def test_a_failing_key_commit_restores_services_and_compose_and_stops_nothing():
    harness = Harness(running=["a"])
    harness.fail["commit_key"] = OSError("read-only")

    with pytest.raises(OSError, match="read-only"):
        rotate_key(harness.deps())

    assert harness.log == [
        ("rotate_in_db", "new"), ("commit_key", "new"),
        ("undo_save", {"a": {"api_key": "old"}}), ("undo_rebuild",),
    ]


def test_a_failed_stop_is_reported_per_container_and_the_rest_still_stop():
    harness = Harness(running=["a", "b"])
    harness.stop_results = {"a": {"success": False, "error": "busy"}}

    outcome = rotate_key(harness.deps())

    assert outcome.stopped == ["b"]
    assert outcome.stop_errors == {"a": "busy"}
    assert outcome.ok is False


def test_a_failure_without_a_reason_reads_as_unknown_error():
    harness = Harness(running=["a"])
    harness.stop_results = {"a": {"success": False}}

    assert rotate_key(harness.deps()).stop_errors == {"a": "unknown error"}


def test_a_stop_that_raises_is_recorded_and_the_remaining_containers_still_stop():
    harness = Harness(running=["a", "b"])
    harness.fail["stop"] = RuntimeError("docker down")

    outcome = rotate_key(harness.deps())

    assert harness.names() == ["rotate_in_db", "commit_key", "stop", "stop"]
    assert outcome.new_key == "new"
    assert outcome.stop_errors == {"a": "docker down", "b": "docker down"}
    assert outcome.ok is False


def test_one_raising_stop_does_not_hide_the_ones_that_succeeded():
    harness = Harness(running=["a", "b"])
    original = harness.deps()
    calls = []

    def stop(name):
        calls.append(name)
        if name == "a":
            raise RuntimeError("boom")
        return {"success": True}

    deps = RotateKeyDeps(
        original.infra, original.affected_state, original.generate_key,
        original.rotate_in_db, original.commit_key, stop,
    )

    outcome = rotate_key(deps)

    assert calls == ["a", "b"] and outcome.stopped == ["b"] and outcome.stop_errors == {"a": "boom"}


def test_the_messages_and_body_match_the_wire_shape():
    ok = KeyRotated("k", ["a"], 3, ["a"], {}, ["b"])
    partial = KeyRotated("k", ["a"], 3, [], {"z": "x", "y": "x"})

    assert ok.ok and ok.body() == {
        "success": True, "partial": False, "new_api_key": "k", "services_updated": 1,
        "total_services": 3, "stopped": ["a"], "stop_errors": {}, "openwebui_registered": ["b"],
        "message": "Default API key rotated across 1 service(s); 1 running container(s) stopped.",
    }
    assert partial.body()["message"].endswith("stop them manually: y, z.")
