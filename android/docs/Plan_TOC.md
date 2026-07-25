# llm-dock for Android — software requirements

Feature requirements for the native Android client. This file is the
entry point: the ground rules, the endpoint surface the app is allowed to
use, and the index of per-feature requirement documents.

These are **feature requirements**, not a technical design. They say what
the app must do and how you know it does it. Screen layout comes from the
validated mockups; architecture, module structure and library choices are
deliberately left open.

---

## 1. Scope

A phone client for chatting with llm-dock-hosted models, plus a small
second tab for looking at the rig.

**In scope**

- Chat: conversations, streaming turns, tools, model switching — all
  server-side in `chat.db`, so threads are shared with the web UI at
  `:3399/v2`.
- Models: read the service list, start/stop a container, watch its logs,
  see GPU load.

**Out of scope, permanently**

- Service configuration of any kind — no create, edit, delete, rename,
  port or key changes, no compose rebuild.
- Critic / sidekick, benchmarks, project file browsing and editing,
  spin-off conversations, editing the server's default system prompt, the
  OpenRouter list or the MCP registry.

Some of those exist in the web UI and have working endpoints. They are
still out — see [Dropped-Features.md](Dropped-Features.md) for each one
and why.

---

## 2. Ground rules

Three rules decided which mockup features survived into these
requirements. They apply to every change made from here on.

**R-A · Backend parity.** The app uses only endpoints that exist on the
dashboard today. No feature in this plan requires new server code. Any
mockup feature that needed a new endpoint was dropped, not deferred with
a promise.

**R-B · Web parity.** If the web UI at `/v2` does not do it, the phone
does not do it either. The two clients read and write the same `chat.db`;
divergence in behaviour is a bug source, not a feature.

**R-C · The mockups are the validated design.** `docs/android/chat-app-mockups.html`
(16 screens) has been reviewed and signed off. Every requirement below
cites the screen it comes from. Where a requirement contradicts a mockup —
because of R-A or R-B — it says so explicitly.

---

## 3. How to work through this plan

> The per-feature delivery loop — branch, verify, commit, PR, merge,
> notify — is in **`android/CLAUDE.md` → "How work proceeds"**. This
> section covers only how the plan itself is maintained.

- Work one feature file at a time, in the order of the index below. The
  order is a dependency order, not a preference: F01 gates everything,
  F04 gates F05/F06/F09.
- A feature is finished when **every Must requirement in its file is
  implemented and every acceptance criterion for those requirements has
  been verified on a device or emulator**. Should-priority items may be
  skipped; if they are, note it in the feature file.
- When a feature is finished, mark it `[DONE]` in the index table in
  section 6 of this file — put the marker in the Status column, and
  nowhere else, so the table stays the single progress view.
- Partially done work stays `[ ]`. Use `[WIP]` only while actively on it.
- If implementation forces a deviation from a requirement, edit the
  requirement in its feature file and say why in that file's *Deviations*
  section. Do not leave the plan describing something the app doesn't do.

### Requirement conventions

- Requirement IDs are `F<nn>-R<n>` and are stable — never renumber. To
  retire one, mark it *Withdrawn* in place.
- Priority:
  - **Must** — v1 does not ship without it.
  - **Should** — v1 should have it; drop only with a note.
  - **Later** — explicitly not v1. Written down so it isn't rediscovered
    as a surprise.
- Acceptance criteria are written as observable behaviour. "Verified"
  means someone drove the app and saw it, not that the code looks right.

---

## 4. Reference material

| What | Where |
|---|---|
| **Technical foundation** — architecture decisions, verified dependency set, testing strategy | [Architecture.md](Architecture.md) |
| Validated screen designs (16 screens) | `docs/android/chat-app-mockups.html` |
| Screen → endpoint map (see caveat below) | `docs/android/README.md` |
| Backend conventions, chat subsystem notes | `CLAUDE.md` (repo root) |
| Toolchain, build commands, emulator control | `android/CLAUDE.md` |

> **Caveat on `docs/android/README.md`:** its API mapping predates this
> plan and names `POST /api/totp/verify` as the login endpoint. That is
> wrong — see [F01](F01-connection-and-auth.md). Where the two disagree,
> this plan wins.

