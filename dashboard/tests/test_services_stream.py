import json
import os
import sys
import time
from datetime import datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DASHBOARD_TOKEN", "test-token-stream")

from services.service_stream import ServiceStream
from services.service_stream_frames import (
    DELTA,
    ERROR,
    KEEPALIVE_FRAME,
    SNAPSHOT,
    delta_frame,
    error_frame,
    snapshot_frame,
)

FIXED_NOW = datetime(2026, 11, 10, 16, 0, 0)


def _event(name, status, action="die"):
    return {
        "service_name": name,
        "status": status,
        "action": action,
        "container_id": "c" * 12,
        "timestamp": 1_700_000_000.0,
    }


class FakeManager:
    def __init__(self, state):
        self.state = dict(state)
        self.callbacks = []
        self.on_snapshot = None

    def register_callback(self, cb):
        self.callbacks.append(cb)

    def unregister_callback(self, cb):
        self.callbacks.remove(cb)

    def emit(self, event):
        for cb in list(self.callbacks):
            cb(event)

    def get_services_snapshot(self):
        snapshot = [{"name": n, "status": s} for n, s in self.state.items()]
        if self.on_snapshot:
            self.on_snapshot()
        return snapshot


def _frames(manager, **kwargs):
    return ServiceStream(manager, **kwargs).frames(0, now=lambda: FIXED_NOW)


def _parse(frame):
    return json.loads(frame[len("data: "):])


def _apply(view, frame):
    if frame == KEEPALIVE_FRAME:
        return view
    payload = _parse(frame)
    if payload["type"] == SNAPSHOT:
        return {s["name"]: s["status"] for s in payload["data"]["services"]}
    view = dict(view)
    view[payload["service_name"]] = payload["status"]
    return view


def _settle(gen, view):
    for _ in range(50):
        frame = next(gen)
        if frame == KEEPALIVE_FRAME:
            return view
        view = _apply(view, frame)
    raise AssertionError("stream never went idle")


def test_event_during_snapshot_acquisition_is_delivered():
    manager = FakeManager({"svc": "running"})

    def change_mid_snapshot():
        manager.state["svc"] = "exited"
        manager.emit(_event("svc", "exited"))

    manager.on_snapshot = change_mid_snapshot
    gen = _frames(manager)
    view = _apply({}, next(gen))

    assert _settle(gen, view) == {"svc": "exited"}


def test_event_right_after_first_yield_is_delivered():
    manager = FakeManager({"svc": "running"})
    gen = _frames(manager)
    view = _apply({}, next(gen))

    manager.state["svc"] = "exited"
    manager.emit(_event("svc", "exited"))

    assert _settle(gen, view) == {"svc": "exited"}


def test_replayed_deltas_end_on_the_final_state():
    manager = FakeManager({"svc": "exited"})

    def burst():
        manager.emit(_event("svc", "running", "start"))
        manager.emit(_event("svc", "exited", "die"))

    manager.on_snapshot = burst
    gen = _frames(manager)
    view = _apply({}, next(gen))

    assert _settle(gen, view) == {"svc": "exited"}


def test_disconnect_right_after_the_first_frame_unregisters():
    manager = FakeManager({"svc": "running"})
    gen = _frames(manager)
    assert _parse(next(gen))["type"] == SNAPSHOT
    assert len(manager.callbacks) == 1

    gen.close()

    assert manager.callbacks == []


def test_unstarted_stream_registers_nothing():
    manager = FakeManager({"svc": "running"})
    gen = _frames(manager)
    gen.close()

    assert manager.callbacks == []


def test_snapshot_failure_yields_an_error_frame_and_unregisters():
    manager = FakeManager({"svc": "running"})

    def boom():
        raise RuntimeError("docker is down")

    manager.on_snapshot = boom
    gen = _frames(manager)

    assert _parse(next(gen)) == {"type": ERROR, "message": "docker is down"}
    with pytest.raises(StopIteration):
        next(gen)
    assert manager.callbacks == []


def test_updates_after_subscription_still_flow():
    manager = FakeManager({"svc": "running"})
    gen = _frames(manager)
    view = _apply({}, next(gen))
    assert next(gen) == KEEPALIVE_FRAME

    manager.emit(_event("svc", "exited"))
    first = next(gen)
    manager.emit(_event("svc", "running", "start"))
    second = next(gen)

    assert _parse(first)["type"] == DELTA and _parse(second)["type"] == DELTA
    assert _apply(_apply(view, first), second) == {"svc": "running"}


def test_overflow_resnapshots_instead_of_growing_unbounded():
    manager = FakeManager({"svc": "running"})
    gen = _frames(manager, max_pending=3)
    view = _apply({}, next(gen))
    assert next(gen) == KEEPALIVE_FRAME

    for _ in range(10):
        manager.emit(_event("svc", "running", "start"))
    manager.state["svc"] = "exited"
    manager.emit(_event("svc", "exited"))

    frame = next(gen)
    assert _parse(frame)["type"] == SNAPSHOT
    assert _apply(view, frame) == {"svc": "exited"}
    assert next(gen) == KEEPALIVE_FRAME

    manager.emit(_event("svc", "running", "start"))
    assert _parse(next(gen))["type"] == DELTA


@pytest.fixture
def utc(monkeypatch):
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def test_snapshot_frame_golden():
    frame = snapshot_frame(
        [{"name": "a", "status": "running"}, {"name": "b", "status": "exited"}],
        lambda: FIXED_NOW,
    )

    assert frame == (
        'data: {"type": "snapshot", "data": {"services": ['
        '{"name": "a", "status": "running"}, {"name": "b", "status": "exited"}], '
        '"total": 2, "running": 1, "stopped": 1}, "timestamp": "2026-11-10T16:00:00Z"}\n\n'
    )


def test_delta_frame_golden(utc):
    assert delta_frame(_event("a", "exited")) == (
        'data: {"type": "delta", "service_name": "a", "status": "exited", '
        '"action": "die", "container_id": "cccccccccccc", '
        '"timestamp": "2023-11-14T22:13:20Z"}\n\n'
    )


def test_delta_frame_with_metadata_golden(utc):
    event = {**_event("a", "running", "metadata-changed"), "metadata": {"favorite": True}}

    assert delta_frame(event) == (
        'data: {"type": "delta", "service_name": "a", "status": "running", '
        '"action": "metadata-changed", "container_id": "cccccccccccc", '
        '"timestamp": "2023-11-14T22:13:20Z", "metadata": {"favorite": true}}\n\n'
    )


def test_error_frame_golden():
    assert error_frame("boom") == 'data: {"type": "error", "message": "boom"}\n\n'


def test_keepalive_frame_golden():
    assert KEEPALIVE_FRAME == ": keepalive\n\n"
