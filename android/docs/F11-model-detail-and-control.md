# F11 · Model detail, start and stop

**Mockup:** screen 10b (detail). Screen 10d (start conflict) is not
implemented — see the dropped F11-R5. · **Depends on:** F10

The one place the app touches the rig. Everything shares one GPU, so a
start that does not fit is the app's single genuinely dangerous action.

---

## F11-R1 · Detail screen (Must)

Tapping a service opens a detail screen: name, engine, status, host port,
model, model size, and — if exited — the exit code. Live from the same
services stream as the list.

**Acceptance criteria**

- [ ] Status on the detail screen tracks the container in real time.
- [ ] A service that stops while the screen is open updates in place.
- [ ] Navigating back and forward does not lose the live connection.

## F11-R2 · Read-only configuration (Should)

`GET /api/services/<name>` returns the stored config: `model_path` (llama.cpp),
`model_name` (vLLM), `params` (the CLI flag map), `template_type`, port
and computed `model_size`. Rendering the flags is useful when deciding
whether to start something.

**Strictly read-only.** No field is editable, and `api_key` — which is in
this payload too — is never shown.

**Acceptance criteria**

- [ ] Flags render as a readable list or as the equivalent command line.
- [ ] Nothing on the screen is editable and no PUT is ever issued.
- [ ] `api_key` does not appear.
- [ ] A service present in Docker but missing from `services.json` (404)
      shows a graceful partial view rather than an error screen.

## F11-R3 · Stop a container (Must)

`POST /api/services/<name>/stop`, behind a confirm naming the service.

Stopping a model that a chat is mid-answer on will kill that run. The
app **warns and allows** — it never refuses. On a single-user rig the
person tapping Stop is the person whose chat dies, and they usually mean
it. The confirm's job is to make sure they know, not to argue.

**Acceptance criteria**

- [ ] The confirm names the service.
- [ ] The confirm warns that in-flight chats on that model will fail.
- [ ] Stopping a container while a chat is streaming on it **succeeds** —
      the app never blocks the action.
- [ ] The affected thread then shows the run's failure (F04-R8) rather
      than hanging on a stream that will never produce another token.
- [ ] After stopping, the status reaches `exited` in the list and detail
      without a manual refresh.
- [ ] A failed stop shows the server's error and leaves the status as it
      actually is.

## F11-R4 · Start a container (Must)

`POST /api/services/<name>/start`, behind the VRAM guard below.

**Acceptance criteria**

- [ ] Starting a service moves it to running and it becomes selectable in
      the chat model picker.
- [ ] A start that fails (bad flags, image missing, out of memory) shows
      the server's error, and the service does not appear running.
- [ ] The button shows a pending state while the request is in flight and
      cannot be double-fired.

## F11-R5 · The VRAM guard (DROPPED)

**Dropped at the owner's direction, 2026-07-25:** *"no vram guard. let it
fail if it fails. i'll see it in the logs."*

The guard was to compare `memory.free` from `GET /api/gpu` against the
target's `model_size` and show screen 10d's conflict dialog before
starting. It is not built.

The reasoning holds up: the estimate was necessarily rough — `model_size`
is weights on disk, with KV cache and CUDA graphs extra — so it would
have blocked starts that would have fit and waved through starts that did
not. On a single-user rig the owner watches, a failed start is visible in
`docker logs` within seconds and costs nothing but a retry. A dialog that
guesses wrong in both directions is worse than the honest failure.

**Consequence to keep in mind:** the server has no admission control, so
nothing now prevents an oversubscribed start. Starting a large model
while another large one runs will fail at the container, not in the app.
The app must surface that failure clearly (F11-R4) rather than appearing
to succeed.

Screen 10d (the start-conflict dialog) is therefore not implemented.

## F11-R6 · Restart (Should)

Restart is stop-then-start, as on the dashboard. There is no restart
endpoint.

**Acceptance criteria**

- [ ] Restart stops the container, waits for it to reach a stopped state,
      then starts it.
- [ ] A failure at either step is reported and does not leave the UI
      claiming success.

## F11-R7 · Readiness (Should)

