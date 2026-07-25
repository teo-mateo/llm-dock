# Dropped and deferred features

Everything the mockups show, or the web UI does, that is **not** in the
Android requirements — with the reason. Kept as a register so nothing
gets rediscovered as an oversight, and so reopening any of them is a
decision rather than a surprise.

Categories:

- **No endpoint** — would need new server code. Excluded by ground rule
  R-A.
- **Not in the web UI** — the dashboard doesn't do it either. Excluded by
  R-B.
- **Scope** — has an endpoint and a web equivalent, deliberately out of
  scope for a phone.
- **Deferred** — in scope in principle, not in v1.

---

## No endpoint

### Notification when an answer lands

*Mockup: screen 08b, and the decision table's "NEW" row.*

The mockup's own headline feature: a notification when a background run
finishes while the app is closed. Nothing on the dashboard notifies a
client, and there is no push registration endpoint. The alternatives are
new server code, or a foreground service polling the conversation list —
which R-A excludes.

This is the single item most worth reopening. It needs a small
dashboard-side addition, and it is the difference between an app and a
bookmark. See F09-R6.

### Notification when a starting model becomes ready

*Mockup: screen 10c notes.*

Same machinery, near-zero extra cost once the above exists. In-app
readiness detection, while the log screen is open, is kept as F11-R7.

### Failure notifications

A run that dies because a container fell over. Same machinery again.

---

## Not in the web UI

### Search over conversations

*Mockup: screen 02, "your call"; the decision table cuts it.*

There is no search endpoint, and the web sidebar has no conversation
search either. Client-side title filtering over one loaded page is half a
feature. Cut.

### Live tokens-per-second readout in the chat

*Mockup: screen 04, decision table "derived · keep".*

The web chat has no tok/s readout. Throughput numbers on the dashboard
come from a separate service-metrics panel that scrapes each container's
Prometheus endpoint (`/api/services/<name>/metrics`) — not from the chat
stream. Adding it to the phone chat would be the phone doing something
the web client does not. Cut under R-B; reopenable cheaply if you want
it in both.

### Offline reading cache

*Mockup: screen 08b, "your call"; decision table cuts it for v1.*

Caching the last N threads for reading without a connection. No web
equivalent, and it creates a second source of truth for message content.
Cut for v1.

### Whisper round-trip for voice input

*Mockup: screen 06a.*

No transcription endpoint exists. Android's own dictation is free and
needs no app feature at all — the system keyboard's microphone works in
the composer without a line of code, which is why voice does not appear
as a requirement.

### Biometric unlock

*Mockup: screen 01, "your call".*

No web equivalent. Deferred, recorded as F01-R8.

---

## Scope — endpoints and web features that stay off the phone

### Critic / sidekick

Requested out from the start. The endpoints
(`/api/chat/messages/<id>/critique`) and the web UI both exist. Threads
created on the phone send no `sidekick_service`; critiques run on the
desktop simply do not render on the phone.

### Spin-off conversations

*Decision table: cut.*

A desktop reading gesture — select text, spin off a floating window with
a taskbar. No phone equivalent. `POST /api/chat/spinoff` is never called.
Spin-offs created on the desktop open on the phone as ordinary threads.

### Project file browser and editor

The full filesystem API exists (`/api/chat/projects/<id>/files/*`) and
the web UI has a complete explorer with drag-and-drop, cut/copy/paste and
an editor with optimistic concurrency. Desktop work on a phone screen.
The model may still use the project file tools on a thread that has a
project (F08-R5); the phone never browses them itself.

### Projects, entirely

*Decision 3, 2026-07-25. Mockup: screens 02 and 03.*

The phone has no project concept at all — no grouping in the conversation
list, no project row in the new-chat sheet, no project names anywhere,
and `GET /api/chat/projects` is never called. The conversation list is
flat.

This is broader than the mockups proposed: screen 02 drew collapsible
project headers and screen 03 drew a project row, both marked "your
call". Both are out.

Threads that belong to a project keep working: created on the desktop,
they appear in the flat list, open normally, and their model still gets
the project-scoped file tools the server wires up (F08-R5). The phone
simply never says the word "project".

### Creating, editing and deleting prompts

Managed prompts are read-only on the phone (F03-R2). They are
dashboard-managed.

### Service configuration

No create, edit, rename, delete, port change, public-port change,
favourite toggle, Open WebUI registration, API key display or key
rotation. All have endpoints. A bad tap must not corrupt
`services.json`. See F11-R8.

### Benchmarks

`/api/benchmarks/*` exists and the dashboard has a whole benchmarking
page. Running `llama-bench` from a phone helps nobody.

### Editing server settings

The default system prompt, the curated OpenRouter list and the MCP
registry all have GET/PUT/DELETE endpoints and dashboard editors. The
phone reads them where it needs them (F03, F07, F08) and never writes.
See F00-R10.

### Service metrics panel

`/api/services/<name>/metrics` and `/slots` back the dashboard's metrics
charts. Not on the phone; the Models tab is status, control and logs.

---

## Deferred within scope

| Item | Where | Why not v1 |
|---|---|---|
| HTML artifacts rendered in a WebView | F05-R8 | A WebView per artifact. Open them on the desktop. |
| Maths rendering | F05-R7 | Decision 5: cut. Exists in the web UI, so parity would have allowed it, but it is a WebView or a native maths renderer per formula. LaTeX passes through as legible source instead. |
| Log search | F12-R6 | Buffer filtering, cheap to add later. |
| Syntax highlighting in code blocks | F05-R2 | A monospace block with a language label meets the requirement. |

Light theme is **not** on this list any more — decision 2 put both
palettes in v1, following the system theme (F00-R7).

---

## Corrections to the mockups

Recorded here because they are factual errors in an otherwise validated
design, and they will mislead anyone reading the mockups alone.

1. **Login endpoint.** Screen 01 and `docs/android/README.md` name
   `POST /api/totp/verify`. That endpoint is TOTP *enrollment* and
   requires an existing token. Login is `POST /api/auth/login` with an
   `X-TOTP-Code` header. See F01.
2. **"Partial text is kept" on Stop.** Screen 04 says cancelling keeps
   the partial answer. It does not — the server marks the run cancelled
   and saves no assistant message. Failed runs *do* persist their
   partial. See F04-R6 and F04-R8.
3. **Last-line preview in the conversation list.** Screen 02 draws one.
   The list endpoint returns conversation rows without messages. See
   F02.
4. **Per-container VRAM segments.** Screen 10a splits the VRAM bar by
   container. `nvidia-smi` is queried for device totals only; no
   per-process breakdown reaches the API. See F10-R4.
5. **Per-service uptime.** Screen 10a shows uptime; the payload carries
   the container's creation time, not its last start. See F10.