---

## 5. Endpoint surface

The complete set of endpoints the app is permitted to call. Anything not
in this table is out of scope by definition. All except `/api/health`
require `Authorization: Bearer <token>`.

### Auth

| Method | Path | Use |
|---|---|---|
| GET | `/api/health` | Unauthenticated reachability check for the server URL |
| POST | `/api/auth/login` | TOTP login — `X-TOTP-Code` header → `{token, expires_in}` |
| POST | `/api/auth/session` | Exchange a static dashboard token for a session token |
| POST | `/api/auth/verify` | Cheap "is my token still good" probe |

### Chat

| Method | Path | Use |
|---|---|---|
| GET | `/api/chat/conversations?limit&offset` | Conversation list, `updated_at DESC` |
| POST | `/api/chat/conversations` | Create — `main_service` required |
| GET | `/api/chat/conversations/<id>` | Full thread with messages |
| PUT | `/api/chat/conversations/<id>` | Update title, `main_service`, `mcp_servers_json`, `project_id` |
| DELETE | `/api/chat/conversations/<id>` | Delete one |
| POST | `/api/chat/conversations/delete` | Delete a batch — `{ids: [...]}` |
| POST | `/api/chat/conversations/<id>/messages` | Send a turn → SSE stream |
| PUT | `/api/chat/conversations/<id>/messages/<msg>` | Edit + re-run → SSE stream |
| DELETE | `/api/chat/conversations/<id>/messages/<msg>` | Delete a message |
| GET | `/api/chat/runs/<id>` | Run status |
| GET | `/api/chat/runs/<id>/stream` | Reattach to a live run, with replay |
| POST | `/api/chat/runs/<id>/cancel` | Cancel by run id |
| POST | `/api/chat/conversations/<id>/cancel-active-run` | Cancel by conversation (preferred) |
| GET | `/api/chat/prompts` | Managed system prompts |
| GET | `/api/chat/mcp-servers` | Available MCP tool servers |
| GET | `/api/chat/settings/openrouter-models` | Curated OpenRouter picker list |

Read-only use of `/api/chat/prompts` and the settings endpoints: the app
never POSTs, PUTs or DELETEs against them. `/api/chat/projects` is **not**
called at all — the phone has no project concept (decision 3).

### Models and rig

| Method | Path | Use |
|---|---|---|
| GET | `/api/services` | Service snapshot with live status |
| GET | `/api/services/stream` | SSE: snapshot then status deltas |
| GET | `/api/services/<name>` | Service config — model, flags, size |
| POST | `/api/services/<name>/start` | Start a container |
| POST | `/api/services/<name>/stop` | Stop a container |
| GET | `/api/services/<name>/logs?tail=N` | Log tail, one shot |
| GET | `/api/services/<name>/logs/stream?tail=N` | SSE log stream |
| GET | `/api/gpu` | GPU snapshot |
| GET | `/api/gpu/stream?interval=N` | SSE GPU stream |

---

## 6. Feature index

Mark completed features `[DONE]` in the Status column.

