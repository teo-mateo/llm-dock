import os
import sys
import json
import threading
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

TEST_TOKEN = "test-token-sse"


@pytest.fixture(autouse=True)
def set_env_vars():
    """Ensure required env vars are set before any imports."""
    os.environ["DASHBOARD_TOKEN"] = TEST_TOKEN
    os.environ["COMPOSE_PROJECT_NAME"] = "llm-dock"


def _auth_headers():
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


@pytest.fixture
def client_and_services_path(tmp_path):
    """Create a test client using the app factory."""
    compose_content = """services: {}
  # <<<<<<< BEGIN DYNAMIC
  # >>>>>>> END DYNAMIC

networks:
  llm-network:
    driver: bridge
"""
    compose_path = tmp_path / "docker-compose.yml"
    compose_path.write_text(compose_content)

    services_json = {}
    services_path = tmp_path / "services.json"
    services_path.write_text(json.dumps(services_json))

    from app import create_app

    app = create_app(config={
        "TESTING": True,
        "COMPOSE_FILE": str(compose_path),
        "DASHBOARD_TOKEN": TEST_TOKEN,
    })

    client = app.test_client()

    yield client, services_path


@pytest.fixture
def auth_headers():
    """Return headers with valid auth token."""
    return _auth_headers()


class TestSSEEndpoint:
    """Tests for the /api/services/stream SSE endpoint."""

    def test_sse_requires_auth(self, client_and_services_path):
        """Verify that SSE endpoint requires authentication."""
        client, _ = client_and_services_path
        response = client.get("/api/services/stream")
        assert response.status_code == 401

    def test_sse_content_type(self, client_and_services_path):
        """Verify that SSE endpoint returns correct content type."""
        client, _ = client_and_services_path
        response = client.get("/api/services/stream", headers=_auth_headers())
        assert response.status_code == 200
        assert response.mimetype == "text/event-stream"

    def test_sse_returns_snapshot_on_connect(self, client_and_services_path):
        """Verify that SSE stream returns a snapshot as first message."""
        client, _ = client_and_services_path
        response = client.get("/api/services/stream", headers=_auth_headers())
        assert response.status_code == 200

        # Read the first chunk (should contain snapshot)
        # The stream starts with the snapshot
        chunks = []
        for chunk in response.response:
            chunks.append(chunk.decode("utf-8"))
            if len(chunks) >= 1:
                break

        assert len(chunks) > 0
        first_chunk = chunks[0]
        assert "data: " in first_chunk

        # Parse the JSON payload from the first message
        # Format: "data: {json}\n\n"
        data_start = first_chunk.find("data: ") + len("data: ")
        data_end = first_chunk.find("\n\n")
        if data_end == -1:
            data_end = first_chunk.find("\n")
        json_str = first_chunk[data_start:data_end].strip()
        payload = json.loads(json_str)

        assert payload["type"] == "snapshot"
        assert "data" in payload
        assert "services" in payload["data"]
        assert "total" in payload["data"]
        assert "running" in payload["data"]
        assert "stopped" in payload["data"]
        assert "timestamp" in payload

    def test_sse_streams_events_on_container_lifecycle(self, client_and_services_path, monkeypatch):
        """Verify that the SSE stream relays deltas emitted through the same
        production path the routes use for container lifecycle events."""
        client, _ = client_and_services_path
        from routes import services as services_route
        from services import event_manager

        monkeypatch.setattr(services_route, "SSE_KEEPALIVE_INTERVAL_S", 0.02)

        response = client.get("/api/services/stream", headers=_auth_headers())
        assert response.status_code == 200

        events_received = []
        snapshot_received = threading.Event()
        keepalive_received = threading.Event()

        def process_chunks():
            for chunk in response.response:
                decoded = chunk.decode("utf-8")
                if decoded.startswith(": keepalive"):
                    keepalive_received.set()
                    continue
                if "data: " not in decoded:
                    continue
                data_start = decoded.find("data: ") + len("data: ")
                data_end = decoded.find("\n\n")
                if data_end == -1:
                    data_end = decoded.find("\n")
                try:
                    payload = json.loads(decoded[data_start:data_end].strip())
                except json.JSONDecodeError:
                    continue
                if payload.get("type") == "snapshot":
                    snapshot_received.set()
                elif payload.get("type") == "delta":
                    events_received.append(payload)

        thread = threading.Thread(target=process_chunks, daemon=True)
        thread.start()

        assert snapshot_received.wait(timeout=5), "No snapshot received"
        # The keepalive proves the generator has passed the callback
        # registration, so an emit from here on cannot be dropped.
        assert keepalive_received.wait(timeout=5), "No keepalive after snapshot"

        event_manager.emit({
            "service_name": "test-sse-svc",
            "status": "running",
            "action": "start",
            "container_id": "c" * 12,
            "timestamp": time.time(),
        })

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not events_received:
            time.sleep(0.01)

        own = [e for e in events_received if e.get("service_name") == "test-sse-svc"]
        assert len(own) > 0, f"No delta events received: {events_received}"
        assert own[0]["status"] == "running"
        assert own[0]["action"] == "start"

    def test_sse_headers(self, client_and_services_path):
        """Verify that SSE endpoint sets proper headers."""
        client, _ = client_and_services_path
        response = client.get("/api/services/stream", headers=_auth_headers())
        assert response.status_code == 200
        assert "Cache-Control" in response.headers
        assert "no-cache" in response.headers.get("Cache-Control", "")
        assert "X-Accel-Buffering" in response.headers
        assert response.headers.get("X-Accel-Buffering") == "no"
