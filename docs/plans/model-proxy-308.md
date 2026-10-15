# Model proxy by port (issue #308)

Expose configured model services through one fixed port on all local interfaces.

    http://<host>:3388/proxy/3301/v1/chat/completions
      -> http://localhost:3301/v1/chat/completions

## Decisions

- **Whitelist, not open relay.** The whitelist is the `port` field of each
  `services.json` entry, nothing else. `inspect_upstream_port` is excluded:
  whitelisting it lets clients bypass a running inspector proxy (silent
  no-capture traffic) and leaks the retained upstream ports of disabled
  inspection. A non-configured port gets `404` with the discriminated error
  body below. A stopped service stays whitelisted and yields 502, and the
  set-public-port window where services.json names the new port before the
  container is recreated 502s by the same rule — "services.json is the
  host-port authority".
- **Auth is pure pass-through.** The caller's `Authorization` header reaches
  the engine unchanged; the engine's per-service API key authenticates. No
  dashboard-token check on this port — it is meant to be pointed at like any
  OpenAI server.
- **Targets stay loopback.** Scheme and host are fixed to
  `http://127.0.0.1:<port>`; the URL segment selects only the port number
  (integer in 1-65535, else 400).
- **Security posture.** 3388 adds no new exposure: every whitelisted port is
  already published on all interfaces with the same pass-through key. Name the
  one that matters: ds4 services carry no API key, so through 3388 they are
  anonymous inference on a well-known port, and `GET /proxy` discloses the
  port list unauthenticated. Binding is IPv4 `0.0.0.0` ("all local interfaces"
  in the issue's sense); `::1` is not served — document it.
- **Not a capture proxy.** No persistence. With `inspect` on, the service's
  public port is served by the inspector's `ServiceProxy`, so traffic flows
  `3388 -> inspector proxy -> container` and is captured. The capture records
  the *stripped* path and this proxy's own headers, not the client's, so an
  Inspector row cannot be distinguished from direct traffic to the service's
  public port. Accepted; the service filter still keys on service name.
- **Runs in the dashboard process**, as a stdlib `ThreadingHTTPServer` bound to
  `0.0.0.0:3388`, following the `inspector/proxy.py` precedent exactly,
  including its limitations: bind failure is recorded (`bind_error`) and
  logged, never fatal. Before starting, cross-check the configured port
  against services.json and log the owning service name on collision.

## Layout

    dashboard/model_proxy/
    ├── __init__.py
    ├── proxy.py        # PortProxy: ThreadingHTTPServer, forwards /proxy/<port>/<rest>
    └── supervisor.py   # model_proxy_supervisor singleton: start / stop_all / status

Port and bind from env: `LLM_DOCK_MODEL_PROXY_PORT` (default `3388`) and
`LLM_DOCK_MODEL_PROXY_BIND` (default `0.0.0.0`). Conftest must default
`LLM_DOCK_MODEL_PROXY_PORT=0` alongside the existing hermetic env set, or any
test importing `app` binds the developer's real 3388 (`app.py` calls
`create_app()` at import time). `create_app()` may run twice under pytest:
`start()` must be idempotent for an already-running listener, as the
inspector's `start()` is.

`app.py`: start through the supervisor in `create_app()` (next to
`proxy_supervisor.configure/sync`) and `atexit.register(stop_all)`.

Allowed ports resolve per request by reading `services.json` directly (module
helper: `json.load` + mtime check), **without** `SERVICES_DB_LOCK`: writers
commit via temp-file + `os.replace`, so an unlocked read sees old-or-new, and
the lock is held across compose validation that can take seconds. Do not
construct a `ComposeManager` per request — it builds a Jinja environment and
raises `FileNotFoundError`. The eventual TTL cache must be invalidated from
the write paths (the routes that already call `proxy_supervisor.sync()` call
the model-proxy hook too), not on a blind timer, so a set-public-port never
leaves a staleness window.

## Forwarding contract

- Methods GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS.
- Request: strip the `/proxy/<port>` prefix, keep path and query verbatim,
  forward all headers except hop-by-hop and `Host` (rewritten to
  `127.0.0.1:<port>`). Body: read `Content-Length` bytes, as the inspector's
  `_request_body` does. A request with `Transfer-Encoding: chunked` is
  rejected with `411` — the inspector precedent treats a missing length as a
  zero-length body, and silently forwarding an empty body is data loss.
  `Expect: 100-continue` works for free (`handle_expect_100` answers before
  the body is read). No `Via`/`X-Forwarded-*` are added; byte-forwarding
  posture, like the precedent.
- Response: status + headers minus hop-by-hop (`Connection`, `Keep-Alive`,
  `Proxy-Authenticate`, `Proxy-Authorization`, `TE`, `Trailer`,
  `Transfer-Encoding`, `Upgrade`), following `inspector/proxy.py`'s body
  framing exactly: forward upstream `Content-Length`/`Content-Encoding`
  verbatim and stream with `iter_raw` (raw bytes — `iter_content` would
  decompress a gzipped body while relabelling it), and when upstream gives no
  `Content-Length`, respond with `Connection: close` + `close_connection =
  True` and stream until EOF. No hand-rolled chunked framing;
  `BaseHTTPRequestHandler` never auto-chunks. SSE frames arrive as written
  because each chunk is `wfile.write` + `flush`.