| # | Feature | File | Mockup screens | Status |
|---|---|---|---|---|
| F00 | Cross-cutting requirements | [F00-cross-cutting.md](F00-cross-cutting.md) | all | [DONE] |
| F01 | Connection and authentication | [F01-connection-and-auth.md](F01-connection-and-auth.md) | 01 | [WIP] — one Must criterion outstanding, see the feature file |
| F02 | Conversation list | [F02-conversation-list.md](F02-conversation-list.md) | 02 | [DONE] |
| F03 | Starting a conversation | [F03-new-conversation.md](F03-new-conversation.md) | 03 | [DONE] |
| F04 | Sending a turn and streaming the reply | [F04-chat-turn-and-streaming.md](F04-chat-turn-and-streaming.md) | 04, 06a | [ ] |
| F05 | Rendering assistant output | [F05-message-rendering.md](F05-message-rendering.md) | 05 | [ ] |
| F06 | Message actions | [F06-message-actions.md](F06-message-actions.md) | 06b | [ ] |
| F07 | Model selection | [F07-model-selection.md](F07-model-selection.md) | 07a | [ ] |
| F08 | Per-conversation tools | [F08-conversation-tools.md](F08-conversation-tools.md) | 07b | [ ] |
| F09 | Run continuity and reattachment | [F09-run-continuity.md](F09-run-continuity.md) | 08a, 08b | [ ] |
| F10 | Models tab — list and GPU header | [F10-models-list.md](F10-models-list.md) | 10a | [ ] |
| F11 | Model detail, start and stop | [F11-model-detail-and-control.md](F11-model-detail-and-control.md) | 10b, 10d | [ ] |
| F12 | Container logs | [F12-container-logs.md](F12-container-logs.md) | 10c | [ ] |
| F13 | Settings | [F13-settings.md](F13-settings.md) | 09 | [ ] |
| — | Dropped and deferred features | [Dropped-Features.md](Dropped-Features.md) | — | n/a |

---

## 7. Backend behaviour that shaped these requirements

Each of these is a real constraint discovered in the dashboard source,
not an assumption. They are repeated in the feature files where they
bite, and collected here so nothing rediscovers them the hard way.

1. **Login is `POST /api/auth/login` with an `X-TOTP-Code` header.**
   `POST /api/totp/verify` is TOTP *enrollment*, requires an existing
   token, and cannot be used to sign in.
2. **Session tokens live in a process-memory dict on the server.**
   Restarting the dashboard invalidates every token. A 401 is a normal
   event, not an error state.
3. **Sessions slide.** Every authenticated request pushes expiry out by
   8 h. An app used daily never sees a login screen again.
4. **SSE needs an `Authorization` header,** so a plain `EventSource`-style
   client will not work. The web UI reads the response body as a stream
   for exactly this reason.
5. **Model deltas are forwarded raw** — an OpenAI-compatible chunk, not a
   typed frame. Every other frame is `{"type": ...}`.
6. **`data: [DONE]` does not end the stream.** `message_saved` follows
   it, and `conversation_updated` (auto-title) can follow that. Tearing
   the connection down at `[DONE]` loses the title of every new thread.
7. **One active run per conversation.** A second send while one is
   running returns 409 and is rolled back.
8. **Leaving a thread does not cancel its run.** The server keeps
   generating and persists the reply. This is the reason the app is worth
   building.
9. **Deleting a message is refused (409) while a run is active.**
10. **Editing a message truncates the thread from that point** and
    re-runs. It is destructive.
11. **Conversations are written back through `mcp_servers_json`** — a JSON
    *string*. The `mcp_servers` array in the payload is read-only.
12. **The conversation list carries no message preview.** It returns
    conversation rows only; a last-line preview would need one fetch per
    row.
13. **There is no search endpoint and no notification endpoint.**
14. **`GET /api/chat/conversations` with `limit=-1`** returns the whole
    list as one consistent snapshot; offset paging over `updated_at DESC`
    can skip or duplicate rows as threads are touched.

---

## 8. Decisions taken

Settled 2026-07-25. Each is already folded into the feature file that
owns it; they are recorded here so the reasoning does not have to be
reconstructed later.

1. **Bottom navigation.** Two tabs, Chats and Models, on the two list
   screens only — as the mockups draw it. → F02-R7.
2. **Follow the system theme.** Both palettes, switching with the device.
   The mockups' dark palette is the dark theme; a light counterpart is
   derived from it. → F00-R7.
3. **No projects on the phone.** Chats only: no grouping in the list, no
   project row in the new-chat sheet, no `GET /api/chat/projects` call.
   Threads that belong to a project (created on the desktop) still open
   and work normally — they simply appear in the flat list, and their
   model keeps its project file tools. → F02-R6 and F03-R4 withdrawn,
   F08-R5.
4. **The phone may stop a container at any time,** including one a chat
   is mid-answer on. It warns; it does not refuse. → F11-R3.
5. **No maths rendering in v1.** LaTeX is shown verbatim rather than
   silently stripped. → F05-R7.
