#!/usr/bin/env python3
import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from scenarios import NAMES, sessions


class FixtureState:
    def __init__(self):
        self.condition = threading.Condition()
        self.name = "empty"
        self.version = 0

    def select(self, name):
        if name not in NAMES:
            raise ValueError("unknown scenario")
        with self.condition:
            self.name = name
            self.version += 1
            self.condition.notify_all()

    def snapshot(self):
        with self.condition:
            return self.version, sessions(self.name)


class FixtureServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address):
        self.state = FixtureState()
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def respond(self, status, body):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/health":
            self.respond(200, {"status": "healthy"})
        elif path == "/api/auth/verify":
            self.respond(200, {"valid": True})
        elif path == "/api/pi/sessions":
            self.respond(200, {"sessions": self.server.state.snapshot()[1]})
        elif path == "/api/pi/sessions/stream":
            self.stream()
        elif path == "/__fixture/scenario":
            self.respond(200, {"scenario": self.server.state.name})
        else:
            self.respond(404, {"error": "fixture_path_not_supported"})

    def do_POST(self):
        path = urlsplit(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 4096:
                raise ValueError("invalid body length")
            raw = self.rfile.read(length)
            if path == "/api/auth/session":
                self.respond(200, {"token": "fixture-only-token", "expires_in": 28800})
            elif path == "/__fixture/scenario":
                self.server.state.select(json.loads(raw)["name"])
                self.respond(200, {"scenario": self.server.state.name})
            else:
                self.respond(404, {"error": "fixture_path_not_supported"})
        except (ValueError, KeyError, TypeError):
            self.close_connection = True
            self.respond(400, {"error": "invalid_fixture_request"})

    def send_frame(self, event, payload):
        raw = f"event: {event}\ndata: {json.dumps({'type': event, **payload})}\n\n".encode()
        self.wfile.write(f"{len(raw):x}\r\n".encode() + raw + b"\r\n")
        self.wfile.flush()

    def stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        state = self.server.state
        version, rows = state.snapshot()
        try:
            self.send_frame("snapshot", {"sessions": rows})
            while True:
                with state.condition:
                    changed = state.condition.wait_for(lambda: state.version != version, timeout=2)
                    next_version, rows = state.snapshot()
                if changed:
                    for row in rows:
                        self.send_frame("session", row)
                    version = next_version
                else:
                    raw = b": fixture heartbeat\n\n"
                    self.wfile.write(f"{len(raw):x}\r\n".encode() + raw + b"\r\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            return


def main():
    parser = argparse.ArgumentParser(description="Loopback-only Android Pi sessions fixture")
    parser.add_argument("--port", type=int, default=3999)
    args = parser.parse_args()
    if not 0 < args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    with FixtureServer(("127.0.0.1", args.port)) as server:
        print(f"Android Pi fixture ready on 127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
