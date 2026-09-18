import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from inspector.db import InspectorDB
from inspector.proxy import ServiceProxy
from inspector.redact import MAX_BODY_CHARS, REDACTED


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_rows(db, expected: int, timeout: float = 5.0) -> int:
    deadline = time.monotonic() + timeout
    total = 0
    while time.monotonic() < deadline:
        total = db.list_captures()[1]
        if total == expected:
            return total
        time.sleep(0.05)
    raise AssertionError(f"expected {expected} capture row(s), got {total}")


class Upstream(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass

    def _record(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self.server.state["requests"].append(
            {
                "method": self.command,
                "path": self.path,
                "headers": dict(self.headers),
                "body": body,
            }
        )
        return body

    def _send_json(self, payload, status: int = 200):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._record()
        if self.path == "/health":
            self._send_json({"status": "ok"})
        else:
            self._send_json({"object": "error", "message": "not found"})

    def do_POST(self):
        body = self._record()
        if self.path == "/v1/models":
            self._send_json([{"id": "m-1"}])
            return
        if self.path != "/v1/chat/completions":
            self._send_json({"ok": True})
            return
        try:
            payload = json.loads(body)
        except ValueError:
            payload = {}
        if not isinstance(payload, dict) or not payload.get("stream"):
            self._send_json(
                {
                    "id": "chatcmpl-1",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "hello from upstream"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
                }
            )
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        chunks = [
            b'data: {"choices": [{"delta": {"reasoning_content": "r1 "}, "index": 0}]}\n\n',
            b'data: {"choices": [{"delta": {"content": "hello"}, "index": 0}]}\n\n',
            b'data: {"choices": [{"delta": {"content": " from upstream"}, "index": 0}]}\n\n',
            b'data: {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}], '
            b'"usage": {"prompt_tokens": 2, "completion_tokens": 5, "total_tokens": 7}}\n\n',
            b"data: [DONE]\n\n",
        ]
        for i, chunk in enumerate(chunks):
            self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
            self.wfile.flush()
            if i < len(chunks) - 1:
                time.sleep(0.4)
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()
        self.server.state["stream_finished_at"] = time.monotonic()


@pytest.fixture
def upstream():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    server.state = {"requests": [], "stream_finished_at": None}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture
def inspector_db():
    return InspectorDB(":memory:")


@pytest.fixture
def proxy_env(upstream, inspector_db):
    port = _free_port()
    proxy = ServiceProxy(
        "llamacpp-test",
        listen_port=port,
        upstream_port=upstream.server_address[1],
        db=inspector_db,
        template_type="llamacpp",
        listen_host="127.0.0.1",
    )
    proxy.start()
    assert proxy.running
    yield proxy, inspector_db, f"http://127.0.0.1:{port}"
    proxy.stop()


class TestPassthrough:
    def test_get_health_proxies_through_and_writes_no_row(self, proxy_env, upstream):
        _, db, base = proxy_env
        resp = requests.get(base + "/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
        assert resp.headers["Content-Type"].startswith("application/json")
        assert db.list_captures()[1] == 0
        assert upstream.state["requests"][-1]["method"] == "GET"

    def test_post_models_writes_no_row(self, proxy_env):
        _, db, base = proxy_env
        resp = requests.post(
            base + "/v1/models",
            data="{}",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        assert db.list_captures()[1] == 0

    def test_get_completions_writes_no_row(self, proxy_env):
        _, db, base = proxy_env
        resp = requests.get(base + "/v1/chat/completions")
        assert resp.status_code == 200
        assert db.list_captures()[1] == 0

    def test_text_plain_post_writes_no_row(self, proxy_env):
        _, db, base = proxy_env
        resp = requests.post(
            base + "/v1/chat/completions",
            data="hello",
            headers={"Content-Type": "text/plain"},
        )
        assert resp.status_code == 200
        assert db.list_captures()[1] == 0


class TestNonStreamingCapture:
    def test_row_round_trips_every_field(self, proxy_env, upstream):
        _, db, base = proxy_env
        raw = json.dumps({"model": "qwen-test", "messages": [{"role": "user", "content": "hi"}]})
        resp = requests.post(
            base + "/v1/chat/completions",
            data=raw,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        _wait_for_rows(db, 1)
        row = db.get_capture(db.list_captures()[0][0].id)
        assert row.service_name == "llamacpp-test"
        assert row.model == "qwen-test"
        assert row.template_type == "llamacpp"
        assert row.method == "POST"
        assert row.path == "/v1/chat/completions"
        assert row.status_code == 200
        assert row.stream is False
        assert row.request_body == raw
        assert row.request_truncated is False
        assert row.response_text == "hello from upstream"
        assert row.finish_reason == "stop"
        assert row.prompt_tokens == 7
        assert row.completion_tokens == 3
        assert row.total_tokens == 10
        assert row.ttfb_ms is not None and row.ttfb_ms >= 0
        assert row.duration_ms is not None and row.duration_ms >= 0
        assert row.error is None
        assert upstream.state["requests"][-1]["body"] == raw.encode()

    def test_oversized_request_body_truncated_stored_full_upstream(self, proxy_env, upstream):
        _, db, base = proxy_env
        raw = json.dumps(
            {"model": "m", "messages": [{"role": "user", "content": "x" * (2 * 1024 * 1024)}]}
        )
        resp = requests.post(
            base + "/v1/chat/completions",
            data=raw,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        assert len(upstream.state["requests"][-1]["body"]) == len(raw.encode())
        _wait_for_rows(db, 1)
        row = db.get_capture(db.list_captures()[0][0].id)
        assert row.request_truncated is True
        assert len(row.request_body) <= MAX_BODY_CHARS + 64


class TestStreamingCapture:
    def test_first_chunk_reaches_client_before_upstream_finishes(self, proxy_env, upstream):
        _, db, base = proxy_env
        resp = requests.post(
            base + "/v1/chat/completions",
            data=json.dumps({"model": "m", "stream": True, "messages": []}),
            headers={"Content-Type": "application/json"},
            stream=True,
        )
        first_data_at = None
        for line in resp.iter_lines(chunk_size=1):
            if first_data_at is None and line.startswith(b"data:"):
                first_data_at = time.monotonic()
        resp.close()
        finished_at = upstream.state["stream_finished_at"]
        assert first_data_at is not None
        assert finished_at is not None
        assert first_data_at < finished_at

        _wait_for_rows(db, 1)
        row = db.get_capture(db.list_captures()[0][0].id)
        assert row.stream is True
        assert row.response_text == "hello from upstream"
        assert row.reasoning_text == "r1 "
        assert row.prompt_tokens == 2
        assert row.completion_tokens == 5
        assert row.total_tokens == 7
        assert row.finish_reason == "stop"

    def test_client_disconnect_still_persists_with_error(self, proxy_env):
        _, db, base = proxy_env
        resp = requests.post(
            base + "/v1/chat/completions",
            data=json.dumps({"model": "m", "stream": True, "messages": []}),
            headers={"Content-Type": "application/json"},
            stream=True,
        )
        for line in resp.iter_lines(chunk_size=1):
            if line.startswith(b"data:"):
                resp.close()
                break
        _wait_for_rows(db, 1)
        row = db.get_capture(db.list_captures()[0][0].id)
        assert row.error == "client disconnected"


class TestAuthorization:
    def test_forwarded_verbatim_and_redacted_in_capture(self, proxy_env, upstream):
        _, db, base = proxy_env
        resp = requests.post(
            base + "/v1/chat/completions",
            data=json.dumps({"model": "m", "messages": []}),
            headers={"Content-Type": "application/json", "Authorization": "Bearer key-abc"},
        )
        assert resp.status_code == 200
        assert upstream.state["requests"][-1]["headers"]["Authorization"] == "Bearer key-abc"
        _wait_for_rows(db, 1)
        row = db.get_capture(db.list_captures()[0][0].id)
        headers = row.request_headers_json
        assert headers["Authorization"] == REDACTED
        assert "key-abc" not in json.dumps(headers)


class TestFailurePaths:
    def test_upstream_down_returns_502_and_writes_row(self, proxy_env, upstream):
        _, db, base = proxy_env
        upstream.shutdown()
        upstream.server_close()
        resp = requests.post(
            base + "/v1/chat/completions",
            data=json.dumps({"model": "m", "messages": []}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 502
        assert resp.json()["error"]["type"] == "upstream_unavailable"
        _wait_for_rows(db, 1)
        row = db.get_capture(db.list_captures()[0][0].id)
        assert row.status_code == 502

    def test_db_failure_does_not_break_proxied_response(self, proxy_env, monkeypatch):
        _, db, base = proxy_env

        def boom(capture):
            raise RuntimeError("db on fire")

        monkeypatch.setattr(db, "insert_capture", boom)
        resp = requests.post(
            base + "/v1/chat/completions",
            data=json.dumps({"model": "m", "messages": []}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["choices"][0]["message"]["content"] == "hello from upstream"


class TestLifecycle:
    def test_bind_failure_sets_error_and_stop_is_idempotent(self, inspector_db):
        port = _free_port()
        blocker = socket.socket()
        blocker.bind(("127.0.0.1", port))
        proxy = ServiceProxy(
            "s1", listen_port=port, upstream_port=_free_port(),
            db=inspector_db, listen_host="127.0.0.1",
        )
        proxy.start()
        assert proxy.running is False
        assert proxy.bind_error
        proxy.stop()
        blocker.close()

        proxy.start()
        assert proxy.running is True
        assert proxy.bind_error is None
        proxy.stop()
        proxy.stop()

        second = ServiceProxy(
            "s2", listen_port=port, upstream_port=_free_port(),
            db=inspector_db, listen_host="127.0.0.1",
        )
        second.start()
        assert second.running is True
        second.stop()
