import gzip
import json
import re
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
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
        if path in ("/stream", "/stream-close"):
            return self._respond_stream(chunked=path == "/stream")
        if path == "/slow":
            time.sleep(1.0)
        if path == "/gz":
            return self._respond_gzip()
        if path == "/truncate":
            self.send_response(200)
            self.send_header("Content-Length", "1000")
            self.end_headers()
            self.wfile.write(b"partial")
            self.wfile.flush()
            self.close_connection = True
            return
        payload = {
            "method": self.command,
            "path": path,
            "query": query,
            "body": body.decode("utf-8", "replace"),
            "authorization": self.headers.get("Authorization"),
            "x_probe": self.headers.get("X-Probe"),
            "connection": self.headers.get("Connection"),
            "te": self.headers.get("TE"),
        }
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _respond_gzip(self):
        raw = gzip.compress(b"hello world " * 20)
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _respond_stream(self, chunked):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        if chunked:
            self.send_header("Transfer-Encoding", "chunked")
        else:
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        for i in range(3):
            frame = f"data: frame-{i}\n\n".encode()
            if chunked:
                self.wfile.write(f"{len(frame):x}\r\n".encode() + frame + b"\r\n")
            else:
                self.wfile.write(frame)
            self.wfile.flush()
            time.sleep(0.15)
        if chunked:
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


def _raw_requests(port, payloads, stop_when, timeout=5):
    sock = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    arrivals = []
    buf = b""
    t0 = time.perf_counter()
    for payload in payloads:
        sock.sendall(payload)
    while not stop_when(buf) and time.perf_counter() - t0 < timeout:
        chunk = sock.recv(4096)
        if not chunk:
            break
        arrivals.append((time.perf_counter(), chunk))
        buf += chunk
    sock.close()
    return arrivals, buf


def _read_response(port, payload, timeout=5):
    sock = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    sock.sendall(payload)
    buf = b""
    while True:
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            break
        if not chunk:
            break
        buf += chunk
        header_end = buf.find(b"\r\n\r\n")
        if header_end >= 0:
            match = re.search(rb"content-length: (\d+)", buf[:header_end].lower())
            if match and len(buf) - header_end - 4 >= int(match.group(1)):
                break
    sock.close()
    return buf


def _split_responses(buf):
    return buf.split(b"HTTP/1.1 ")


@pytest.fixture
def upstream_port():
    server = _serve(_UpstreamHandler)
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


def test_forwards_method_path_body_and_headers(upstream_port):
    with _Proxy({upstream_port: "svc"}) as p:
        resp = requests.post(
            p.url(f"/proxy/{upstream_port}/v1/chat/completions"),
            json={"model": "m", "messages": []},
            headers={"Authorization": "Bearer key-1", "X-Probe": "keep-me",
                     "TE": "deflate"},
            timeout=10,
        )
        assert resp.status_code == 200
        echoed = resp.json()
        assert echoed["method"] == "POST"
        assert echoed["path"] == "/v1/chat/completions"
        assert json.loads(echoed["body"]) == {"model": "m", "messages": []}
        assert echoed["authorization"] == "Bearer key-1"
        assert echoed["x_probe"] == "keep-me"
        assert echoed["te"] is None


def test_preserves_query_string_and_root(upstream_port):
    with _Proxy({upstream_port: "svc"}) as p:
        resp = requests.get(p.url(f"/proxy/{upstream_port}/echo?a=1&b=two"), timeout=10)
        assert resp.json()["query"] == "a=1&b=two"
        resp = requests.get(p.url(f"/proxy/{upstream_port}"), timeout=10)
        assert resp.json()["path"] == "/"


def test_bad_port_segments_rejected_400(upstream_port):
    with _Proxy({upstream_port: "svc"}) as p:
        for segment in ("abc", "0", "70000", "3377x", "\xb2"):
            resp = requests.get(p.url(f"/proxy/{segment}/v1/models"), timeout=10)
            assert resp.status_code == 400, segment
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


