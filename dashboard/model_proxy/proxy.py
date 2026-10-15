import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Dict, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# long generations legitimately take minutes; a shorter read timeout would kill a live stream
UPSTREAM_TIMEOUT = (10, 1800)

RELAY_CHUNK = 65535

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}

MAX_PORT = 65535


class _ProxyHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class PortProxy:
    def __init__(
        self,
        allowed_ports: Callable[[], Dict[int, str]],
        listen_host: str = "0.0.0.0",
        listen_port: int = 3388,
        upstream_host: str = "127.0.0.1",
        upstream_timeout: Tuple[float, float] = UPSTREAM_TIMEOUT,
    ) -> None:
        self.allowed_ports = allowed_ports
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.upstream_host = upstream_host
        self.upstream_timeout = upstream_timeout
        self._server: Optional[_ProxyHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._bind_error: Optional[str] = None

    def start(self) -> None:
        if self._server is not None:
            return
        self._bind_error = None
        try:
            self._server = _ProxyHTTPServer(
                (self.listen_host, self.listen_port), _make_handler(self)
            )
        except OSError as exc:
            self._bind_error = str(exc)
            logger.warning(
                "Model proxy could not bind %s:%s: %s",
                self.listen_host, self.listen_port, exc,
            )
            return
        self.listen_port = self._server.server_address[1]
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            kwargs={"poll_interval": 0.05},
            name="model-proxy",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        server, thread = self._server, self._thread
        self._server = None
        self._thread = None
        if server is None:
            return
        server.shutdown()
        server.server_close()
        if thread is not None:
            thread.join(timeout=5)

    @property
    def running(self) -> bool:
        return self._server is not None and self._thread is not None and self._thread.is_alive()

    @property
    def bind_error(self) -> Optional[str]:
        return self._bind_error


def _error_body(code: str, message: str) -> bytes:
    return json.dumps(
        {"error": {"message": message, "type": "invalid_request_error", "code": code}}
    ).encode("utf-8")


def _make_handler(proxy: PortProxy):
    class _Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args) -> None:
            logger.debug("model proxy: " + format, *args)

        def do_GET(self):
            self._handle()

        def do_POST(self):
            self._handle()

        def do_PUT(self):
            self._handle()

        def do_PATCH(self):
            self._handle()

        def do_DELETE(self):
            self._handle()

        def do_HEAD(self):
            self._handle()

        def do_OPTIONS(self):
            self._handle()

        def _send_json(self, status: int, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_error_json(self, status: int, code: str, message: str) -> None:
            self._send_json(status, _error_body(code, message))

        def _handle(self) -> None:
            if "chunked" in self.headers.get("Transfer-Encoding", "").lower():
                self.close_connection = True
                self._send_error_json(
                    411, "model_proxy_length_required",
                    "the model proxy requires Content-Length request bodies",
                )
                return
            request_body = self._request_body()
            path, _, query = self.path.partition("?")
            segments = path.split("/")
            if segments[1:2] != ["proxy"]:
                self._send_error_json(
                    404, "model_proxy_unknown_path",
                    "the model proxy only serves /proxy/<port>/<path>",
                )
                return
            if len(segments) <= 2 or segments[2] == "":
                self._send_json(200, self._listing_body())
                return
            port = _parse_port(segments[2])
            if port is None:
                self._send_error_json(
                    400, "model_proxy_bad_port",
                    f"'{segments[2]}' is not a port number in 1-{MAX_PORT}",
                )
                return
            if port not in proxy.allowed_ports():
                self._send_error_json(
                    404, "model_proxy_port_not_allowed",
                    f"port {port} is not a configured llm-dock service port",
                )
                return
            rest = "/" + "/".join(segments[3:])
            self._forward(port, rest, query, request_body)

        def _listing_body(self) -> bytes:
            return json.dumps({
                "proxy": {"listen_port": proxy.listen_port},
                "ports": [
                    {"port": port, "alias": alias}
                    for port, alias in sorted(proxy.allowed_ports().items())
                ],
            }).encode("utf-8")

        def _request_body(self) -> bytes:
            raw_length = self.headers.get("Content-Length")
            try:
                length = int(raw_length) if raw_length else 0
            except ValueError:
                length = 0
            if length <= 0:
                return b""
            return self.rfile.read(length)

        def _forward(self, port: int, rest: str, query: str, request_body: bytes) -> None:
            url = f"http://{proxy.upstream_host}:{port}{rest}"
            if query:
                url = f"{url}?{query}"
            request_headers = {
                name: value
                for name, value in self.headers.items()
                if name.lower() not in HOP_BY_HOP_HEADERS
            }
            request_headers["Host"] = f"{proxy.upstream_host}:{port}"
            try:
                upstream = requests.request(
                    self.command,
                    url,
                    headers=request_headers,
                    data=request_body,
                    stream=True,
                    timeout=proxy.upstream_timeout,
                    allow_redirects=False,
                )
            except requests.ConnectionError:
                self._send_error_json(
                    502, "upstream_unavailable",
                    f"no service is reachable on port {port}",
                )
                return
            except requests.Timeout:
                self._send_error_json(
                    504, "upstream_timeout", f"port {port} did not respond in time",
                )
                return

            response_headers = {
                name: value
                for name, value in upstream.headers.items()
                if name.lower() not in HOP_BY_HOP_HEADERS
            }
            content_length_out = next(
                (value for name, value in response_headers.items() if name.lower() == "content-length"),
                None,
            )
            try:
                declared_length = (
                    int(content_length_out) if content_length_out is not None else None
                )
            except ValueError:
                declared_length = None
            self.send_response(upstream.status_code)
            if content_length_out is None:
                self.send_header("Connection", "close")
                self.close_connection = True
            else:
                self.send_header("Content-Length", content_length_out)
            for name, value in response_headers.items():
                if name.lower() != "content-length":
                    self.send_header(name, value)
            self.end_headers()

            client_disconnected = False
            bytes_relayed = 0
            try:
                while True:
                    chunk = upstream.raw._fp.read1(RELAY_CHUNK)
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                        self.wfile.flush()
                        bytes_relayed += len(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        client_disconnected = True
                        logger.info(
                            "Client disconnected mid-relay for %s %s to port %s",
                            self.command, self.path, port,
                        )
                        break
            except Exception:
                self.close_connection = True
                logger.info(
                    "Relay failed for %s %s to port %s",
                    self.command, self.path, port, exc_info=True,
                )
            finally:
                upstream.close()
            if client_disconnected or (
                declared_length is not None and bytes_relayed < declared_length
            ):
                self.close_connection = True

    return _Handler


def _parse_port(segment: str) -> Optional[int]:
    if not segment.isascii() or not segment.isdigit():
        return None
    port = int(segment)
    return port if 1 <= port <= MAX_PORT else None
