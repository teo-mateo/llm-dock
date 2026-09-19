import json
import logging
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

import requests

from .db import MAX_CAPTURES, InspectorDB
from .models import Capture
from .redact import MAX_BODY_CHARS, redact_headers, truncate
from .sse_assembly import assemble_json, assemble_stream

logger = logging.getLogger(__name__)

MAX_CAPTURES_ROWS = MAX_CAPTURES

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

CAPTURED_PATHS = (
    "/v1/chat/completions",
    "/v1/completions",
    "/v1/embeddings",
    "/v1/responses",
    "/completion",
    "/completions",
    "/infill",
)

# long generations legitimately take minutes; a shorter read timeout would kill a live stream
UPSTREAM_TIMEOUT = (10, 1800)


class _ProxyHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class ServiceProxy:
    def __init__(
        self,
        service_name: str,
        listen_port: int,
        upstream_port: int,
        db: InspectorDB,
        template_type: str = "",
        listen_host: str = "0.0.0.0",
        upstream_host: str = "127.0.0.1",
        default_model: Optional[str] = None,
    ) -> None:
        self.service_name = service_name
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.upstream_host = upstream_host
        self.upstream_port = upstream_port
        self.db = db
        self.template_type = template_type
        self.default_model = default_model
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
                "Inspector proxy for '%s' could not bind %s:%s: %s",
                self.service_name, self.listen_host, self.listen_port, exc,
            )
            return
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            kwargs={"poll_interval": 0.05},
            name=f"inspector-proxy-{self.service_name}",
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


