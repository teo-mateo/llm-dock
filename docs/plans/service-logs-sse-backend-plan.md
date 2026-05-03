# Backend Plan: SSE Docker Service Logs

## Goal

Replace 3-second log polling with a backend SSE stream for Docker service logs, matching the existing authenticated `fetch()` + `ReadableStream` style used by `/api/gpu/stream` and `/api/services/stream`.

This plan covers backend changes only. The existing polling endpoint should remain available during the transition.

## Current State

- Existing log endpoint: `GET /api/services/<service_name>/logs?tail=200`
- Implementation: `dashboard/routes/services.py::get_service_logs`
- Behavior: resolves the compose service container with `get_service_container()`, reads `container.logs(tail=..., timestamps=True)`, returns JSON.
- Current SSE examples:
  - `GET /api/gpu/stream`
  - `GET /api/services/stream`
- Authentication uses `@require_auth`, so clients use `fetch()` with `Authorization: Bearer ...` rather than browser `EventSource`.

## Proposed Endpoint

Add:

```text
GET /api/services/<service_name>/logs/stream?tail=200&timestamps=true
```

Response:

```text
Content-Type: text/event-stream
Cache-Control: no-cache, no-transform
X-Accel-Buffering: no
```

Keep `GET /api/services/<service_name>/logs` unchanged for manual refresh, fallback, and compatibility.

## Event Contract

Use JSON payloads in `data:` frames, consistent with the existing services stream.

```text
data: {"type":"snapshot_start","service":"llamacpp-qwen","timestamp":"2026-05-03T...Z"}

data: {"type":"log","service":"llamacpp-qwen","line":"2026-05-03T... message text"}

data: {"type":"snapshot_end","service":"llamacpp-qwen","timestamp":"2026-05-03T...Z"}

: keepalive

data: {"type":"error","service":"llamacpp-qwen","message":"..."}
```

Recommended event types:

- `snapshot_start`: first event after connection is accepted.
- `log`: one complete log line. Keep the Docker timestamp inside `line` when `timestamps=true`.
- `snapshot_end`: sent after the initial tail has been drained. After this, subsequent `log` events are live follow output.
- `stream_end`: optional event when the container exits or Docker closes the log stream.
- `error`: recoverable stream or Docker read error.

Do not send raw multi-line log chunks as SSE data. Split Docker chunks into complete lines and JSON-encode each line so embedded characters are safe.

## Backend Implementation Steps

1. Add a small log streaming helper.
   - Suggested location: `dashboard/docker_utils.py` if kept minimal, or `dashboard/services/log_stream.py` if the route would otherwise get crowded.
   - Responsibilities:
     - Validate `tail`, clamp to a sane maximum like the current endpoint (`1000`).
     - Resolve the container with `get_service_container(service_name)`.
     - Read Docker logs with `stream=True`, `follow=True`, and `timestamps=True`.
     - Decode bytes as UTF-8 with replacement for invalid bytes.
     - Buffer partial chunks and emit complete lines.

2. Add the new route in `dashboard/routes/services.py`.
   - Decorate with `@require_auth`.
   - Return `404` JSON before opening the stream if the compose service has no container.
   - Return `text/event-stream` after validation succeeds.
   - Reuse the same SSE headers used by `gpu_stream`, including `no-transform`.

3. Avoid blocking keepalives behind Docker log reads.
   - Docker log streaming can block when the container is quiet.
   - Use a bounded `queue.Queue` and a daemon reader thread per SSE connection.
   - The reader thread pushes parsed log lines into the queue.
   - The Flask generator polls the queue with a timeout and yields `: keepalive\n\n` every few seconds when there are no lines.
   - On `GeneratorExit`, set a stop flag and close the Docker log generator if possible.

4. Handle lifecycle edge cases.
   - If the service has not been created, return `404` before starting SSE.
   - If the container is stopped, stream the requested tail and then send `stream_end`.
   - If Docker closes the stream unexpectedly, send `stream_end` or `error` depending on whether an exception occurred.
   - If the service is recreated while viewing logs, the current stream will naturally end with the old container; the frontend can reconnect to attach to the new one.

5. Format SSE frames through a shared local helper.
   - Example helper inside `services.py`:

```python
def _sse_data(payload):
    return "data: " + json.dumps(payload) + "\n\n"
```

   - Keep comments sparse and local to non-obvious concurrency cleanup.

6. Preserve current REST behavior.
   - Do not remove or alter `/api/services/<service_name>/logs`.
   - The legacy and React frontends can switch independently.

## Test Plan

Add focused backend tests, likely in a new `dashboard/tests/test_service_logs_sse.py`.

Test cases:

- unauthenticated requests to `/api/services/<service_name>/logs/stream` return `401`.
- nonexistent or not-created service returns `404` before streaming.
- successful response has `text/event-stream`.
- initial events include `snapshot_start`, at least one `log` event when mocked logs exist, and `snapshot_end`.
- `tail` is clamped to the same maximum as the existing logs endpoint.
- Docker read errors produce an `error` SSE payload rather than crashing the Flask response generator.

Mock Docker container access rather than requiring real Docker containers for unit tests. Keep any live Docker coverage separate from regular pytest runs.

## Acceptance Criteria

- Backend exposes `GET /api/services/<service_name>/logs/stream`.
- Endpoint requires the same Bearer token auth as existing service routes.
- Endpoint streams initial tail plus live appended log lines without 3-second polling.
- Endpoint sends keepalives while containers are quiet.
- Endpoint cleans up its Docker reader when the client disconnects.
- Existing JSON log endpoint remains intact.
- Backend tests cover auth, content type, event payloads, and basic error handling.