def test_non_ascii_digit_port_segment_rejected_400(upstream_port):
    with _Proxy({upstream_port: "svc"}) as p:
        buf = _read_response(
            p.proxy.listen_port,
            b"GET /proxy/\xb2/v1/models HTTP/1.1\r\nHost: x\r\n\r\n",
        )
        assert buf.startswith(b"HTTP/1.1 400")
        assert b"model_proxy_bad_port" in buf


def test_chunked_request_rejected_411(upstream_port):
    with _Proxy({upstream_port: "svc"}) as p:
        resp = requests.post(
            p.url(f"/proxy/{upstream_port}/v1/chat/completions"),
            data=iter([b'{"stream": true}']),
            timeout=10,
        )
        assert resp.status_code == 411
        assert _error_code(resp) == "model_proxy_length_required"


def test_error_response_drains_body_and_keeps_connection_alive(upstream_port):
    with _Proxy({upstream_port: "svc"}) as p:
        arrivals, buf = _raw_requests(
            p.proxy.listen_port,
            [
                b"POST /proxy/99999/v1/chat/completions HTTP/1.1\r\n"
                b"Host: x\r\nContent-Length: 7\r\n\r\nabcdefg",
                f"GET /proxy/{upstream_port}/echo HTTP/1.1\r\nHost: x\r\n\r\n".encode(),
            ],
            lambda b: b.count(b"HTTP/1.1 ") >= 2,
        )
        responses = _split_responses(buf)[1:]
        assert len(responses) == 2
        assert responses[0].startswith(b"400")
        assert responses[1].startswith(b"200")


def test_post_to_listing_drains_body(upstream_port):
    with _Proxy({upstream_port: "svc"}) as p:
        _, buf = _raw_requests(
            p.proxy.listen_port,
            [
                b"POST /proxy HTTP/1.1\r\nHost: x\r\nContent-Length: 7\r\n\r\nabcdefg",
                b"GET /proxy HTTP/1.1\r\nHost: x\r\n\r\n",
            ],
            lambda b: b.count(b"HTTP/1.1 ") >= 2,
        )
        responses = _split_responses(buf)[1:]
        assert len(responses) == 2
        assert responses[0].startswith(b"200")
        assert responses[1].startswith(b"200")


def _assert_frames_incremental(arrivals, buf):
    header_end = buf.find(b"\r\n\r\n")
    assert buf[:header_end].splitlines()[0].split()[1] == b"200"
    assert b"text/event-stream" in buf[:header_end]
    assert buf[header_end:].count(b"data: frame-") == 3
    assert len(arrivals) >= 3
    assert arrivals[-1][0] - arrivals[0][0] > 0.2


def _stream_probe(p, upstream_port, endpoint):
    arrivals, buf = _raw_requests(
        p.proxy.listen_port,
        [f"GET /proxy/{upstream_port}/{endpoint} HTTP/1.1\r\nHost: x\r\n\r\n".encode()],
        lambda b: b"frame-2" in b,
    )
    return arrivals, buf


def test_sse_frames_arrive_incrementally_chunked(upstream_port):
    with _Proxy({upstream_port: "svc"}) as p:
        arrivals, buf = _stream_probe(p, upstream_port, "stream")
        _assert_frames_incremental(arrivals, buf)


def test_sse_frames_arrive_incrementally_close_delimited(upstream_port):
    with _Proxy({upstream_port: "svc"}) as p:
        arrivals, buf = _stream_probe(p, upstream_port, "stream-close")
        _assert_frames_incremental(arrivals, buf)


def test_gzip_body_reaches_client_undecoded(upstream_port):
    with _Proxy({upstream_port: "svc"}) as p:
        buf = _read_response(
            p.proxy.listen_port,
            (f"GET /proxy/{upstream_port}/gz HTTP/1.1\r\nHost: x\r\n"
             "Accept-Encoding: gzip\r\n\r\n").encode(),
        )
        header_end = buf.find(b"\r\n\r\n")
        headers = buf[:header_end].lower()
        body = buf[header_end + 4:]
        assert b"content-encoding: gzip" in headers
        assert body.startswith(b"\x1f\x8b")
        assert f"content-length: {len(body)}".encode() in headers
        assert gzip.decompress(body) == b"hello world " * 20