def _make_handler(proxy: ServiceProxy):
    class _Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args) -> None:
            logger.debug("inspector proxy %s: " + format, proxy.service_name, *args)

        def do_GET(self):
            self._forward()

        def do_POST(self):
            self._forward()

        def do_PUT(self):
            self._forward()

        def do_PATCH(self):
            self._forward()

        def do_DELETE(self):
            self._forward()

        def do_HEAD(self):
            self._forward()

        def do_OPTIONS(self):
            self._forward()

        def _request_body(self) -> bytes:
            raw_length = self.headers.get("Content-Length")
            try:
                length = int(raw_length) if raw_length else 0
            except ValueError:
                length = 0
            if length <= 0:
                return b""
            return self.rfile.read(length)

        def _upstream_url(self) -> str:
            return f"http://{proxy.upstream_host}:{proxy.upstream_port}{self.path}"

        def _persist_capture(
            self,
            status_code: int,
            request_body: bytes,
            response_bytes: bytes,
            seen_bytes: int,
            t_start: float,
            t_last: float,
            t_first: Optional[float],
            error: Optional[str],
        ) -> None:
            try:
                request_text = request_body.decode("utf-8", errors="replace")
                request_body_text, request_truncated = truncate(request_text)
                response_text_raw = response_bytes.decode("utf-8", errors="replace")
                response_body, response_text_truncated = truncate(response_text_raw)
                response_truncated = response_text_truncated or seen_bytes > MAX_BODY_CHARS

                payload = {}
                try:
                    parsed = json.loads(request_body_text) if request_body_text else None
                except ValueError:
                    parsed = None
                if isinstance(parsed, dict):
                    payload = parsed
                model = payload.get("model")
                if not isinstance(model, str) or not model:
                    model = proxy.default_model
                stream = bool(payload.get("stream"))

                assembled = assemble_stream(response_text_raw) if stream else assemble_json(response_text_raw)
                usage = assembled.get("usage")
                capture = Capture(
                    id=str(uuid.uuid4()),
                    service_name=proxy.service_name,
                    model=model,
                    template_type=proxy.template_type or None,
                    method=self.command,
                    path=self.path,
                    status_code=status_code,
                    stream=stream,
                    request_headers_json=redact_headers(dict(self.headers)),
                    request_body=request_body_text,
                    response_body=response_body,
                    response_text=assembled["text"] or None,
                    reasoning_text=assembled["reasoning"] or None,
                    tool_calls_json=json.dumps(assembled["tool_calls"]) if assembled["tool_calls"] else None,
                    finish_reason=assembled["finish_reason"],
                    prompt_tokens=usage.get("prompt_tokens") if usage else None,
                    completion_tokens=usage.get("completion_tokens") if usage else None,
                    total_tokens=usage.get("total_tokens") if usage else None,
                    ttfb_ms=int((t_first - t_start) * 1000) if t_first is not None else None,
                    duration_ms=int((t_last - t_start) * 1000),
                    error=error,
                    request_truncated=request_truncated,
                    response_truncated=response_truncated,
                )
                proxy.db.insert_capture(capture)
                proxy.db.trim(MAX_CAPTURES_ROWS)
            except Exception as exc:
                logger.warning(
                    "Inspector capture failed for %s %s %s: %s",
                    proxy.service_name, self.command, self.path, exc,
                    exc_info=True,
                )

        def _send_error_json(
            self,
            status: int,
            error_type: str,
            should_capture: bool,
            request_body: bytes,
            t_start: float,
        ) -> None:
            body = json.dumps(
                {
                    "error": {
                        "message": (
                            f"llm-dock inspector: upstream for {proxy.service_name} is not "
                            f"reachable on {proxy.upstream_host}:{proxy.upstream_port}"
                        ),
                        "type": error_type,
                    }
                }
            ).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            if should_capture:
                self._persist_capture(
                    status_code=status,
                    request_body=request_body,
                    response_bytes=body,
                    seen_bytes=len(body),
                    t_start=t_start,
                    t_last=t_start,
                    t_first=None,
                    error=error_type,
                )

        def _forward(self) -> None:
            request_body = self._request_body()

            path_no_query = self.path.partition("?")[0]
            content_type = self.headers.get("Content-Type", "").strip().lower()
            should_capture = (
                self.command == "POST"
                and path_no_query.endswith(CAPTURED_PATHS)
                and content_type.startswith("application/json")
            )

            upstream_headers = {
                name: value
                for name, value in self.headers.items()
                if name.lower() not in HOP_BY_HOP_HEADERS
            }
            upstream_headers["Host"] = f"{proxy.upstream_host}:{proxy.upstream_port}"

            t_start = time.perf_counter()
            try:
                upstream = requests.request(
                    self.command,
                    self._upstream_url(),
                    headers=upstream_headers,
                    data=request_body,
                    stream=True,
                    timeout=UPSTREAM_TIMEOUT,
                    allow_redirects=False,
                )
            except requests.ConnectionError:
                self._send_error_json(502, "upstream_unavailable", should_capture, request_body, t_start)
                return
            except requests.Timeout:
                self._send_error_json(504, "upstream_timeout", should_capture, request_body, t_start)
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

            self.send_response(upstream.status_code)
            if content_length_out is not None:
                self.send_header("Content-Length", content_length_out)
            else:
                self.send_header("Connection", "close")
                self.close_connection = True
            for name, value in response_headers.items():
                if name.lower() != "content-length":
                    self.send_header(name, value)
            self.end_headers()

            buffer = bytearray()
            seen_bytes = 0
            t_first: Optional[float] = None
            t_last = t_start
            client_disconnected = False
            try:
                for chunk in upstream.iter_content(chunk_size=None):
                    now = time.perf_counter()
                    if t_first is None:
                        t_first = now
                    t_last = now
                    try:
                        self.wfile.write(chunk)
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        client_disconnected = True
                        break
                    if len(buffer) < MAX_BODY_CHARS:
                        buffer.extend(chunk[: MAX_BODY_CHARS - len(buffer)])
                    seen_bytes += len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                client_disconnected = True
            finally:
                upstream.close()

            if client_disconnected:
                logger.info(
                    "Client disconnected mid-relay for %s %s on %s",
                    self.command, self.path, proxy.service_name,
                )
            if should_capture:
                self._persist_capture(
                    status_code=upstream.status_code,
                    request_body=request_body,
                    response_bytes=bytes(buffer),
                    seen_bytes=seen_bytes,
                    t_start=t_start,
                    t_last=t_last,
                    t_first=t_first,
                    error="client disconnected" if client_disconnected else None,
                )

    return _Handler
