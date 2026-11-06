#!/usr/bin/env python3
import argparse
import json
import os
import socket
import socketserver
import sys
import time
from http.server import BaseHTTPRequestHandler

DEFAULT_SOCKET = "~/.cache/pi-remote/pi-remote-spike.sock"
EVENTS = [
    {"seq": 1, "kind": "hello", "text": "event one"},
    {"seq": 2, "kind": "state", "text": "event two"},
    {"seq": 3, "kind": "bye", "text": "event three"},
]
EVENT_GAP = 1.0
HEARTBEAT_GAP = 5.0


def log(message):
    print(message, flush=True)


def clear_stale_socket(path):
    if not os.path.exists(path):
        return
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    probe.settimeout(1.0)
    try:
        probe.connect(path)
    except OSError:
        if os.path.exists(path):
            os.unlink(path)
            log(f"removed stale socket {path}")
    else:
        log(f"another server is listening on {path}")
        sys.exit(2)
    finally:
        probe.close()


def sse_frame(payload):
    return f"data: {json.dumps(payload)}\n\n".encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "pi-remote-spike/1"

    def log_message(self, fmt, *args):
        log(f"uds {fmt % args}")

    def do_POST(self):
        if self.path != "/hello":
            self._not_found()
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b""
        log(f"POST /hello body={raw.decode('utf-8', 'replace')}")
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            self._json({"ok": False, "error": f"invalid json: {exc}"}, status=400)
            return
        if not isinstance(body, dict):
            self._json({"ok": False, "error": "body must be an object"}, status=400)
            return
        self._json({**body, "ok": True, "server_time": time.time()})

    def do_GET(self):
        if self.path != "/events":
            self._not_found()
            return
        log("GET /events stream opened")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            for event in EVENTS:
                self._write(sse_frame(event))
                log(f"sent event seq={event['seq']}")
                time.sleep(EVENT_GAP)
            while True:
                self._write(b": heartbeat\n\n")
                log("sent heartbeat")
                time.sleep(HEARTBEAT_GAP)
        except (BrokenPipeError, ConnectionResetError, OSError) as exc:
            log(f"client disconnected: {type(exc).__name__}: {exc}")
        finally:
            log("GET /events stream closed")

    def _write(self, payload):
        self.wfile.write(payload)
        self.wfile.flush()

    def _json(self, payload, status=200):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        self.wfile.flush()

    def _not_found(self):
        self._json({"ok": False, "error": f"unknown path {self.path}"}, status=404)


class UnixHTTPServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def main():
    parser = argparse.ArgumentParser(description="pi-remote UDS transport probe stub")
    parser.add_argument("--socket", default=DEFAULT_SOCKET)
    args = parser.parse_args()

    path = os.path.expanduser(args.socket)
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, mode=0o700)
    clear_stale_socket(path)

    server = UnixHTTPServer(path, Handler)
    os.chmod(path, 0o600)
    log(f"listening on {path} (mode {oct(os.stat(path).st_mode & 0o777)})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("interrupted")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