- Timeouts: exactly the precedent's `(connect, read) = (10, 1800)`. Connect
  refused / DNS / other request failure -> `502`; read timeout -> `504` with
  `code: "upstream_timeout"`. `allow_redirects=False`.
- Client disconnect mid-stream: swallow `BrokenPipeError`, close the upstream
  response.
- Error bodies (all ours, all with `error.code`, all `application/json`,
  so clients can tell our rejection from an upstream one without parsing
  prose): non-`/proxy/...` paths and configured-but-wrong inner paths ->
  `404` `error.code: "model_proxy_port_not_allowed"` / upstream's own body
  respectively; malformed port segment -> `400`
  `error.code: "model_proxy_bad_port"`.
- `GET /proxy` lists the forwarded ports and aliases: unauthenticated, no
  secrets, so callers can discover the surface.

## Tests (no GPU, no Docker needed)

`dashboard/tests/test_model_proxy.py`, plus a manual smoke:

1. **Routing** (unit): prefix stripping, query-string preservation, port-number
   validation (`/proxy/abc/`, `/proxy/0/`, `/proxy/70000/` -> 400), non-`/proxy`
   path -> our 404.
2. **Integration**: a fake upstream `ThreadingHTTPServer` on an ephemeral port
   that echoes method/path/query/headers and can stream SSE; a scratch
   `services.json` entry carrying that port. Assert byte-forwarding,
   `Authorization` echo, hop-by-hop stripping, and the 411 on a chunked
   request.
3. **Whitelist**: configured port forwarded; another listening port that no
   service claims -> 404 with `error.code: model_proxy_port_not_allowed`;
   a service's `inspect_upstream_port` is **not** reachable as
   `/proxy/<upstream>/` (pins the upstream-port exclusion).
4. **Streaming**: upstream sends SSE frames with delays; the client observes
   them incrementally (not buffered until EOF).
5. **Upstream down** -> 502; upstream stalled past the read timeout -> 504
   with `code: upstream_timeout` (short injected timeout).
6. **Supervisor**: start binds, second `start()` is a no-op, `stop_all`
   releases the port, `status()` exposes `bind_error`; a services.json edit
   adding a port takes effect on the next request with no restart.
7. **Inspect interaction** (integration): chain model-proxy -> inspector proxy
   -> fake upstream; assert a capture row appears, records the stripped path,
   **and** no capture exists when inspection is off (the forward path is not
   accidentally proxying through a stale listener).

Manual smoke on this GPU-less host: run `scripts/mock-engine/mock_engine.py`
(a stdlib server answering `/v1/models`, `/health`, and one SSE
`/v1/chat/completions`) on a scratch port and add only a `services.json`
entry naming it — no compose rebuild (the proxy whitelist reads the DB, and
the phantom compose entry would only show as a never-starting service), then:

    curl -s http://localhost:3388/proxy/<port>/v1/models
    curl -sN -H "Authorization: Bearer <key>" -d '{"stream":true,...}' \
      http://localhost:3388/proxy/<port>/v1/chat/completions

The mock engine script also becomes the seed for future no-GPU e2e tests.

## Edge cases

- **set-public-port / rename / delete** need nothing: the whitelist is resolved
  per request from services.json, the single source of truth. The
  swap-before-recreate window 502s, per "services.json is the host-port
  authority".
- **Dashboard restart** while the proxy is up: same as the inspector's
  documented window (listener lives in the dashboard process); `create_app()`
  re-binds.
- **Port 3388 collides** with an existing service port: startup logs
  `bind_error` naming the owning service (cross-checked against services.json)
  and the dashboard continues; the operator moves the other service.
- **IPv6 clients** (`http://[::1]:3388/`) get connection refused; document the
  IPv4 bind in CLAUDE.md.

## Out of scope

WebSockets, chunked request bodies (rejected with 411), TLS, per-client rate
limiting, capture (the inspector owns that), IPv6 binding, and exposing the
proxy through Open WebUI.

## Work order

1. New branch from fresh `main`; conftest hermetic default
   `LLM_DOCK_MODEL_PROXY_PORT=0` lands in the same commit as the supervisor.
2. `model_proxy/proxy.py` + unit tests (routing, whitelist, hop-by-hop, 411).
3. Supervisor + `app.py` wiring + supervisor tests (idempotent start).
4. Integration tests with the fake upstream (streaming, 502/504, inspect chain
   incl. the inspect-off negative).
5. Mock-engine smoke script + manual verification on this host.
6. CLAUDE.md section (port table row, gotchas: whitelist + `inspect_upstream_port`
   exclusion, ds4 anonymous-through-3388, IPv4-only bind, swap-window 502) + PR.
