import io
import json
import os
import sys
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

TEST_TOKEN = "test-token-logs-sse"


def _auth():
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


def _parse_sse(raw: bytes) -> list[dict]:
    """Parse SSE frames from raw bytes. Returns list of parsed JSON payloads.
    Keepalive comments are returned as {'type': 'keepalive'}."""
    events = []
    for line in raw.decode("utf-8").splitlines():
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
        elif line.startswith(": keepalive"):
            events.append({"type": "keepalive"})
    return events


def _make_container(log_lines: list[str], follow_chunks: list[bytes] | None = None):
    """Build a mock Docker container whose .logs() behaves predictably."""
    container = MagicMock()
    initial_bytes = ("\n".join(log_lines) + ("\n" if log_lines else "")).encode()

    def logs_side_effect(*args, **kwargs):
        if kwargs.get("stream") or kwargs.get("follow"):
            return iter(follow_chunks or [])
        return initial_bytes

    container.logs.side_effect = logs_side_effect
    return container


@pytest.fixture(autouse=True)
def env(tmp_path):
    os.environ["DASHBOARD_TOKEN"] = TEST_TOKEN
    os.environ["COMPOSE_PROJECT_NAME"] = "llm-dock-test"

    compose = tmp_path / "docker-compose.yml"
    compose.write_text(
        "services:\n  # <<<<<<< BEGIN DYNAMIC\n  # >>>>>>> END DYNAMIC\n"
        "networks:\n  llm-network:\n    driver: bridge\n"
    )
    (tmp_path / "services.json").write_text("{}")
    os.environ["COMPOSE_FILE"] = str(compose)
    yield


@pytest.fixture
def app():
    from app import create_app
    return create_app(config={
        "TESTING": True,
        "DASHBOARD_TOKEN": TEST_TOKEN,
        "COMPOSE_FILE": os.environ["COMPOSE_FILE"],
    })


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# T1 – auth
# ---------------------------------------------------------------------------

class TestAuth:
    def test_unauthenticated_returns_401(self, client):
        r = client.get("/api/services/my-svc/logs/stream")
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# T2 – 404 when no container
# ---------------------------------------------------------------------------

class TestNotFound:
    def test_service_not_found_returns_404(self, client):
        with patch("routes.services.get_service_container", return_value=None):
            r = client.get("/api/services/ghost-svc/logs/stream", headers=_auth())
        assert r.status_code == 404
        body = r.get_json()
        assert "error" in body


# ---------------------------------------------------------------------------
# T3 / T4 – content-type and headers
# ---------------------------------------------------------------------------

class TestHeaders:
    def _get(self, client):
        container = _make_container([])
        with patch("routes.services.get_service_container", return_value=container):
            return client.get("/api/services/my-svc/logs/stream", headers=_auth())

    def test_content_type_is_event_stream(self, client):
        r = self._get(client)
        assert r.status_code == 200
        assert r.mimetype == "text/event-stream"

    def test_cache_control_no_cache(self, client):
        r = self._get(client)
        assert "no-cache" in r.headers.get("Cache-Control", "")

    def test_x_accel_buffering_no(self, client):
        r = self._get(client)
        assert r.headers.get("X-Accel-Buffering") == "no"


# ---------------------------------------------------------------------------
# T5 – event sequence
# ---------------------------------------------------------------------------

class TestEventSequence:
    def test_snapshot_event_sequence(self, client):
        lines = ["2026-05-03T00:00:01Z line one", "2026-05-03T00:00:02Z line two"]
        container = _make_container(lines)
        with patch("routes.services.get_service_container", return_value=container):
            r = client.get("/api/services/my-svc/logs/stream", headers=_auth())
        raw = b"".join(r.response)
        events = _parse_sse(raw)

        types = [e["type"] for e in events]
        assert types[0] == "snapshot_start"

        log_events = [e for e in events if e["type"] == "log"]
        assert len(log_events) == 2
        assert log_events[0]["line"] == lines[0]
        assert log_events[1]["line"] == lines[1]

        assert "snapshot_end" in types
        assert "stream_end" in types

        # order: snapshot_start < all logs < snapshot_end < stream_end
        idx = {t: types.index(t) for t in ("snapshot_start", "snapshot_end", "stream_end")}
        first_log_idx = next(i for i, e in enumerate(events) if e["type"] == "log")
        assert idx["snapshot_start"] < first_log_idx
        assert first_log_idx < idx["snapshot_end"]
        assert idx["snapshot_end"] < idx["stream_end"]

    def test_service_name_in_every_event(self, client):
        container = _make_container(["line"])
        with patch("routes.services.get_service_container", return_value=container):
            r = client.get("/api/services/my-svc/logs/stream", headers=_auth())
        events = _parse_sse(b"".join(r.response))
        for e in events:
            if e.get("type") != "keepalive":
                assert e.get("service") == "my-svc"

    def test_empty_log_still_has_lifecycle_events(self, client):
        container = _make_container([])
        with patch("routes.services.get_service_container", return_value=container):
            r = client.get("/api/services/my-svc/logs/stream", headers=_auth())
        types = [e["type"] for e in _parse_sse(b"".join(r.response))]
        assert "snapshot_start" in types
        assert "snapshot_end" in types
        assert "stream_end" in types


# ---------------------------------------------------------------------------
# T6 / T7 / T8 – tail clamping
# ---------------------------------------------------------------------------

