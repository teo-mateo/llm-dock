import os
import sys
import threading
import time
import uuid

import pytest
import docker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.docker_events import DockerEventConsumer
from services.event_manager import DockerEventManager


def _pre_clean_stopped(client, name_prefix: str):
    # A run interrupted between container creation and its finally leaves an
    # exited corpse under the test's name prefix; with unique per-run names
    # only corpses (never live containers) can accumulate, so clean exited only.
    for c in client.containers.list(filters={"name": name_prefix, "status": "exited"}):
        try:
            c.remove(force=True)
        except Exception:
            pass


def _wait_for(predicate, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


class _ParkedStream:
    """Parks until close() — stands in for the engine long-poll without a daemon."""

    def __init__(self):
        self._stop = threading.Event()

    def __iter__(self):
        return self

    def __next__(self):
        while not self._stop.wait(timeout=0.05):
            pass
        raise StopIteration

    def close(self):
        self._stop.set()


class _FakeDockerClient:
    def __init__(self):
        self._stream = _ParkedStream()

    def events(self, **kwargs):
        return self._stream


def _synthetic_event(service_name: str) -> dict:
    return {
        "service_name": service_name,
        "status": "running",
        "action": "start",
        "container_id": "c" * 12,
        "timestamp": time.time(),
    }


@pytest.mark.docker
def test_list_events_captures_container_lifecycle():
    """
    Integration test: instantiate DockerEventConsumer against real Docker,
    start and stop a test container, and assert list_events yields the
    corresponding lifecycle events.
    """
    client = docker.from_env()
    project_name = os.environ.get("COMPOSE_PROJECT_NAME", "llm-dock")

    consumer = DockerEventConsumer(docker_client=client, project_name=project_name)

    events = []

    def event_collector():
        try:
            for evt in consumer.list_events():
                events.append(evt)
        except Exception:
            pass

    collector = threading.Thread(target=event_collector, daemon=True)
    collector.start()

    # The stream must be open before the container starts, or its earliest
    # lifecycle events are missed.
    assert consumer.stream_ready.wait(timeout=10), "event stream never opened"

    _pre_clean_stopped(client, "llm-dock-test-integration-svc")
    container = client.containers.run(
        "hello-world",
        name=f"llm-dock-test-integration-svc-{uuid.uuid4().hex[:8]}",
        labels={
            "com.docker.compose.project": project_name,
            "com.docker.compose.service": "test-integration-svc",
        },
        detach=True,
    )

    try:
        assert _wait_for(
            lambda: any(e.get("service_name") == "test-integration-svc" for e in events)
        ), "No events captured from real Docker"

        test_events = [e for e in events if e.get("service_name") == "test-integration-svc"]
        for evt in test_events:
            assert "status" in evt, f"Event missing 'status': {evt}"
            assert "action" in evt, f"Event missing 'action': {evt}"
            assert "container_id" in evt, f"Event missing 'container_id': {evt}"
            assert "timestamp" in evt, f"Event missing 'timestamp': {evt}"
    finally:
        try:
            container.remove(force=True)
        except Exception:
            pass
        consumer.close()
        collector.join(timeout=5)


def test_event_manager_callbacks_fire_on_container_lifecycle():
    """
    DockerEventManager dispatches events to registered callbacks, and the
    start/stop lifecycle works correctly. Events arrive via emit(), the
    same public API the routes use for deltas that have no Docker event.
    """
    manager = DockerEventManager(docker_client=_FakeDockerClient(), project_name="llm-dock")

    received_events = []

    def on_event(event):
        received_events.append(event)

    manager.register_callback(on_event)
    assert manager.is_running is False

    manager.start()
    assert manager.is_running is True

    manager.emit(_synthetic_event("test-mgr-svc"))

    manager.stop()

    assert not manager.is_running
    assert len(received_events) > 0

    mgr_events = [e for e in received_events if e.get("service_name") == "test-mgr-svc"]
    assert len(mgr_events) > 0, f"No events for test-mgr-svc. Got events: {received_events}"


def test_event_manager_start_stop_idempotent():
    """
    Verify that calling start() twice or stop() twice doesn't raise.
    """
    manager = DockerEventManager(docker_client=_FakeDockerClient())

    manager.start()
    manager.start()
    assert manager.is_running is True

    manager.stop()
    manager.stop()
    assert manager.is_running is False


def test_event_manager_unregister_callback():
    """
    Verify that unregistering a callback prevents it from receiving events.
    """
    manager = DockerEventManager(docker_client=_FakeDockerClient(), project_name="llm-dock")

    kept_events = []
    removed_events = []

    def kept_callback(event):
        kept_events.append(event)

    def removed_callback(event):
        removed_events.append(event)

    manager.register_callback(kept_callback)
    manager.register_callback(removed_callback)
    manager.unregister_callback(removed_callback)

    manager.start()
    manager.emit(_synthetic_event("test-unreg-svc"))
    manager.stop()

    assert len(kept_events) > 0, "Kept callback should have received events"
    assert len(removed_events) == 0, "Removed callback should not have received events"


@pytest.mark.docker
def test_event_manager_snapshot_returns_real_services():
    """
    Verify get_services_snapshot() returns the current Docker services list.
    Uses a test docker-compose file with alpine images.
    """
    import unittest.mock as mock
    import os

    test_compose_path = os.path.join(os.path.dirname(__file__), "docker-compose.test.yml")

    with mock.patch("docker_utils.COMPOSE_FILE", test_compose_path):
        manager = DockerEventManager()

        snapshot = manager.get_services_snapshot()

        assert isinstance(snapshot, list)
        assert len(snapshot) > 0, "Snapshot should contain services from the test compose file"

        for svc in snapshot:
            assert "name" in svc
            assert "status" in svc
            assert "host_port" in svc
