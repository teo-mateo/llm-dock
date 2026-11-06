import json
import logging
import os
import socketserver
import threading
from http.server import BaseHTTPRequestHandler
from typing import Any, Callable, Optional

from .contract import JsonResponse
from .socket_path import clear_stale_socket, ensure_directory

logger = logging.getLogger(__name__)

SERVER_READ_TIMEOUT = 5


class _UnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


class UdsListener:
    def __init__(
        self,
        socket_path: str,
        request_handler: Callable[[str, str, Any], JsonResponse],
    ) -> None:
        self.socket_path = os.path.expanduser(socket_path)
        self.request_handler = request_handler
        self._server: Optional[_UnixServer] = None
        self._thread: Optional[threading.Thread] = None
        self._bind_error: Optional[str] = None

    def start(self) -> None:
        if self._server is not None:
            return
        self._bind_error = None
        error = ensure_directory(self.socket_path)
        if error is not None:
            self._bind_error = error
            logger.error("pi remote: %s", error)
            return
        error = clear_stale_socket(self.socket_path)
        if error is not None:
            self._bind_error = error
            logger.warning("pi remote: %s", error)
            return
        try:
            server = _UnixServer(
                self.socket_path, _make_handler(self.request_handler)
            )
        except OSError as exc:
            self._bind_error = str(exc)
            logger.warning(
                "pi remote: could not bind %s: %s", self.socket_path, exc
            )
            return
        try:
            os.chmod(self.socket_path, 0o600)
        except OSError as exc:
            server.server_close()
            try:
                os.unlink(self.socket_path)
            except OSError:
                pass
            self._bind_error = f"cannot set socket mode: {exc}"
            logger.error("pi remote: %s", self._bind_error)
            return
        self._server = server
        self._thread = threading.Thread(
            target=server.serve_forever,
            kwargs={"poll_interval": 0.05},
            name="pi-remote-listener",
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
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.warning("pi remote: could not remove %s: %s", self.socket_path, exc)

    @property
    def running(self) -> bool:
        return (
            self._server is not None
            and self._thread is not None
            and self._thread.is_alive()
        )

    @property
    def bind_error(self) -> Optional[str]:
        return self._bind_error


def _make_handler(request_handler: Callable[[str, str, Any], JsonResponse]):
    class _Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "llm-dock-pi-remote/1"
        timeout = SERVER_READ_TIMEOUT

        def log_message(self, format: str, *args) -> None:
            logger.debug("pi remote: " + format, *args)

        def _read_body(self) -> Any:
            raw_length = self.headers.get("Content-Length")
            try:
                length = int(raw_length) if raw_length else 0
            except ValueError:
                length = 0
            raw = self.rfile.read(length) if length > 0 else b""
            if not raw:
                return None
            try:
                return json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                return None

        def _handle(self) -> None:
            method = self.command
            body = self._read_body()
            path = self.path.split("?", 1)[0]
            response = request_handler(method, path, body)
            logger.info("pi remote %s %s -> %s", method, path, response.status)
            data = json.dumps(response.payload).encode("utf-8")
            self.send_response(response.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if method != "HEAD":
                self.wfile.write(data)

        do_POST = _handle
        do_GET = _handle
        do_PUT = _handle
        do_PATCH = _handle
        do_DELETE = _handle
        do_OPTIONS = _handle
        do_HEAD = _handle

    return _Handler
