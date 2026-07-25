# Android chat client — design mockups

`chat-app-mockups.html` is a self-contained design proposal for a phone
client that chats with llm-dock's hosted models. Open it in any browser
(no build step, no external assets) or view it on a phone — the page is
responsive.

> **Status: validated design, superseded on specifics.**
> The screens were reviewed and signed off, and remain the reference for
> layout and visual language. The *requirements* now live in
> **`android/docs/Plan_TOC.md`** — scope, ground rules, the endpoint
> surface, and one file per feature with acceptance criteria.
> Where this page and the requirements disagree, **the requirements
> win**: several claims here turned out to be wrong about the API, and
> five features drawn here have since been cut. Both lists are below.

Scope of the proposal: a chat app with a small second tab for the rig.
Conversations stay on the server in `chat.db`, so threads are shared with
the React frontend at `:3399/v2`. No critic/sidekick, no benchmarks, no
project file editing, and **no service configuration** — the Models tab
can start, stop and observe, never create or edit.

## Screens

| # | Screen | Notes |
|---|--------|-------|
| 01 | Connect | Server URL + password or TOTP → 8 h sliding session (`auth.py`) |
| 02 | Conversations | List, model chip per thread, live "generating" dot |
| 03 | New chat sheet | Model / system prompt / tools |
| 04 | Streaming thread | Collapsed reasoning, tool-call cards, Stop |
| 05 | Rendered answer | Markdown, code + copy, tables |
| 06 | Composer, long-press actions | Attachments, edit-and-resend, delete |
| 07 | Model picker, tools sheet | Running/stopped locals + OpenRouter; per-chat MCP toggles |
| 08 | Reattach, offline | Background runs survive app close |
| 09 | Settings | Server, per-chat defaults, reading |
| 10 | Models tab | GPU header, running/stopped list, detail with read-only flags, streaming logs, VRAM guard before a start |

## API mapping

Every screen maps to an endpoint that exists today. Nothing in the
requirements needs new server code.

**Authentication — corrected.** An earlier version of this file named
`POST /api/totp/verify` as the login endpoint. That is **wrong**:
`/api/totp/verify` is TOTP *enrollment*, requires an already-valid token,
and writes the secret to config. The two real ways in, both returning
`{token, expires_in: 28800}`:

- `POST /api/auth/session` with `Authorization: Bearer <password>` — what
  the login page calls a password is `DASHBOARD_TOKEN` from
  `dashboard/.env`
- `POST /api/auth/login` with an `X-TOTP-Code: <6 digits>` header

Then `Authorization: Bearer <token>` on every other call. Sessions are
held in process memory, so a dashboard restart invalidates them all;
expiry slides 8 h on each request.

The rest:

- `GET|POST /api/chat/conversations`, `POST /api/chat/conversations/delete` — 02, 03
- `GET /api/chat/prompts`, `GET /api/chat/mcp-servers` — 03, 07b
- `POST /api/chat/conversations/<id>/messages` → run + SSE — 04, 05
- `PUT|DELETE …/messages/<id>` — 06b
- `POST /api/chat/conversations/<id>/cancel-active-run` — 04 (preferred over
  cancelling by run id: the server can always find a conversation's active
  run, and `expected_run_id` guards against a stale Stop)
- `GET /api/chat/runs/<id>/stream` (reattach + replay buffer) — 08a
- `GET /api/services` + `GET /api/chat/settings/openrouter-models` — 07a
- `GET /api/services`, `GET /api/services/stream`, `GET /api/gpu/stream` — 10a
- `GET /api/services/<name>` (config, flags, model size) — 10b
- `POST /api/services/<name>/start|stop` — 10a, 10b, 10d
- `GET /api/services/<name>/logs?tail=N`, `GET /api/services/<name>/logs/stream` — 10c

## Corrections to the drawn screens

Factual errors found while writing the requirements against the backend
source. The screens still show these; do not build them.

1. **Screen 01 — login endpoint.** As above.
2. **Screen 04 — "Partial text is kept" on Stop.** It is not. A cancelled
   run marks itself cancelled and saves **no** assistant message; the
   partial exists only in the client's buffer and vanishes on refetch. A
   *failed* run does persist its partial plus the error. The two are not
   alike.
3. **Screen 02 — last-line preview.** The conversation list endpoint
   returns conversation rows without messages, so a preview would cost one
   extra request per visible row. Rows show title, model chip and time.
4. **Screen 10a — per-container VRAM segments.** `nvidia-smi` is queried
   for device totals only; no per-process breakdown reaches the API. The
   only per-service number is weights-on-disk size, which is not resident
   VRAM.
5. **Screen 10a — per-service uptime.** The payload carries the
   container's creation time, not its last start, so "uptime" is wrong for
   anything that has been restarted.

## Decisions taken since sign-off

The mockups left several things marked "your call". They have been
answered:

- **No projects on the phone at all** — no grouping in the list (02), no
  project row in the new-chat sheet (03). Threads that belong to a project
  still open and work; the app just never mentions projects.
- **Follow the system theme** — the mockups' dark palette is the dark
  theme; a light one is derived from it.
- **Bottom navigation** — two tabs, as drawn.
- **Stopping a container is always allowed**, including one a chat is
  mid-answer on. The app warns; it never refuses.
- **No maths rendering in v1** — LaTeX shows as source rather than being
  silently stripped.
- **No notifications.** Screen 08b's headline feature needs server code
  that does not exist, so it is cut rather than deferred — along with
  conversation search, the tok/s readout, and the offline reading cache.

The full register, with reasons, is `android/docs/Dropped-Features.md`.

## Why leaving a screen doesn't cancel a run

That behaviour is what makes the reattach flow in screen 08 work. The
authoritative description is the source — `dashboard/chat/runtime.py`,
`run_manager.py` (`_sse_frames_for` is the wire format), and
`persistence.py`. The SSE frame table in
`android/docs/F04-chat-turn-and-streaming.md` documents the format as it
actually is.
