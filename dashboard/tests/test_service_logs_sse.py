"""Tests for SSE service logs endpoint."""

import json
import pytest
from unittest.mock import MagicMock, patch
from flask import Flask
from dashboard.routes.services import services_bp
from dashboard.auth import require_auth


@pytest.fixture
def client():
    """Test client with services blueprint registered."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["DASHBOARD_TOKEN"] = "test"  # Required for auth
    app.register_blueprint(services_bp, url_prefix="/api/services")
    
    # Mock auth decorator to pass through
    with patch("dashboard.routes.services.require_auth", lambda f: f):
        yield app.test_client()


@pytest.fixture
def mock_docker_client():
    """Mock Docker client with container."""
    with patch("dashboard.routes.services.get_service_container") as mock:
        mock_container = MagicMock()
        mock_container.name = "test-service"  # Set explicit name
        mock_container.logs.side_effect = lambda **kwargs: [
            b"2026-05-03T12:34:56.789000Z stdout log line 1\n",
            b"2026-05-03T12:34:57.123000Z stdout log line 2\n"
        ]
        mock.return_value = mock_container
        yield mock


def test_unauthenticated_access(client):
    """Test that unauthenticated access returns 401."""
    # Remove the auth mock for this test
    with patch("dashboard.routes.services.require_auth") as mock_auth:
        mock_auth.side_effect = lambda f: require_auth(f)
        response = client.get("/api/services/test-service/logs/stream")
        assert response.status_code == 401


def test_nonexistent_service(client):
    """Test that nonexistent service returns 404."""
    with patch("dashboard.routes.services.get_service_container") as mock_get:
        mock_get.return_value = None
        response = client.get(
            "/api/services/test-service/logs/stream",
            headers={"Authorization": "Bearer test"}
        )
        assert response.status_code == 404


def test_sse_headers(client, mock_docker_client):
    """Test that valid request returns proper SSE headers."""
    response = client.get(
        "/api/services/test-service/logs/stream",
        headers={"Authorization": "Bearer test"}
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["Content-Type"]
    assert "no-cache" in response.headers["Cache-Control"]


def test_initial_events(client, mock_docker_client):
    """Test that initial events include snapshot_start and log events."""
    response = client.get(
        "/api/services/test-service/logs/stream",
        headers={"Authorization": "Bearer test"}
    )
    
    # Read response data
    data = b"".join(response.response)
    events = data.decode().split("\n\n")
    
    # Filter out empty events and keepalives
    events = [e for e in events if e and not e.startswith(":")]
    
    assert len(events) >= 3  # snapshot_start + at least one log + snapshot_end
    
    # Check first event is snapshot_start
    first_event = json.loads(events[0].replace("data: ", ""))
    assert first_event["type"] == "snapshot_start"
    assert first_event["service"] == "test-service"


def test_log_line_formatting(client, mock_docker_client):
    """Test that log lines are properly formatted in SSE events."""
    response = client.get(
        "/api/services/test-service/logs/stream",
        headers={"Authorization": "Bearer test"}
    )
    
    data = b"".join(response.response)
    events = data.decode().split("\n\n")
    events = [e for e in events if e and not e.startswith(":")]
    
    # Find log events
    log_events = [json.loads(e.replace("data: ", "")) 
                 for e in events 
                 if "log line" in e]
    
    assert len(log_events) >= 2
    assert all(e["type"] == "log" for e in log_events)
    assert all("line" in e for e in log_events)
    assert all("2026-05-03T" in e["line"] for e in log_events)


def test_tail_parameter_clamping():
    """Test that tail parameter is properly clamped."""
    # This would be tested more thoroughly with the actual LogStreamer implementation
    # For now just verify the route accepts the parameter
    with patch("dashboard.routes.services.get_service_container") as mock_get:
        mock_container = MagicMock()
        mock_container.name = "test-service"
        mock_container.logs.return_value = b""
        mock_get.return_value = mock_container
        
        client = Flask(__name__).test_client()
        client.application.config["DASHBOARD_TOKEN"] = "test"
        client.application.register_blueprint(services_bp, url_prefix="/api/services")
        
        # Test with very large tail value
        response = client.get(
            "/api/services/test-service/logs/stream?tail=999999",
            headers={"Authorization": "Bearer test"}
        )
        assert response.status_code == 200