import os
import sys
import threading
import time

import pytest
import docker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.docker_events import DockerEventConsumer
from services.event_manager import DockerEventManager


@pytest.fixture(autouse=True)
def set_env_vars():
    os.environ.setdefault("DASHBOARD_TOKEN", "test-token-events")
    os.environ.setdefault("COMPOSE_PROJECT_NAME", "llm-dock")


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
    stop_event = threading.Event()

    def event_collector():
        try:
            for evt in consumer.list_events():
                events.append(evt)
                if stop_event.is_set():
                    time.sleep(0.5)
                    return
        except Exception:
            pass
        stop_event.wait(timeout=10)

    collector = threading.Thread(target=event_collector, daemon=True)
    collector.start()

    time.sleep(0.5)

    container = client.containers.run(
        "hello-world",
        name="llm-dock-test-integration-svc",
        labels={
            "com.docker.compose.project": project_name,
            "com.docker.compose.service": "test-integration-svc",
        },
        detach=True,
    )

    time.sleep(2)

    stop_event.set()
    collector.join(timeout=5)

    assert len(events) > 0, "No events captured from real Docker"

    test_events = [e for e in events if e.get("service_name") == "test-integration-svc"]
    assert len(test_events) > 0, f"No events for test-integration-svc. Got events: {events}"

    for evt in test_events:
        assert "status" in evt, f"Event missing 'status': {evt}"
        assert "action" in evt, f"Event missing 'action': {evt}"
        assert "container_id" in evt, f"Event missing 'container_id': {evt}"
        assert "timestamp" in evt, f"Event missing 'timestamp': {evt}"

    try:
        container.remove(force=True)
    except Exception:
        pass


def test_event_manager_callbacks_fire_on_container_lifecycle():
    """
    Integration test: DockerEventManager runs in a background thread,
    callbacks receive events, and start/stop lifecycle works correctly.
    """
    client = docker.from_env()
    project_name = os.environ.get("COMPOSE_PROJECT_NAME", "llm-dock")

    manager = DockerEventManager(docker_client=client, project_name=project_name)

    received_events = []

    def on_event(event):
        received_events.append(event)

    manager.register_callback(on_event)
    assert manager.is_running is False

    manager.start()
    assert manager.is_running is True

    time.sleep(0.5)

    container = client.containers.run(
        "hello-world",
        name="llm-dock-test-mgr-svc",
        labels={
            "com.docker.compose.project": project_name,
            "com.docker.compose.service": "test-mgr-svc",
        },
        detach=True,
    )

    time.sleep(2)

    try:
        container.remove(force=True)
    except Exception:
        pass

    manager.stop()

    assert not manager.is_running
    assert len(received_events) > 0

    mgr_events = [e for e in received_events if e.get("service_name") == "test-mgr-svc"]
    assert len(mgr_events) > 0, f"No events for test-mgr-svc. Got events: {received_events}"


def test_event_manager_start_stop_idempotent():
    """
    Verify that calling start() twice or stop() twice doesn't raise.
    """
    manager = DockerEventManager()

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
    client = docker.from_env()
    project_name = os.environ.get("COMPOSE_PROJECT_NAME", "llm-dock")

    manager = DockerEventManager(docker_client=client, project_name=project_name)

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
    time.sleep(0.5)

    container = client.containers.run(
        "hello-world",
        name="llm-dock-test-unreg-svc",
        labels={
            "com.docker.compose.project": project_name,
            "com.docker.compose.service": "test-unreg-svc",
        },
        detach=True,
    )

    time.sleep(2)

    try:
        container.remove(force=True)
    except Exception:
        pass

    manager.stop()

    assert len(kept_events) > 0, "Kept callback should have received events"
    assert len(removed_events) == 0, "Removed callback should not have received events"


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