vLLM takes one to three minutes to come up; a container reported
`running` is not yet answering. The app can watch the log stream (F12)
for the readiness line — `Uvicorn running on http://0.0.0.0:8000` for
vLLM, `HTTP server is listening` for llama.cpp — and show "starting"
until then.

This is in-app only, while the screen is open. Notifying when a model
becomes ready needs a background mechanism that does not exist — see
F09-R6 and Dropped-Features.

**Acceptance criteria**

- [ ] A vLLM service shows "starting" from `running` until its readiness
      line appears, then "ready".
- [ ] The chat model picker does not offer a service that is up but not
      yet ready, or marks it clearly.
- [ ] Leaving the screen mid-startup does not leave a stream running.

## F11-R8 · No configuration, ever (Must)

No create, no flag editing, no rename, no port or key changes, no delete,
no compose rebuild, no Open WebUI registration. The endpoints exist; the
app must not call them. A bad tap must not be able to corrupt
`services.json`.

**Acceptance criteria**

- [ ] The only service endpoints the app calls are `GET /api/services`,
      `GET /api/services/stream`, `GET /api/services/<name>`, the log
      endpoints, and `.../start` / `.../stop`.

---

## Endpoints used

| Method | Path |
|---|---|
| GET | `/api/services/<name>` |
| POST | `/api/services/<name>/start` |
| POST | `/api/services/<name>/stop` |
| GET | `/api/gpu` |

## Deviations from the mockup

- **No start-conflict dialog.** Screen 10d reads as though the VRAM
  numbers are exact; they never could be (F10-R4). The guard was dropped
  outright rather than shipped as a confident-looking guess — see F11-R5.

## Out of scope

- Anything that writes `services.json`.
- Benchmarks (`/api/benchmarks/*`).

## Verification notes

All Must criteria verified, most on device against the live rig. The
review reproduced the implementer's findings independently rather than
trusting them.

**One shared confirm path, structurally.** `ServiceControlController` is
a single sealed state machine (Idle / Confirming / InFlight / Failed).
Both `ModelsViewModel` (the row actions, F10-R5) and
`ModelDetailViewModel` hold an instance and only ever call
`requestStart` / `requestStop` / `confirm` / `dismiss`. Verified by grep:
the repository's `start`/`stop` are reached from exactly one place,
inside `confirm()`. There is no second path that could fire without a
confirm — which is the property F10-R5's "same confirmation path"
criterion actually wanted.

`InFlight` refuses a second request; the test asserts the state is
unchanged after a second `requestStart`, not that a button looked
disabled.

**Dropping the VRAM guard was exercised for real, twice.** With the GPU
at 94.1 / 95.6 GB, starting `llamacpp-gemma-4-26b-a4b-it-q8` (27 GB) from
the app failed in ~0.6 s with exit code 139 — a genuine `cudaMalloc
failed: out of memory` in `docker logs`. The app never showed "running"
at any point; it went straight back to "Exited (code 139)" live, with no
manual refresh. This is the behaviour the owner asked for in place of a
guard.

**The start confirm's wording was corrected.** It said *"you'll see the
error here"*. It will not: the screen only ever learns the **exit code**.
The reason lives in the container's log, which is exactly the split
F11-R5's own reasoning assumed. Now says the status shows the exit code
and the reason is in the logs.

**A long `model_path` broke the detail rows** — the label had `weight(1f)`
and the value none, so "Model path" wrapped one character per line. The
same failure mode as F10's GPU card, and neither was caught by a JVM test,
because layout is not what they measure. Fixed by swapping which side
takes the weight; confirmed on device against a real
`/hf-cache/hub/models--unsloth--…` path.

**Skipped, both Should**

| Item | Why |
|---|---|
| R6 · Restart | Deprioritised. A clean extension of the same controller if it is ever wanted. |
| R7 · Readiness | **Blocked on F12.** Readiness means watching the container log for the server's listening line, and no log-stream client exists until F12 builds one. Picked up there. |

**Rig state after review:** unchanged. `llamacpp-laguna-s-2.1-q4` and
`open-webui` running as before; `llamacpp-gemma-4-26b-a4b-it-q8` still
exited, its exit code moved 0 → 139 by the deliberate OOM tests. Every
action went through the app's own confirm → start/stop, never `docker`
directly and never a configuration endpoint.
