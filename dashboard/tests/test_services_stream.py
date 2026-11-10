import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DASHBOARD_TOKEN", "test-token-stream")

from routes import services as services_route
from services.service_stream import DELTA, SNAPSHOT, ServiceStream


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


def _apply(view, kind, body):
    if kind == SNAPSHOT:
        return {s["name"]: s["status"] for s in body}
    view = dict(view)
    view[body["service_name"]] = body["status"]
    return view


def _drain(stream, view):
    while (item := stream.poll()) is not None:
        view = _apply(view, *item)
    return view


def _connect(manager, stream):
    return {s["name"]: s["status"] for s in stream.open()}


def test_event_during_snapshot_acquisition_is_delivered():
    manager = FakeManager({"svc": "running"})

    def change_mid_snapshot():
        manager.state["svc"] = "exited"
        manager.emit(_event("svc", "exited"))

    manager.on_snapshot = change_mid_snapshot
    stream = ServiceStream(manager)
    view = _connect(manager, stream)
    view = _drain(stream, view)

    assert view == {"svc": "exited"}


def test_event_right_after_first_yield_is_delivered():
    manager = FakeManager({"svc": "running"})
    stream = ServiceStream(manager)
    view = _connect(manager, stream)

    manager.state["svc"] = "exited"
    manager.emit(_event("svc", "exited"))

    assert _drain(stream, view) == {"svc": "exited"}


def test_replayed_deltas_end_on_the_final_state():
    manager = FakeManager({"svc": "exited"})

    def burst():
        manager.emit(_event("svc", "running", "start"))
        manager.emit(_event("svc", "exited", "die"))

    manager.on_snapshot = burst
    stream = ServiceStream(manager)
    view = _drain(stream, _connect(manager, stream))

    assert view == {"svc": "exited"}


def test_immediate_disconnect_unregisters():
    manager = FakeManager({"svc": "running"})
    stream = ServiceStream(manager)
    stream.open()
    assert len(manager.callbacks) == 1

    stream.close()
    stream.close()

    assert manager.callbacks == []


def test_generator_close_after_first_frame_unregisters(monkeypatch):
    from services import event_manager

    manager = FakeManager({"svc": "running"})
    monkeypatch.setattr(event_manager, "register_callback", manager.register_callback)
    monkeypatch.setattr(event_manager, "unregister_callback", manager.unregister_callback)
    monkeypatch.setattr(event_manager, "get_services_snapshot", manager.get_services_snapshot)

    generate = _generator(services_route)
    first = next(generate)
    assert json.loads(first[len("data: "):])["type"] == "snapshot"
    assert len(manager.callbacks) == 1

    generate.close()

    assert manager.callbacks == []


def _generator(route_module):
    from flask import Flask

    app = Flask(__name__)
    with app.test_request_context("/api/services/stream"):
        view = route_module.services_stream.__wrapped__
        response = view()
        return response.response.__self__ if hasattr(response.response, "__self__") else response.response


def test_updates_after_subscription_still_flow():
    manager = FakeManager({"svc": "running"})
    stream = ServiceStream(manager)
    view = _connect(manager, stream)
    assert stream.poll() is None

    manager.emit(_event("svc", "exited"))
    first = stream.poll()
    manager.emit(_event("svc", "running", "start"))
    second = stream.poll()

    assert first[0] == DELTA and second[0] == DELTA
    assert _apply(_apply(view, *first), *second) == {"svc": "running"}


def test_overflow_resnapshots_instead_of_growing_unbounded():
    manager = FakeManager({"svc": "running"})
    stream = ServiceStream(manager, max_pending=3)
    view = _connect(manager, stream)

    for _ in range(10):
        manager.emit(_event("svc", "running", "start"))
    manager.state["svc"] = "exited"
    manager.emit(_event("svc", "exited"))

    kind, body = stream.poll()
    assert kind == SNAPSHOT
    assert _apply(view, kind, body) == {"svc": "exited"}
    assert stream.poll() is None

    manager.emit(_event("svc", "running", "start"))
    assert stream.poll()[0] == DELTA


def test_frame_shapes_are_unchanged():
    snapshot = json.loads(services_route._snapshot_frame([
        {"name": "a", "status": "running"},
        {"name": "b", "status": "exited"},
    ])[len("data: "):])
    assert snapshot["type"] == "snapshot"
    assert snapshot["data"]["total"] == 2
    assert snapshot["data"]["running"] == 1
    assert snapshot["data"]["stopped"] == 1
    assert set(snapshot) == {"type", "data", "timestamp"}

    delta = json.loads(services_route._delta_frame(
        {**_event("a", "exited"), "metadata": {"favorite": True}}
    )[len("data: "):])
    assert set(delta) == {
        "type", "service_name", "status", "action", "container_id", "timestamp", "metadata",
    }
    assert delta["type"] == "delta"