def test_upstream_dying_mid_body_closes_connection(upstream_port):
    with _Proxy({upstream_port: "svc"}) as p:
        sock = socket.create_connection(("127.0.0.1", p.proxy.listen_port), timeout=5)
        t0 = time.perf_counter()
        sock.sendall(
            f"GET /proxy/{upstream_port}/truncate HTTP/1.1\r\nHost: x\r\n\r\n".encode()
        )
        buf = b""
        while time.perf_counter() - t0 < 3:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        sock.close()
        assert b"content-length: 1000" in buf[:buf.find(b"\r\n\r\n")].lower()
        assert b"partial" in buf
        assert time.perf_counter() - t0 < 2.0


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


def test_listing_serves_ports(upstream_port):
    with _Proxy({upstream_port: "svc"}) as p:
        resp = requests.get(p.url("/proxy"), timeout=10)
        assert resp.status_code == 200
        body = resp.json()
        assert body["proxy"]["listen_port"] == p.proxy.listen_port
        assert body["ports"] == [{"port": upstream_port, "alias": "svc"}]


@pytest.fixture
def supervisor(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_DOCK_MODEL_PROXY_PORT", "0")
    monkeypatch.setenv("LLM_DOCK_MODEL_PROXY_BIND", "127.0.0.1")
    services = tmp_path / "services.json"
    services.write_text("{}")
    sup = ModelProxySupervisor()
    sup.configure(services_path=str(services))
    yield sup, services
    sup.stop_all()


def _base(sup):
    return f"http://127.0.0.1:{sup.status()['listen_port']}"


def test_supervisor_lifecycle(supervisor, upstream_port):
    sup, services = supervisor
    services.write_text(json.dumps({"svc": {"port": upstream_port, "alias": "svc"}}))
    sup.start()
    sup.start()
    status = sup.status()
    assert status["running"] and status["bind_error"] is None
    base = _base(sup)
    assert requests.get(f"{base}/proxy/{upstream_port}/echo", timeout=10).status_code == 200
    sup.stop_all()
    assert not sup.status()["running"]
    with pytest.raises(requests.ConnectionError):
        requests.get(f"{base}/proxy", timeout=10)


def test_supervisor_whitelist_follows_rewrite_through_requests(supervisor, upstream_port):
    sup, services = supervisor
    services.write_text(json.dumps({"svc": {"port": upstream_port, "alias": "svc"}}))
    sup.start()
    base = _base(sup)
    assert requests.get(f"{base}/proxy/{upstream_port}/echo", timeout=10).status_code == 200
    replacement = f'{{"svc": {{"port": 40000, "alias": "svc"}}}}'
    assert len(replacement) == len(services.read_text())
    services.write_text(replacement)
    resp = requests.get(f"{base}/proxy/{upstream_port}/echo", timeout=10)
    assert resp.status_code == 404
    assert _error_code(resp) == "model_proxy_port_not_allowed"


def test_inspect_upstream_port_is_not_forwardable(supervisor):
    sup, services = supervisor
    server = _serve(_UpstreamHandler)
    try:
        services.write_text(json.dumps({
            "svc": {"port": _free_port(), "inspect_upstream_port":
                    server.server_address[1]},
        }))
        sup.start()
        resp = requests.get(
            f"{_base(sup)}/proxy/{server.server_address[1]}/echo", timeout=10
        )
        assert resp.status_code == 404
        assert _error_code(resp) == "model_proxy_port_not_allowed"
    finally:
        server.shutdown()
        server.server_close()


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


def test_no_capture_without_inspection(tmp_path, upstream_port):
    db = InspectorDB(str(tmp_path / "inspector.db"))
    with _Proxy({upstream_port: "svc"}) as p:
        resp = requests.post(
            p.url(f"/proxy/{upstream_port}/v1/chat/completions"),
            json={"model": "svc", "messages": []},
            timeout=10,
        )
        assert resp.status_code == 200
    captures, _total = db.list_captures(service="svc")
    assert captures == []
