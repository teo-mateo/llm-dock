import json
import os
import sys
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

TEST_TOKEN = "test-token-sse-logs"


@pytest.fixture(autouse=True)
def set_env_vars():
    os.environ["DASHBOARD_TOKEN"] = TEST_TOKEN
    os.environ["COMPOSE_PROJECT_NAME"] = "llm-dock"


def _auth_headers():
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


@pytest.fixture
def client_and_services_path(tmp_path):
    compose_content = """services:
  # <<<<<<< BEGIN DYNAMIC
  test-svc:
    image: test
  # >>>>>>> END DYNAMIC

networks:
  llm-network:
    driver: bridge
"""
    compose_path = tmp_path / "docker-compose.yml"
    compose_path.write_text(compose_content)

    services_json = {
        "test-svc": {
            "alias": "test-svc",
            "port": 3301,
            "api_key": "test-key",
            "model_path": "/path/to/model.gguf",
            "template_type": "llamacpp",
            "params": {},
        }
    }
    services_path = tmp_path / "services.json"
    services_path.write_text(json.dumps(services_json))

    from app import create_app

    app = create_app(
        config={
            "TESTING": True,
            "COMPOSE_FILE": str(compose_path),
            "DASHBOARD_TOKEN": TEST_TOKEN,
        }
    )

    client = app.test_client()
    yield client, services_path


@pytest.fixture
def mock_container():
    """Return a mock Docker container with configurable logs()."""
    container = MagicMock()
    container.status = "running"
    return container


def _parse_sse_chunks(response):
    """Read all chunks from an SSE response and parse them into a list of
    (event_type, payload_dict) tuples.  Comment-only chunks (keepalives) are
    returned as ('comment', None)."""
    events = []
    for raw in response.response:
        text = raw.decode("utf-8")
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith(": "):
                events.append(("comment", None))
            elif line.startswith("data: "):
                payload = json.loads(line[len("data: "):])
                events.append((payload.get("type"), payload))
    return events


class TestLogsStreamAuth:
    def test_requires_auth(self, client_and_services_path):
        client, _ = client_and_services_path
        resp = client.get("/api/services/test-svc/logs/stream")
        assert resp.status_code == 401

    def test_missing_service_returns_404(self, client_and_services_path):
        client, _ = client_and_services_path
        resp = client.get(
            "/api/services/nonexistent/logs/stream", headers=_auth_headers()
        )
        assert resp.status_code == 404


class TestLogsStreamHeaders:
    def test_content_type(self, client_and_services_path, mock_container):
        mock_container.logs.return_value = iter([b"line1\n", b"line2\n"])
        with patch(
            "routes.services.get_service_container", return_value=mock_container
        ):
            client, _ = client_and_services_path
            resp = client.get(
                "/api/services/test-svc/logs/stream", headers=_auth_headers()
            )
        assert resp.status_code == 200
        assert resp.mimetype == "text/event-stream"

    def test_sse_headers(self, client_and_services_path, mock_container):
        mock_container.logs.return_value = iter([b"line1\n"])
        with patch(
            "routes.services.get_service_container", return_value=mock_container
        ):
            client, _ = client_and_services_path
            resp = client.get(
                "/api/services/test-svc/logs/stream", headers=_auth_headers()
            )
        assert "no-cache" in resp.headers.get("Cache-Control", "")
        assert resp.headers.get("X-Accel-Buffering") == "no"


