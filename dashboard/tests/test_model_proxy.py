import json
import socket
import threading
import pytest
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

from inspector.db import InspectorDB
from inspector.proxy import ServiceProxy
from model_proxy.proxy import PortProxy
from model_proxy.supervisor import ModelProxySupervisor


class _UpstreamHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass

    def _respond(self):
        path, _, query = self.path.partition("?")
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        if path == "/stream":
            return self._respond_stream()
        if path == "/slow":
            time.sleep(1.0)
        payload = {
            "method": self.command,
            "path": path,
            "query": query,
            "body": body.decode("utf-8", "replace"),
            "authorization": self.headers.get("Authorization"),
            "x_probe": self.headers.get("X-Probe"),
        }
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _respond_stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()
        for i in range(3):
            frame = f"data: frame-{i}\n\n".encode()
            self.wfile.write(f"{len(frame):x}\r\n".encode() + frame + b"\r\n")
            self.wfile.flush()
            time.sleep(0.15)
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _respond


def _serve(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class _Proxy:
    def __init__(self, allowed, **kwargs):
        self.proxy = PortProxy(lambda: allowed, listen_host="127.0.0.1",
                               listen_port=0, **kwargs)
        self.proxy.start()
        assert self.proxy.running

    def url(self, path=""):
        return f"http://127.0.0.1:{self.proxy.listen_port}{path}"

    def stop(self):
        self.proxy.stop()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()


def _error_code(response):
    return response.json()["error"]["code"]


def test_forwards_method_path_body_and_headers(upstream_port):
    with _Proxy({upstream_port: "svc"}) as p:
        resp = requests.post(
            p.url(f"/proxy/{upstream_port}/v1/chat/completions"),
            json={"model": "m", "messages": []},
            headers={"Authorization": "Bearer key-1", "X-Probe": "keep-me"},
            timeout=10,
        )
        assert resp.status_code == 200
        echoed = resp.json()
        assert echoed["method"] == "POST"
        assert echoed["path"] == "/v1/chat/completions"
        assert json.loads(echoed["body"]) == {"model": "m", "messages": []}
        assert echoed["authorization"] == "Bearer key-1"
        assert echoed["x_probe"] == "keep-me"


def test_preserves_query_string(upstream_port):
    with _Proxy({upstream_port: "svc"}) as p:
        resp = requests.get(p.url(f"/proxy/{upstream_port}/echo?a=1&b=two"), timeout=10)
        assert resp.json()["query"] == "a=1&b=two"


def test_forwards_root_as_slash(upstream_port):
    with _Proxy({upstream_port: "svc"}) as p:
        resp = requests.get(p.url(f"/proxy/{upstream_port}"), timeout=10)
        assert resp.json()["path"] == "/"


@pytest.fixture
def upstream_port():
    server = _serve(_UpstreamHandler)
    yield server.server_address[1]
    server.shutdown()
    server.server_close()

def test_bad_port_segments_rejected_400(upstream_port):
    with _Proxy({upstream_port: "svc"}) as p:
        for segment in ("abc", "0", "70000"):
            resp = requests.get(p.url(f"/proxy/{segment}/v1/models"), timeout=10)
            assert resp.status_code == 400
            assert _error_code(resp) == "model_proxy_bad_port"


def test_unconfigured_port_rejected_404(upstream_port):
    unclaimed = _free_port()
    with _Proxy({upstream_port: "svc"}) as p:
        resp = requests.get(p.url(f"/proxy/{unclaimed}/v1/models"), timeout=10)
        assert resp.status_code == 404
        assert _error_code(resp) == "model_proxy_port_not_allowed"


def test_non_proxy_path_rejected_404(upstream_port):
    with _Proxy({upstream_port: "svc"}) as p:
        resp = requests.get(p.url("/health"), timeout=10)
        assert resp.status_code == 404
        assert _error_code(resp) == "model_proxy_unknown_path"


def test_chunked_request_rejected_411(upstream_port):
    with _Proxy({upstream_port: "svc"}) as p:
        resp = requests.post(
            p.url(f"/proxy/{upstream_port}/v1/chat/completions"),
            data=iter([b'{"stream": true}']),
            timeout=10,
        )
        assert resp.status_code == 411
        assert _error_code(resp) == "model_proxy_length_required"


def test_error_paths_keep_connection_alive(upstream_port):
    with _Proxy({upstream_port: "svc"}) as p:
        session = requests.Session()
        resp = session.post(
            p.url("/proxy/99999/v1/chat/completions"),
            json={"a": 1}, timeout=10,
        )
        assert resp.status_code == 400
        resp = session.get(p.url(f"/proxy/{upstream_port}/echo"), timeout=10)
        assert resp.status_code == 200
        session.close()


def test_dead_upstream_is_502(upstream_port):
    dead = _free_port()
    with _Proxy({dead: "svc"}) as p:
        resp = requests.get(p.url(f"/proxy/{dead}/v1/models"), timeout=10)
        assert resp.status_code == 502
        assert _error_code(resp) == "upstream_unavailable"


def test_read_timeout_is_504(upstream_port):
    with _Proxy({upstream_port: "svc"}, upstream_timeout=(5, 0.2)) as p:
        resp = requests.get(p.url(f"/proxy/{upstream_port}/slow"), timeout=10)
        assert resp.status_code == 504
        assert _error_code(resp) == "upstream_timeout"


def test_sse_frames_arrive_incrementally(upstream_port):
    with _Proxy({upstream_port: "svc"}) as p:
        sock = socket.create_connection(("127.0.0.1", p.proxy.listen_port), timeout=5)
        sock.sendall(f"GET /proxy/{upstream_port}/stream HTTP/1.1\r\nHost: x\r\n\r\n".encode())
        arrivals = []
        buf = b""
        t0 = time.perf_counter()
        while b"frame-2" not in buf and time.perf_counter() - t0 < 5:
            chunk = sock.recv(4096)
            if not chunk:
                break
            arrivals.append((time.perf_counter(), chunk))
            buf += chunk
        sock.close()
    header_end = buf.find(b"\r\n\r\n")
    assert buf[:header_end].splitlines()[0].split()[1] == b"200"
    assert b"text/event-stream" in buf[:header_end]
    assert buf[header_end:].count(b"data: frame-") == 3
    assert arrivals[-1][0] - arrivals[0][0] > 0.2


def test_listing_serves_ports(upstream_port):
    with _Proxy({upstream_port: "svc"}) as p:
        resp = requests.get(p.url("/proxy"), timeout=10)
        assert resp.status_code == 200
        body = resp.json()
        assert body["proxy"]["listen_port"] == p.proxy.listen_port
        assert body["ports"] == [{"port": upstream_port, "alias": "svc"}]


def _write_services(path, entries):
    path.write_text(json.dumps(entries))


def test_supervisor_lifecycle_and_live_whitelist(tmp_path, upstream_port, monkeypatch):
    monkeypatch.setenv("LLM_DOCK_MODEL_PROXY_PORT", "0")
    monkeypatch.setenv("LLM_DOCK_MODEL_PROXY_BIND", "127.0.0.1")
    services = tmp_path / "services.json"
    _write_services(services, {"svc": {"port": upstream_port, "alias": "svc"}})
    supervisor = ModelProxySupervisor()
    supervisor.configure(services_path=str(services))
    supervisor.start()
    supervisor.start()
    status = supervisor.status()
    assert status["running"] and status["bind_error"] is None
    base = f"http://127.0.0.1:{status['listen_port']}"
    assert requests.get(
        f"{base}/proxy/{upstream_port}/echo", timeout=10
    ).status_code == 200
    dead = _free_port()
    _write_services(services, {"svc": {"port": upstream_port}, "late": {"port": dead}})
    assert supervisor.allowed_ports() == {upstream_port: "svc", dead: "late"}
    supervisor.stop_all()
    assert not supervisor.status()["running"]
    with pytest.raises(requests.ConnectionError):
        requests.get(f"{base}/proxy", timeout=10)


def test_inspect_chain_captures_stripped_path(tmp_path, upstream_port):
    listen = _free_port()
    db = InspectorDB(str(tmp_path / "inspector.db"))
    inspector = ServiceProxy(
        "svc", listen_port=listen, upstream_port=upstream_port, db=db,
        template_type="vllm", default_model="svc",
    )
    inspector.start()
    assert inspector.running
    with _Proxy({listen: "svc"}) as p:
        resp = requests.post(
            p.url(f"/proxy/{listen}/v1/chat/completions"),
            json={"model": "svc", "messages": [{"role": "user", "content": "hi"}]},
            timeout=10,
        )
        assert resp.status_code == 200
    captures, _total = db.list_captures(service="svc")
    assert len(captures) == 1
    assert captures[0].path == "/v1/chat/completions"
    inspector.stop()
