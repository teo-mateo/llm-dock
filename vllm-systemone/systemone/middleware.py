import json
import os
import subprocess
import sys
import threading

import httpx
from starlette.types import ASGIApp, Receive, Scope, Send

ROUTES = frozenset({"/v1/systemone", "/v1/prewarm", "/v1/version"})
SHIM_HOST = "127.0.0.1"
SHIM_PORT = int(os.environ.get("SYSTEMONE_SHIM_PORT", "3000"))

CALIBRATION_DEFAULTS = {
    "READOUT_T": "0.85",
    "READOUT_NOUL_T": "1.829074",
    "READOUT_NOUL_BIAS": "0",
    "READOUT_TARGETED": "1",
    "READOUT_INSTR_STYLE": "pyrepr",
    "SHIM_STAGGER": "1",
}


def parse_serve_argv(argv: list[str]) -> dict:
    opts: dict[str, list[str]] = {}
    model = None
    tokens = argv[argv.index("serve") + 1:] if "serve" in argv else argv[1:]
    key = None
    for tok in tokens:
        if tok.startswith("--"):
            name, eq, value = tok.partition("=")
            key = name
            opts.setdefault(key, [])
            if eq:
                opts[key].append(value)
                key = None
        elif key is not None:
            opts[key].append(tok)
        elif model is None:
            model = tok
    return {
        "model": model or (opts.get("--model") or [None])[0],
        "served_names": opts.get("--served-model-name") or [],
        "api_keys": opts.get("--api-key") or [],
        "port": int((opts.get("--port") or ["8000"])[0]),
    }


class _Shim:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None

    def ensure(self) -> None:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return
            self._proc = subprocess.Popen(
                [sys.executable, "-m", "systemone.launcher", "--host", SHIM_HOST, "--port", str(SHIM_PORT)],
                env=self._env(),
            )

    @staticmethod
    def _env() -> dict:
        serve = parse_serve_argv(sys.argv)
        key = next(iter(serve["api_keys"]), "") or os.environ.get("VLLM_API_KEY", "")
        env = dict(os.environ)
        for name, value in CALIBRATION_DEFAULTS.items():
            env.setdefault(name, value)
        env.setdefault("TOKENIZER", serve["model"] or "")
        env["VLLM"] = f"http://127.0.0.1:{serve['port']}/v1"
        env["SYSTEMONE_BACKEND_MODEL"] = next(iter(serve["served_names"]), serve["model"] or "")
        env["SYSTEMONE_BACKEND_KEY"] = key
        env["SHIM_TOKEN"] = key
        return env


_shim = _Shim()


def _json_error(code: int, message: str) -> tuple[int, bytes]:
    return code, json.dumps({"error": {"code": code, "message": message}}).encode()


class SystemOne:
    """vLLM --middleware entry point.

    vLLM installs --middleware outside its own AuthenticationMiddleware, so
    requests reaching the intercepted routes have not been authenticated. The
    shim enforces the same key through SHIM_TOKEN; do not start it without one
    when vLLM runs with --api-key.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._client: httpx.AsyncClient | None = None
        _shim.ensure()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"].rstrip("/") not in ROUTES:
            await self.app(scope, receive, send)
            return

        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body"):
                break

        _shim.ensure()
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=f"http://{SHIM_HOST}:{SHIM_PORT}", timeout=600.0)

        headers = {
            name: value
            for name, value in ((k.decode("latin-1"), v.decode("latin-1")) for k, v in scope["headers"])
            if name.lower() in ("authorization", "content-type")
        }
        # shim.py answers 401 without draining the request body, so a reused
        # keep-alive connection parses that leftover body as the next request.
        headers["connection"] = "close"
        try:
            resp = await self._client.request(scope["method"], scope["path"], content=body, headers=headers)
            status, payload = resp.status_code, resp.content
        except httpx.ConnectError as e:
            status, payload = _json_error(503, f"systemone helper not reachable yet: {e}")
        except httpx.HTTPError as e:
            status, payload = _json_error(502, f"systemone helper dropped the request: {e!r}")

        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode())],
        })
        await send({"type": "http.response.body", "body": payload})