class TestLogsStreamEvents:
    """Tests that verify correctness of SSE event payloads."""

    def _make_stream_resp(self, client, log_lines, tail=200, timestamps=True):
        """Helper: mock container, hit endpoint, return parsed events."""
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_container.logs.return_value = iter(log_lines)

        with patch(
            "routes.services.get_service_container", return_value=mock_container
        ):
            resp = client.get(
                f"/api/services/test-svc/logs/stream?tail={tail}&timestamps={timestamps}",
                headers=_auth_headers(),
            )
        return _parse_sse_events(resp)

    def test_starts_with_snapshot_start(self, client_and_services_path):
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_container.logs.return_value = iter([b"hello\n"])

        with patch(
            "routes.services.get_service_container", return_value=mock_container
        ):
            client, _ = client_and_services_path
            resp = client.get(
                "/api/services/test-svc/logs/stream", headers=_auth_headers()
            )
        events = _parse_sse_events(resp)
        types = [e[0] for e in events]
        assert "snapshot_start" in types
        start_event = [e for e in events if e[0] == "snapshot_start"][0]
        assert start_event[1]["service"] == "test-svc"

    def test_log_lines_emitted(self, client_and_services_path):
        mock_container = MagicMock()
        mock_container.status = "running"
        lines = [
            b"2026-05-03T10:00:00Z log line A\n",
            b"2026-05-03T10:00:01Z log line B\n",
        ]
        mock_container.logs.return_value = iter(lines)

        with patch(
            "routes.services.get_service_container", return_value=mock_container
        ):
            client, _ = client_and_services_path
            resp = client.get(
                "/api/services/test-svc/logs/stream", headers=_auth_headers()
            )
        events = _parse_sse_events(resp)
        log_events = [e for e in events if e[0] == "log"]
        assert len(log_events) == 2
        assert log_events[0][1]["line"].strip() == "2026-05-03T10:00:00Z log line A"
        assert log_events[1][1]["line"].strip() == "2026-05-03T10:00:01Z log line B"

    def test_snapshot_end_after_initial_tail(self, client_and_services_path):
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_container.logs.return_value = iter([
            b"line1\n",
            b"line2\n",
        ])

        with patch(
            "routes.services.get_service_container", return_value=mock_container
        ):
            client, _ = client_and_services_path
            resp = client.get(
                "/api/services/test-svc/logs/stream", headers=_auth_headers()
            )
        events = _parse_sse_events(resp)
        types = [e[0] for e in events]
        assert "snapshot_end" in types

    def test_tail_clamped_to_max(self, client_and_services_path):
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_container.logs.return_value = iter([])

        with patch(
            "routes.services.get_service_container", return_value=mock_container
        ):
            client, _ = client_and_services_path
            resp = client.get(
                "/api/services/test-svc/logs/stream?tail=99999",
                headers=_auth_headers(),
            )
        events = _parse_sse_events(resp)
        log_events = [e for e in events if e[0] == "log"]
        assert len(log_events) == 0

    def test_timestamps_param(self, client_and_services_path):
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_container.logs.return_value = iter([b"log message without timestamp\n"])

        with patch(
            "routes.services.get_service_container", return_value=mock_container
        ):
            client, _ = client_and_services_path
            resp = client.get(
                "/api/services/test-svc/logs/stream?timestamps=false",
                headers=_auth_headers(),
            )
        events = _parse_sse_events(resp)
        log_events = [e for e in events if e[0] == "log"]
        assert len(log_events) == 1

    def test_partial_line_buffering(self, client_and_services_path):
        """When Docker splits a log line across chunks, the helper should
        buffer and emit only complete lines."""
        mock_container = MagicMock()
        mock_container.status = "running"
        # "hello world\n" split mid-line
        chunks = [b"hello wor", b"ld\nsecond line\n"]
        mock_container.logs.return_value = iter(chunks)

        with patch(
            "routes.services.get_service_container", return_value=mock_container
        ):
            client, _ = client_and_services_path
            resp = client.get(
                "/api/services/test-svc/logs/stream", headers=_auth_headers()
            )
        events = _parse_sse_events(resp)
        log_events = [e for e in events if e[0] == "log"]
        assert len(log_events) == 2
        assert log_events[0][1]["line"].strip() == "hello world"
        assert log_events[1][1]["line"].strip() == "second line"

    def test_docker_read_error_emits_error_event(self, client_and_services_path):
        """When container.logs() raises during streaming, an error event
        is emitted instead of crashing."""
        mock_container = MagicMock()
        mock_container.status = "running"

        def failing_logs(*args, **kwargs):
            yield b"first line\n"
            raise OSError("connection reset")

        mock_container.logs.side_effect = failing_logs

        with patch(
            "routes.services.get_service_container", return_value=mock_container
        ):
            client, _ = client_and_services_path
            resp = client.get(
                "/api/services/test-svc/logs/stream", headers=_auth_headers()
            )
        events = _parse_sse_events(resp)
        log_events = [e for e in events if e[0] == "log"]
        error_events = [e for e in events if e[0] == "error"]
        assert len(log_events) == 1
        assert len(error_events) >= 1


def _parse_sse_events(resp):
    """Parse SSE response into list of (type, payload) tuples."""
    events = []
    for raw in resp.response:
        text = raw.decode("utf-8")
        lines = text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            if line.startswith("data: "):
                payload = json.loads(line[len("data: "):])
                events.append((payload.get("type"), payload))
            elif line.startswith(":"):
                events.append(("comment", None))
            i += 1
    return events