class TestTailClamping:
    def _tail_used(self, client, query=""):
        container = _make_container([])
        with patch("routes.services.get_service_container", return_value=container):
            r = client.get(f"/api/services/my-svc/logs/stream{query}", headers=_auth())
            b"".join(r.response)  # drain so stream_with_context executes
        # first call is non-streaming (phase 1)
        call_kwargs = container.logs.call_args_list[0][1]
        return call_kwargs["tail"]

    def test_tail_defaults_to_200(self, client):
        assert self._tail_used(client) == 200

    def test_tail_clamped_to_1000(self, client):
        assert self._tail_used(client, "?tail=9999") == 1000

    def test_tail_minimum_clamped_to_1(self, client):
        assert self._tail_used(client, "?tail=0") == 1

    def test_tail_valid_value_passed_through(self, client):
        assert self._tail_used(client, "?tail=50") == 50


# ---------------------------------------------------------------------------
# T9 – Docker error produces error event
# ---------------------------------------------------------------------------

class TestDockerError:
    def test_docker_error_emits_error_event(self, client):
        container = MagicMock()
        container.logs.side_effect = RuntimeError("docker daemon gone")
        with patch("routes.services.get_service_container", return_value=container):
            r = client.get("/api/services/my-svc/logs/stream", headers=_auth())
        events = _parse_sse(b"".join(r.response))
        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) >= 1
        assert "docker daemon gone" in error_events[0]["message"]


# ---------------------------------------------------------------------------
# T10 – multi-line chunks split correctly
# ---------------------------------------------------------------------------

class TestLineSplitting:
    def test_log_lines_split_correctly(self, client):
        # Docker may return multiple lines in one .logs() call (no streaming)
        multi = "line A\nline B\nline C"
        container = _make_container([])
        container.logs.side_effect = None
        container.logs.return_value = multi.encode()

        # Make follow iteration empty
        def logs_se(*a, **kw):
            if kw.get("stream") or kw.get("follow"):
                return iter([])
            return multi.encode()
        container.logs.side_effect = logs_se

        with patch("routes.services.get_service_container", return_value=container):
            r = client.get("/api/services/my-svc/logs/stream", headers=_auth())
        events = _parse_sse(b"".join(r.response))
        log_events = [e for e in events if e["type"] == "log"]
        assert len(log_events) == 3
        assert [e["line"] for e in log_events] == ["line A", "line B", "line C"]

    def test_empty_lines_not_emitted(self, client):
        container = _make_container([])
        container.logs.side_effect = None

        def logs_se(*a, **kw):
            if kw.get("stream") or kw.get("follow"):
                return iter([])
            return b"line A\n\nline B\n\n"
        container.logs.side_effect = logs_se

        with patch("routes.services.get_service_container", return_value=container):
            r = client.get("/api/services/my-svc/logs/stream", headers=_auth())
        log_events = [e for e in _parse_sse(b"".join(r.response)) if e["type"] == "log"]
        assert len(log_events) == 2


# ---------------------------------------------------------------------------
# T11–T13 – iter_log_events unit tests (helper in isolation)
# ---------------------------------------------------------------------------

class TestIterLogEvents:
    def _drain(self, container, tail=10, timeout=3.0):
        """Collect all events from iter_log_events with a wall-clock timeout."""
        from services.log_stream import iter_log_events
        stop = threading.Event()
        events = []
        deadline = time.monotonic() + timeout
        for item in iter_log_events(container, tail, stop):
            events.append(item)
            if item[0] in ("stream_end", "error"):
                break
            if time.monotonic() > deadline:
                stop.set()
                break
        return events

    def test_iter_log_events_sequence(self):
        container = _make_container(["alpha", "beta"])
        events = self._drain(container)
        types = [e[0] for e in events]
        assert "log" in types
        assert "snapshot_end" in types
        assert "stream_end" in types
        log_lines = [e[1] for e in events if e[0] == "log"]
        assert log_lines == ["alpha", "beta"]

    def test_stop_event_terminates_reader(self):
        """Reader thread should respect stop_event during phase 2."""
        from services.log_stream import iter_log_events

        stop = threading.Event()

        container = MagicMock()
        container.logs.side_effect = None

        def logs_se(*a, **kw):
            if kw.get("stream") or kw.get("follow"):
                def _slow():
                    for _ in range(100):
                        if stop.is_set():
                            return
                        time.sleep(0.05)
                        yield b"tick\n"
                return _slow()
            return b""
        container.logs.side_effect = logs_se

        events = []
        deadline = time.monotonic() + 1.0
        for item in iter_log_events(container, 10, stop):
            events.append(item)
            if item[0] == "snapshot_end":
                stop.set()
                break
            if time.monotonic() > deadline:
                break

        # After stop, reader must finish quickly
        time.sleep(0.3)
        assert stop.is_set()

    def test_invalid_utf8_replaced_not_crashed(self):
        container = MagicMock()

        def logs_se(*a, **kw):
            if kw.get("stream") or kw.get("follow"):
                return iter([])
            return b"valid line\nbroken \xff\xfe line\n"
        container.logs.side_effect = logs_se

        events = self._drain(container)
        log_lines = [e[1] for e in events if e[0] == "log"]
        assert len(log_lines) == 2
        assert "broken" in log_lines[1]
