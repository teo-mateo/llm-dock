# pi remote — chat with running pi sessions from the phone and the dashboard

Status: **high-level plan**, big building blocks only. Each block is refined in its
own pass before implementation. Written 2026-11-06.

Goal: every pi coding-agent session on this machine is visible from the llm-dock
Android app and the `/v2` dashboard, over the dashboard's existing internet-exposed
login. From there the user can read live output, send messages, stop a run, answer
pi's prompts (yes/no, choices, free text, approvals), switch model/thinking level,
and read the history after pi has exited. No third-party relay.

---

## 0. What was verified vs assumed

Verified against pi **1.0.4** (`/github/earendil-works/pi`, commit `eb326d265`, the
checkout `~/.nvm/.../bin/pi` symlinks to), in
`packages/coding-agent/src/core/extensions/types.ts` (cited as `types.ts:<line>`),
`runner.ts` and `docs/extensions.md`:

| Capability | API | Where |
|---|---|---|
| Session identity | `ctx.sessionManager.getSessionId()/getSessionFile()/getCwd()/getBranch()` | `session-manager.ts:245` (`ReadonlySessionManager`) |
| Lifecycle | `session_start {reason: startup\|reload\|new\|resume\|fork}`, `session_shutdown {reason}`, `session_info_changed {name}` | `types.ts:741-817` |
| Run lifecycle | `agent_start`, `turn_start/turn_end`, `agent_end`, `agent_before_settle`, `agent_settled` | `types.ts:930-1040` |
| Streaming text | `message_update {message, assistantMessageEvent}` (token-level), `message_start/message_end` | `types.ts:1045-1062` |
| Tools | `tool_execution_start/update/end` (args, partialResult, result, isError, durationMs) | `types.ts:1064-1099` |
| Model / thinking changes | `model_select`, `thinking_level_select` events; `pi.setModel(model)`, `pi.setThinkingLevel(level)`, `ctx.modelRegistry`, `ctx.scopedModels` | `types.ts:1104-1120`, ExtensionAPI |
| Send input | `pi.sendUserMessage(text \| (TextContent\|ImageContent)[], {deliverAs: "steer"\|"followUp", expandPromptTemplates})` — images supported; pi accepts both modes, llm-dock fixes `steer` (A2) | ExtensionAPI |
| Stop | `ctx.abort()`, `ctx.isIdle()`, `ctx.signal` | `types.ts:325-366` |
| Terminal dialogs | `ctx.ui.select/confirm/input/editor(…, {signal, timeout})` — **an AbortSignal dismisses the dialog** | `types.ts:114-160` |
| Prompt observation | `ui_prompt_start/ui_prompt_end {kind, title}` — **title only, no options, no way to answer it** | `types.ts:1009-1026`, `runner.ts:570-616` |
| Inter-extension bus | `pi.events` (same-process event bus) | ExtensionAPI |
| Mirror input | `input {text, images, source: interactive\|rpc\|extension}` | `types.ts:1141` |
| Persistence | pi already writes every session as JSONL under `~/.pi/agent/sessions/--<cwd>--/…` | `docs/session-format.md` |
| Lifecycle rule | no sockets/timers in the factory; start in `session_start`, close in an idempotent `session_shutdown` | `docs/extensions.md` "Respect the runtime lifecycle" |

Consequences that shape the design:

- **pi has no built-in approval system.** "Approvals" come from extensions, e.g.
  `~/.pi/agent/extensions/rm-gate.ts:630` (`ctx.ui.select(... "Approve?")`).
- **An extension cannot answer another extension's dialog.** `ui_prompt_start`
  only says *that* pi is blocked and on what title. Remote answering therefore
  needs a cooperative contract (§4), exactly as remote_pi needed pi-ask's
  `pi.events` contract (`remote_pi/pi-extension/src/extension_ui_bridge.ts`).
- **The steering queue can lose a message — but not on the `sendUserMessage`
  path (measured, #326).** `chatterbox/README.md` ("Why not Pi's steering queue")
  documents a message queued after the loop's last poll sitting there until the
  next run; that is `pi.sendMessage` with `deliverAs: "steer"` plus chatterbox's own
  queue. `pi.sendUserMessage(..., {deliverAs: "steer"})` was consumed in every one
  of 28 measured runs, and queueing it at `turn_end` / `agent_before_settle` /
  `agent_end` starts a continuation run immediately. So phone messages need no
  boundary-delivery machinery, only the identity + settle check in §2 (§0 A2 and
  [P0 evidence §A2](pi-remote-p0-evidence.md#a2-busy-time-delivery-326) for the numbers).

Assumptions, marked where Phase 0 has verified them:

- A1 **verified 2026-11-06 (issue #322):** a pi extension reaches a Unix-domain
  socket with `node:http` `request({socketPath})` — POST and a long-lived SSE stream
  both work with **no new npm dependency** (global `fetch` cannot take a socket path
  without `undici`). Server kill mid-stream → `ECONNREFUSED`, backoff 1→2→4→8→15 s,
  reconnect; quitting pi closes the stream. Evidence, gotchas and commands:
  [P0 evidence §A1](pi-remote-p0-evidence.md#a1-uds-transport-from-a-pi-extension-322).
- A2 **verified 2026-11-06 (issue #326):** `pi.sendUserMessage` behaves as documented
  and **nothing was lost in 28 runs** (idle, mid-stream, mid-tool, final `turn_end`,
  `agent_before_settle`, `agent_end`). A busy send is consumed at the next turn
  boundary of the same run (0.3–6.7 s); a boundary send starts a continuation run
  (0–1 ms). `deliver_as` is therefore a dead contract: the mode is always `steer`.
  Table, log excerpts and the settle-window measurement:
  [P0 evidence §A2](pi-remote-p0-evidence.md#a2-busy-time-delivery-326).
- A3 **verified 2026-11-06 (issue #326):** `ctx.modelRegistry` is the catalogue —
  `getAvailable()` (key present) vs `getAll()`, `hasConfiguredAuth(model)`,
  `find(provider, id)`, `getError()`; `await pi.setModel(model)` takes the object
  whole and returns `true`; `ctx.scopedModels` is empty without `--models` scoping.
  Sample: [P0 evidence §A3](pi-remote-p0-evidence.md#a3-model-catalogue-326).
- A4 **verified 2026-11-06 (issue #326):** aborting through the `AbortSignal` resolves
  the dialog promise instead of throwing (`select`/`input` → `undefined`, `confirm` →
  `false`), `timeout` takes the same cancel path, and the TUI stays clean — what §4's
  `ask_user` depends on. Evidence and source citations:
  [P0 evidence §A4](pi-remote-p0-evidence.md#a4-dialog-abort-and-timeout-326).
- A5 The `llm-dock` systemd unit runs as `teodor` (relevant only if the dashboard
  ever reads pi JSONL files directly — the plan does not require it).
- A6 How 3399 reaches the internet — **answered 2026-11-06:** `https://models.ai.heapzilla.eu`, nginx 1.24 terminating TLS in front of :3399 (`/api/health` answers 200 over HTTP/2).

**Delivery rule (A2 decision).**

1. Idle (`ctx.isIdle()`): `pi.sendUserMessage(text)` — it starts a turn, `deliverAs`
   is irrelevant.
2. Busy: `pi.sendUserMessage(text, {deliverAs: "steer"})` — consumed at the next turn
   boundary of the same run.
3. Unconfirmed at `agent_settled`: re-send once as a plain user message; "unconfirmed"
   is defined in §2 *Delivery identity and the settle check*.
4. Chatterbox's boundary delivery (`{entries, continue: true}` at `turn_end` /
   `agent_before_settle`) is **not** needed on this path — the loss documented in
   `chatterbox/README.md` is about the `pi.sendMessage` steering queue, not
   `sendUserMessage`. Keep it as the fallback for custom messages.

---

## 1. Architecture

```
 pi process (terminal)                 dashboard process (llm-dock.service)              clients
 ┌───────────────────────┐   UDS 0600   ┌─────────────────────────────────┐  HTTPS 3399  ┌──────────┐
 │ pi-remote extension   │ ───────────▶ │ pi_remote/ listener (local only)│              │ Android  │
 │  • event mirror       │  POST events │  • session registry             │ ◀─ bearer ── │ Sessions │
 │  • command executor   │ ◀─────────── │  • event log  (pi_remote.db)    │   REST + SSE │ tab      │
 │  • ask_user tool      │  SSE cmds    │  • command queue + audit        │              ├──────────┤
 │  • pi.events ask API  │              │  • prompt broker                │ ───────────▶ │ /v2/pi   │
 └───────────────────────┘              │ Flask pi_bp on :3399 (existing  │              │ web view │
   × N sessions, each dials out         │   auth, TOTP sessions)          │              └──────────┘
                                        │  • notifier (Telegram, later FCM)│ ──▶ phone notification
                                        └─────────────────────────────────┘
```

Why pi dials out:

- **Nothing new listens on the network.** pi processes come and go; making each
  one a server would mean N ports, discovery and per-process auth. Dialing a
  single local endpoint inverts that: the dashboard is the only rendezvous.
- **The local endpoint is not on 3399.** It is a Unix socket
  (`~/.cache/pi-remote/pi-remote.sock`, socket mode 0600 inside a 0700 directory
  created by the binder) served by a stdlib server inside the dashboard process —
  same in-process pattern as `inspector/proxy.py` and `model_proxy/proxy.py`.
  Filesystem permissions are the extension's authentication; a reverse proxy in
  front of 3399 cannot route to it by construction (A1 verified in #322).
- **The dashboard is the one trust boundary toward the internet**, and already
  owns login (password / TOTP → 8 h sliding token). Clients only ever talk to it.
- Dashboard restart drops the socket; extensions reconnect with backoff and
  resend their unacknowledged outbox (§2). pi itself is never blocked by the
  dashboard being down.

---

## 2. pi-side extension (`pi-remote`)

Lives in this repo under `pi-extension/` (decided, §10 Q12), symlinked into
`~/.pi/agent/extensions/`, imports `@earendil-works/pi-coding-agent`.
Split like chatterbox: `index.ts` (wiring), pure modules for outbox/protocol/prompts
with `node --test` units, a transport module.

**Registration & heartbeat** — the wire fields, paths, status codes and timeouts are
specified once in §3 *Extension endpoint*; this is the behaviour (P1 today:
hello/heartbeat/bye plus `POST /v1/events`).
- On `session_start` (any reason): `hello` with the session identity and runtime
  metadata. `instance_id` is random per `SessionRuntime` (a new one on every
  `session_start`), so every seq stream has its own key; one session resumed in two
  terminals is two instances, not one.
- Snapshot on hello: the active branch (`getBranch()`), rendered to wire events, so a
  session that started before the dashboard (or before the extension connected) still
  shows its history. Capped (last N turns + "earlier history in session file").
- Heartbeat every 15 s with `state` (`idle | working`; `waiting_prompt` and the
  queued-message flag are additive fields that arrive with prompts) and context
  usage (`ctx.getContextUsage()`).
- On `session_shutdown`: best-effort `bye {reason}`; on `new/resume/fork` the next
  `session_start` links `previous_session_id`.

**Event mirror** — `mirror.ts` subscribes to the events in §0 and emits the vocabulary
in §3 through `events.ts` bodies stamped by one `EventStamper` (sequencer + clock) at
`session_start`. It also owns the `working` flag the heartbeat reads; `index.ts` only
forwards pi events. Token deltas are coalesced (~100 ms or ~2 KB batches) and flushed at
`message_end`; tool updates are throttled to ≤ 4/s per call; tool args/results are capped
at 64 KB UTF-8 bytes with `truncated: true`. `message-content.ts`, `coalesce.ts`,
`throttle.ts` and `tool-text.ts` hold the extraction/coalescing/throttle/truncation
rules.

**Outbox & reconnect** — pure `outbox.ts`, bounded to 1000 data events (gap markers are
extra and are never merged; each dropped range gets a new gap event). Events stay
until the dashboard acks their `seq`. Overflow drops the oldest deltas first, then tool updates, and never
`state`/`run_end`/`user_message`/`assistant_message`; it records a `gap` event at the
dropped seq's slot. `discard(seqs)` removes a rejected batch and records its gap.
`sender.ts` flushes batches (≤ 50 events, ≤ 1 MiB body) while `Presence` is online,
using the shared `backoff.ts`. On `onOnline(ackedSeq)` it acks the hello's stream
position and resends the rest; a 404 on `/v1/events` calls `Presence.rejoin()`, the same
re-hello path as a heartbeat; `400 bad_frame` discards the batch with a gap and schedules
the usual backoff instead of re-flushing immediately. `Presence` owns no events and `rejoin()` is idempotent while registering.

**Off / on / stop** — one `SessionRuntime` owns Presence, Sender and Mirror.
`pause()` (from `/remote off`) stops the sender (awaiting an in-flight batch), sends
`bye remote_off`, and pauses the mirror: events while off are dropped, while unacked
events from before the pause stay in the outbox and are resent on `resume()`. Switching
sessions or shutdown calls `stop(reason)`, which also awaits the in-flight send before
`bye`; the switching runtime's outbox is dropped. The command handler talks to the
runtime, not to Presence alone.

**Inbound commands** (SSE stream from the dashboard, each with `command_id`, result
returned as `command_result {command_id, ok, error}`; ids are idempotent):

| Command | Executes |
|---|---|
| `send_message {text, images}` | idle → `pi.sendUserMessage` (starts a turn); busy → `deliverAs: "steer"`, fixed; unconfirmed commands re-sent once at `agent_settled` (see *Delivery identity* below) |
| `abort` | `ctx.abort()` |
| `answer_prompt {prompt_id, value}` | resolves a pending prompt (§4) |
| `set_model {provider, id}` / `set_thinking {level}` | `pi.setModel` / `pi.setThinkingLevel`; result reports clamping/auth failure |
| `list_models` | from `ctx.modelRegistry` / `ctx.scopedModels` (A3) |

**Delivery identity and the settle check.** The rule in §0 needs to know *which* phone
message landed, and no in-band marker is allowed — text added for tracking reaches the
model, and matching on text alone breaks on duplicates and images. So:

- **Identity.** `delivery.ts` keeps an ordered FIFO of what it sent while busy:
  `{command_id, content_hash, sent_at}`, where `content_hash` is computed over the
  normalized payload — the text plus the number of image parts — because the delivered
  message carries image blocks while our record holds attachment ids. A
  `role: "user"` `message_start` whose normalized content matches the head consumes
  that command and removes it from the FIFO. FIFO order disambiguates duplicates
  (identical text + image count is consumed one message at a time), and a message
  typed at the terminal does not match the head, so it never consumes a slot.
- **Predicate.** At `agent_settled`: `unconfirmed` = commands sent during the run that
  no matching `message_start` consumed. `ctx.hasPendingMessages()` is logged next to it
  as corroboration but is not the predicate — it cannot say *which* command is queued,
  and it was `true` at the tool-bearing `turn_end` in every measured run even though the
  message was consumed at that boundary.
- **Still pending at settle → re-send.** The command is re-sent once, as a plain
  `pi.sendUserMessage` from `agent_settled` (the agent is idle there, so it starts a
  turn) and marked `resent`, so a later settle cannot send it again. A bare "wake the
  agent and let the queue drain" is rejected: the queue is only consumed at turn
  boundaries *inside* a run, which is exactly the drain the chatterbox README documents
  as unreliable, while the idle send was reliable in every measured row. The residual
  risk is a duplicate: if the queued copy is delivered later anyway, the model sees it
  twice; the FIFO head is already `resent`, so the duplicate is recorded, not re-sent.

**Module shape.** All of that is one pure module, `delivery.ts`, with
`track(command_id, content, now)`, `observe(message, now)` and
`settle(branch, hasPending)`, owning every timer it starts and covered by `node --test`;
the lifecycle wiring in `index.ts` only forwards events. Same shape as the
`ReconnectingStream` note from the #324 review.

`expandPromptTemplates` is always **false**: phone text never dispatches slash
commands. Phone messages are echoed into the terminal via `ctx.ui.notify("📱 …")`
so the person at the keyboard sees remote input.

**Opt-in switch** — presence is on by default (there is no watch-only mode);
*control* gating arrives with the control issue.
- `~/.pi/agent/pi-remote.json`: `{enabled: true, socket: "/path/to.sock"}` — the shape
  `config.ts` reads today (env > file > default: `PI_REMOTE=0`, `PI_REMOTE_SOCKET`).
- `/remote status|on|off` per session; a config-level disable is authoritative.
- `--no-remote` and `control: "off"|"ask"` are later additions with the control issue.
- The dashboard can only *narrow* this (global kill switch, §8), never widen it:
  a session whose extension says control=off rejects commands locally.

**Multiple sessions** — one connection per pi runtime; the dashboard keys by
`(session_id, instance_id)`. Subagent pi processes (`pi --mode json/print`) register
too but are flagged `mode` so the UI can hide them by default.

---

## 3. Dashboard

New package `dashboard/pi_remote/` (mirrors `inspector/` layout): `listener.py`
(UDS server), `registry.py` (live sessions, in memory), `db.py`, `broker.py`
(commands + prompts), `notifier.py`; Flask blueprint `routes/pi_remote.py` →
`pi_bp`, registered in `create_app()` and started/stopped like `proxy_supervisor`.

**Wire vocabulary** (extension → dashboard; stored and forwarded to clients
mostly verbatim, every frame `{type, seq, ts, …}`):

| Event | Payload (sketch) | Source in pi |
|---|---|---|
| `hello` / `bye` / `heartbeat` | §2 | session_start / session_shutdown / timer |
| `state` | `idle \| working \| waiting_prompt` | agent_start, agent_settled, ui_prompt_* |
| `user_message` | text, image count, `origin: terminal\|extension` | input |
| `assistant_delta` | text and thinking chunks | message_update |
| `assistant_message` | final content, usage, model | message_end |
| `tool_start` / `tool_update` / `tool_end` | call id, name, args/partial/result, is_error, duration_ms, truncated | tool_execution_* |
| `turn_end` / `run_end` | outcome `completed\|aborted\|error` | turn_end / agent_settled |
| `model_changed` / `thinking_changed` | new + previous | model_select / thinking_level_select |
| `compaction` | summary, tokens_before, reason | session_compact |
| `prompt_open` / `prompt_closed` | §4 | broker |
| `terminal_waiting` | kind, title (unanswerable) | ui_prompt_start from other extensions |
| `notice` / `gap` | text / dropped seq range | extension |

Client frames on SSE are the same events, plus `heartbeat` and `command_result`.
Unlike chat, there is no raw OpenAI delta — every frame is typed.

**Storage — separate `pi_remote.db`** (`LLM_DOCK_PI_REMOTE_DB`, default
`dashboard/pi_remote.db`, forced to tmp in `conftest.py` like the others). Not
`chat.db`: the shape is an append-only event log keyed by a foreign id, retention
differs, and keeping it apart avoids touching chat migrations. Precedent:
`inspector.db`.

| Table | Holds |
|---|---|
| `pi_sessions` | session_id, instance_id, cwd, name, session_file, model, first/last seen, ended_at, end_reason, previous_session_id, persisted `acked_seq` |
| `pi_events` | (session_id, instance_id, seq) PK, type, ts, payload_json, gap_from, gap_to, received_at — dedup on retry; indexed by session and seq |
| `pi_prompts` | prompt_id, session, kind, question, options, status, answered_by, value, opened/closed |
| `pi_commands` | audit log: command_id, session, type, payload digest, client token kind, IP, ts, result |
| `pi_attachments` | uploaded images/audio, size-capped, by id |

Histories survive pi exit because they are the event log. `PiRemoteDB._init_db` migrates
the #331 `pi_sessions` table by adding `acked_seq`, and adds `gap_from`/`gap_to` to an
existing `pi_events` table. Retention bound: events
older than **30 days** (`received_at`) are deleted; ended sessions' events are kept
until that bound, not deleted at `bye`. The sweeper alone owns the purge: its first
sweep after listener start purges, then at most once per hour. It does not purge on
every accepted batch and the supervisor does not purge. Optional later: import
pre-existing JSONL files from `~/.pi/agent/sessions/` as read-only history.

**Client API** (on :3399, `@require_auth`, all under `/api/pi/`):

| Method | Path | Use |
|---|---|---|
| GET | `/sessions?state=live\|ended\|all` | list with state, cwd, name, model, pending-prompt count |
| GET | `/sessions/stream` | SSE: list deltas (up/down/state/attention) — feeds the list screen |
| GET | `/sessions/<id>` | meta + current state + open prompts |
| GET | `/sessions/<id>/events?before_seq&limit` | history paging |
| GET | `/sessions/<id>/stream?after_seq=N` | SSE: replay from N, then live tail, heartbeats (pattern of `run_manager.observe()` + `event_bus` replay) |
| POST | `/sessions/<id>/messages` | `{text, attachment_ids}` → 202 + command_id |
| POST | `/sessions/<id>/abort` | stop the current run |
| POST | `/sessions/<id>/prompts/<pid>/answer` | `{value}` → 200, or 409 if already answered |
| GET / PUT | `/sessions/<id>/model`, `/sessions/<id>/thinking` | list / set |
| POST | `/attachments` | image/audio upload → id |
| POST | `/transcribe` | audio → text via local whisper.cpp |
| DELETE | `/sessions/<id>` | delete stored history (ended sessions only) |

Built in #339: `GET /api/pi/sessions` → `{"sessions": [summary_json…]}`; `GET /api/pi/sessions/<session_id>/<instance_id>/events?after=&limit=` → `page_json`, with `invalid_paging` 400 and `unknown_session` 404.

Built in #344: `GET /api/pi/sessions/stream` → `snapshot` then session `session` deltas; `GET /api/pi/sessions/<session_id>/<instance_id>/stream?after=<int>` → replay `events`, then live. Frames are `events` / `session` / `snapshot` / `lagged`; `id` is the last seq sent; reconnect uses `after` or `Last-Event-ID`; a lagged stream sends `lagged` with `after` and ends.

Command flow: client POST → broker records audit row → queues to the live
instance's command stream → waits briefly for `command_result` (e.g. 5 s) → returns
it, or `202 pending` and the result arrives as an SSE frame. Session offline → 409
`code: "pi_session_offline"`. Error codes are typed like the model proxy's.

### Extension endpoint

The extension dials a stdlib server inside the dashboard process over the Unix socket
(§1). JSON only, `POST` only, every frame carries `protocol: 1`. The field names and
path constants are owned by `pi-extension/src/protocol.ts` (`PATHS`, builders,
`classifyResponse`); the server must use exactly the same names.

**`hello`** — `POST /v1/hello`

| Field | Type | Null | Notes |
|---|---|---|---|
| `protocol` | int | no | `1` |
| `type` | string | no | `"hello"` |
| `session_id` | string | no | pi session id |
| `instance_id` | string | no | random per `SessionRuntime` (new on every `session_start`) |
| `session_file` | string | yes | pi's JSONL path |
| `cwd` | string | no | |
| `name` | string | yes | session name |
| `pid` | int | no | process id |
| `model` | `{provider, id}` | yes | current model, null when none |
| `thinking_level` | string | yes | pi thinking level |
| `reason` | enum | no | `startup` \| `reload` \| `new` \| `resume` \| `fork` |
| `previous_session_id` | string | yes | set for new/resume/fork |
| `pi_version` | string | yes | null when not obtainable |
| `ext_version` | string | no | extension package version |

200: `{ok: true, protocol: 1, session_id, instance_id, server_time, acked_seq: N}`.
`acked_seq` is the persisted mark on `pi_sessions` for that `(session_id, instance_id)`
(0 when no mark); the extension acks its outbox to it and then resends the rest. It
survives a dashboard restart because it is a column, not memory.

**`heartbeat`** — `POST /v1/heartbeat`

| Field | Type | Null | Notes |
|---|---|---|---|
| `protocol` | int | no | `1` |
| `type` | string | no | `"heartbeat"` |
| `session_id` | string | no | |
| `instance_id` | string | no | |
| `state` | enum | no | `idle` \| `working` |
| `context` | `{tokens, window, percent}` | yes | `tokens` is pi's estimate, `window` the context window, `percent` as pi reports it (0–100) |
| `sent_at` | int | no | epoch ms |

200: `{ok: true, protocol: 1, server_time}`.

**`bye`** — `POST /v1/bye`

| Field | Type | Null | Notes |
|---|---|---|---|
| `protocol` | int | no | `1` |
| `type` | string | no | `"bye"` |
| `session_id` | string | no | |
| `instance_id` | string | no | |
| `reason` | string | yes | in use: `shutdown`, `switch`, `remote_off`; stored verbatim, not validated |

200: `{ok: true, protocol: 1}`.

**`events`** — `POST /v1/events`

| Field | Type | Null | Notes |
|---|---|---|---|
| `protocol` | int | no | `1` |
| `type` | string | no | `"events"` |
| `session_id` | string | no | |
| `instance_id` | string | no | |
| `events` | array | no | max **50** per batch; body max **1 MiB**; each event ≤ that body limit |

200: `{ok: true, protocol: 1, acked_seq: N}`. **Stream rule:** let `first` be the
smallest seq stored for the key (0 if none). `N` starts at
`first - 1` and advances while every seq from `first` to `N` is stored or covered by a
`gap` range. Thus a key whose first stored batch is `5..6` acks `6` even though `1..4`
are absent; a fresh/empty key acks `0`. Duplicate seqs are accepted and ignored (first
wins). An unknown event **type** is accepted and stored opaque (additive), and counts
as acked; only a malformed envelope, a malformed *known* payload, an oversize batch, or
an oversize body is `400 bad_frame`. Unknown session is `404 unknown_session`.
`UdsListener` owns the body limit: it rejects `Content-Length > 1 MiB` on
`/v1/events` with `bad_frame` before reading, so UTF-8 bytes are counted once and
non-ASCII batches are not rejected by a Python re-serialization. After the identity
and liveness check, an accepted batch inserts all events, touches `last_seen`, and
advances the persisted `acked_seq` in one transaction (first copy wins). The new mark
reads only `seq > old mark` plus `gap_from`/`gap_to`, never the whole history or its
payload JSON.

**Event payloads** (common `seq` int ≥ 1 monotonic per registered session/instance, `ts`
epoch ms):

| Event | Payload fields (type / nullable / units) |
|---|---|
| `state` | `state`: `"idle" \| "working"` |
| `user_message` | `text` string; `image_count` int; `origin`: `"terminal" \| "extension"` |
| `assistant_delta` | `text` string; `thinking` string (one may be empty; coalesced chunks) |
| `assistant_message` | `text` string; `thinking` string; `model`: `{provider, id}` \| null; `usage`: `{input, output, cache_read, cache_write, reasoning\|null, total_tokens, cost_total\|null}` \| null; `stop_reason` string \| null |
| `tool_start` | `call_id` string; `name` string; `args` string \| null (JSON text, ≤ 64 KB); `truncated` bool |
| `tool_update` | `call_id` string; `name` string; `partial` string \| null (JSON text, ≤ 64 KB); `truncated` bool; emitted at most 4/s per call |
| `tool_end` | `call_id` string; `name` string; `result` string \| null (JSON text, ≤ 64 KB); `is_error` bool; `duration_ms` int \| null; `truncated` bool |
| `turn_end` | `outcome`: `"completed" \| "aborted" \| "error"` |
| `run_end` | `outcome`: `"completed" \| "aborted" \| "error"` |
| `model_changed` | `model`: `{provider, id}` \| null; `previous`: `{provider, id}` \| null |
| `thinking_changed` | `level` string \| null; `previous` string \| null |
| `compaction` | `summary` string; `tokens_before` int \| null; `reason` string |
| `gap` | `from_seq` int; `to_seq` int (inclusive); marks dropped seqs; gaps are immutable and never merged |

Status codes:

| Code | Body | Meaning |
|---|---|---|
| 200 | `{ok: true, protocol: 1, ...}` | accepted |
| 400 | `{ok: false, protocol: 1, error: "bad_frame"}` | missing or ill-typed field (`session_id`, `instance_id` required; `type` must match the path) |
| 400 | `{ok: false, protocol: 1, error: "unsupported_protocol"}` | `protocol` is absent or not `1` |
| 404 | `{ok: false, protocol: 1, error: "unknown_session"}` | heartbeat/bye for a stale or unknown `(session_id, instance_id)` |
| 404 | `{ok: false, protocol: 1, error: "not_found"}` | unknown path or non-`POST` method |

**Server semantics**

- **Registry key is `(session_id, instance_id)`.** A second `hello` for the same session
  from another instance **coexists** — two terminals on one session are two instances.
  A heartbeat or bye for a known session with an unknown instance is
  `404 unknown_session`; an events batch for an unknown or stale instance is likewise
  `404 unknown_session`. Liveness is checked before event payload parsing, so a stale
  client gets the re-hello path rather than a `bad_frame` discard. An accepted events
  batch touches the instance's liveness and `pi_sessions.last_seen` at most once.
- **Liveness: 45 s.** An instance is stale after 45 s without a heartbeat (3 missed at
  the 15 s cadence). A sweeper owns the ending: it expires stale instances and writes
  `ended_at`/`end_reason = "stale"` without waiting for another request. A late
  heartbeat or `bye` from a stale instance still gets `404 unknown_session`. At dashboard
  start, open rows are ended `dashboard_restart`; a live pi's next re-`hello` reopens its
  row through the upsert.
- **Check order** (server): (1) method/path → `404 not_found`; (2) body/`protocol`
  → `400 unsupported_protocol`; (3) path/`type` match → `400 bad_frame`; (4) parse
  `session_id`/`instance_id`, then liveness → `404 unknown_session`; (5) for `events`,
  batch shape/count → `400 bad_frame`; (6) each event. The transport checks
  `Content-Length > 1 MiB` before the handler. Unknown extra fields are **ignored**.
- **Per-event validation depth**: known types validate the common envelope (`type`,
  `seq` int ≥ 1, `ts` int) plus their table fields (required types/nulls, `gap` range,
  usage/model shapes); unknown types validate only the envelope. A duplicate seq with a
  different payload keeps the first stored payload. A `gap` whose seq collides with an
  existing event is a duplicate and is ignored; the existing event wins.
- **Client handling**: transport error/timeout, `400 unsupported_protocol`, or another
  non-ok status → offline + backoff (1 s → 30 s cap); `404 unknown_session` on heartbeat
  or `/v1/events` → immediate re-`hello`; `404` on `bye` is ignored (best-effort).
  `400 bad_frame` on `/v1/events` discards that batch with a `gap` marker and schedules
  the usual backoff instead of retrying it forever. `server_time`/`sent_at` are epoch ms; unknown event types are
  accepted and count as acked, so one rejected future event cannot block the stream.

**Version rule**: both directions carry `protocol: 1`; a mismatch is a 400
`unsupported_protocol`, and a version bump ships in the extension and the dashboard
together. **Timeouts**: the extension allows 3 s for `hello`, 2 s for `heartbeat`, 1 s
for `bye` (the last two bounded so a dashboard restart cannot stall pi); server-side
read timeout 5 s per request.

**Golden fixtures**: `pi-extension/test/contract/frames.json` is the executable form of
the presence contract (hello response now includes `acked_seq`, second instance,
heartbeat ok, unknown session, stale instance, bye, instance mismatch, bad_frame,
unsupported_protocol, type/path mismatch, not_found, ignored extra field).
`pi-extension/test/contract/events.json` is the executable events contract (ok batch,
duplicate resend, re-hello on a key holding `1..3` → acked `3`, gap, unknown accepted
type, malformed known event, unknown session, oversize batch, empty batch, a hello with
nothing below seq 5 followed by `5..6` → acked `6`, immutable gaps `10..10` then
`11..11` → acked `11`, and an unknown path with `protocol: 2` → `404 not_found`). Both are
ordered `{path, now, request, status, response}` cases; the extension's TS tests run
them through `test/fake-server.ts`'s `handleFrame`, and
`dashboard/tests/test_pi_remote_fixtures.py` runs both files against the Python handler.
The body-limit cases are separate listener tests: ~400 KB of emoji is accepted and a
declared `Content-Length > 1 MiB` is rejected without reading.

**Ingest package** — `dashboard/pi_remote/`, built in #331:

| Module | Owns |
|---|---|
| `contract.py` | `PATHS`, protocol version, status/error constants, body limit, end reasons, `JsonResponse` and response builders; `validate_request` uses a `{kind: parser}` table for presence frames and the events envelope |
| `wire_types.py` | shared wire vocabulary: `STATES`, int/number/nullable/model/usage checks used by both parsers |
| `frames.py` | frozen presence frame dataclasses (`ModelRef`, `ContextUsage`, `HelloFrame`, `HeartbeatFrame`, `ByeFrame`) and parse helpers |
| `events.py` | frozen `Event`/`EventsEnvelope`/`EventsFrame` dataclasses, envelope and known-payload validation, unknown-type acceptance, batch limit, and the pure `acked_seq()` |
| `schema.py` | SQL text for `pi_sessions` and `pi_events` plus insert/upsert statements |
| `registry.py` | in-memory instances keyed by `(session_id, instance_id)`, `is_live`, `expire`, `touch`, typed frames and the `RegistryResult` enum; thread-safe, time passed in |
| `store.py` | `pi_remote.db` (`pi_sessions`, `pi_events`), upsert/touch/end/end-open, `ingest` (insert + last_seen + mark in one transaction), history read, retention purge; the only module writing SQL |
| `read_model.py` | pure query model: `SessionSummary`, `EventView`, `EventPage`, `session_summary`, `event_page`, `clamp_limit`; no I/O |
| `bus.py` | in-process fan-out: `EventBus`, `Subscription`, `BusMessage`; a full subscriber is marked `lagged` and closed, never silently dropped |
| `stream.py` | SSE generators over a `StreamSource` protocol: subscribe-before-replay, cursor dedupe, lagged ends; no Flask imports |
| `handler.py` | `handle(method, path, body, now) -> JsonResponse`; a `{path: route}` table, no sockets |
| `listener.py` | the only module with sockets: `UdsListener` with `start()`/`stop()`/`running`/`bind_error`, owned thread, `daemon_threads`; speaks only `JsonResponse` |
| `socket_path.py` | filesystem policy as plain functions: directory `0700`, stale-socket replacement, live-socket detection |
| `sweeper.py` | `StaleSweeper` (injected clock + interval, idempotent `start()`/`stop()`) owns stale expiry, row ending, and the first/hourly retention purge; logs a failed sweep and keeps looping |
| `settings.py` | defaults and env resolution for the socket and DB |
| `supervisor.py` | singleton owning listener + registry + store + sweeper + bus; clock injected; configured/started from `create_app()`, stopped by `atexit`; facade `session()`, `sessions()`, `events()` and `subscribe()` |
| `__main__.py` | standalone `python -m pi_remote --socket … --db …` for the live check |

- **Env**: `LLM_DOCK_PI_REMOTE_SOCKET` (default `~/.cache/pi-remote/pi-remote.sock` — the
  same path as `pi-extension/src/config.ts`; the two defaults must change together) and
  `LLM_DOCK_PI_REMOTE_DB` (default `dashboard/pi_remote.db`). App config keys
  `PI_REMOTE_SOCKET` / `PI_REMOTE_DB_PATH` override them at boot.
- **Directory rule**: the socket's parent is created `0700` if absent; an existing parent
  with group or other permission bits is refused with a logged error and `bind_error`, and
  the dashboard still boots. The socket is `0600`. A stale socket file is replaced; a live
  one (another dashboard) sets `bind_error`. `stop()` removes the socket file it created.
- **Storage**: `pi_sessions` is one row per `(session_id, instance_id)`; hello upserts and
  preserves `first_seen`, heartbeat updates `last_seen`, bye sets `ended_at`/`end_reason`,
  and the sweeper ends a stale instance with `end_reason = "stale"`. At supervisor start,
  leftover open rows are ended `dashboard_restart` before the listener accepts traffic.

The later `GET /v1/commands` (SSE) and `POST /v1/command-results`, plus the additive
presence fields (`waiting_prompt`, queued-message flag, `target_session_file` on bye),
are not part of this contract — they arrive with the commands/prompt issues and are
ignored by a server that does not know them.

**Relation to chat conversations** — separate entity. A pi session is not a
`conversations` row: the model runs inside pi, not through `llm_proxy`, and the
dashboard only mirrors and relays. The two share auth, SSE framing helpers
(`event_codec.py`) and UI building blocks (markdown/tool-call rendering), nothing
else. No cross-linking in v1.

---

## 4. Interactive prompts

**Kinds** (Hermes-style buttons: question in the body, short buttons, plus "Other…"):

| Kind | Phone UI | Value |
|---|---|---|
| `confirm` | Yes / No | bool |
| `select` | one button per option (+ Other → text) | option string or free text if allowed |
| `input` | text field (voice-capable) | string |
| `approval` | Allow once / Allow for session / Deny (+ reason) | enum + optional text |

**Where prompts come from**

1. **`ask_user` tool** registered by pi-remote (`exposure: "model-only"`, per
   docs/extensions.md "Tool exposure"): the model asks the user a question with
   optional choices. Locally it opens `ctx.ui.select/input` *with an AbortSignal*;
   remotely it emits `prompt_open`. First answer wins; the loser is aborted.
2. **`pi.events` ask contract** for other extensions — `llm-dock/pi-remote:ask`
   `{prompt_id, kind, title, message, options, timeout_ms}` → reply event
   `…:answer`. rm-gate (and any future gate) calls a tiny helper:
   "race `ctx.ui.select` vs the contract if pi-remote is loaded, else plain
   `ctx.ui.select`". Inert without pi-remote.
3. **pi-ask bridge** (optional): if `@eko24ive/pi-ask` is installed, subscribe to its
   `:started/:submit/:completed` events as remote_pi does.
4. **Any other dialog** — only `ui_prompt_start {kind, title}` is visible. Shown as a
   read-only "pi is waiting at the terminal: <title>" banner, and it triggers a
   notification. Monkey-patching another extension's `ctx.ui` is rejected
   (unsupported, breaks on reload). Upstream ask: richer `ui_prompt_start` plus an
   answer hook.

**Lifecycle**: `open → answered(by: terminal|phone|web, value) | cancelled
(run aborted) | expired(timeout) | orphaned(session ended)`.
- The extension owns the truth: the first resolution wins in-process; the dashboard
  broker stores it and closes the prompt for every client (`prompt_closed`). A late
  phone answer gets 409 `prompt_already_answered` with the winning value.
- Open prompts are part of `GET /sessions/<id>` and replayed on SSE attach (the
  remote_pi lesson: the agent usually asks while the app is closed).
- Timeouts: none by default for `ask_user` (pi just waits, as it would at the
  terminal); per-call `timeout_ms` for gates, which already have defaults. Expiry
  resolves to the safe value (deny / no / cancelled).
- Dashboard restart while a prompt is open: the extension re-sends it with `hello`.

---

## 5. Android app

**Mockups:** `docs/pi-remote/mockups/` (Android sessions, live session, approval sheet; web `/v2/pi`) — the visual reference for every UI issue.


New feature files, in the existing process (one feature, one commit, one PR, merged,
via implementer + reviewer agents; `Plan_TOC.md` §6 index). Numbers are proposals:

| F | Feature | Must |
|---|---|---|
| F17 | Sessions tab — list | third bottom tab "Pi"; live first (state chip, cwd, name, model, ⚠ pending prompt), ended below; `/sessions/stream` |
| F18 | Session view — live transcript | reuse F05 rendering for markdown and tool calls (collapsed tool output), replay from `after_seq`, history paging; read-only |
| F19 | Composer + Stop | send text (always steer); Stop button while `working`; "terminal: control off" disabled state |
| F20 | Prompt cards | inline buttons for confirm/select/approval, text for input, closed state showing who answered |
| F21 | Attachments | images from gallery/camera/share sheet (F14 reuse) → `/attachments` → message |
| F22 | Voice in | record → `/transcribe` → text **into the composer for review**, never auto-sent; Android `SpeechRecognizer` as an offline-free fallback is an open question |
| F23 | Voice out | Android `TextToSpeech` reads final assistant messages; per-session toggle; skips tool output |
| F24 | Model / thinking switch | picker from `/sessions/<id>/model`, ladder from pi's thinking levels |
| F25 | Notifications | §7; reopens F09-R6 and `Dropped-Features.md` "Notification when an answer lands" |

Fit with the ground rules:
- **R-A (backend parity)**: each Android feature lands after its endpoints exist;
  `Plan_TOC.md` §5 gains a "pi sessions" table as they ship.
- **R-B (web parity)**: every phone capability has the §6 web counterpart first or
  in the same phase.
- **R-C (mockups)**: no mockups exist — add 4–5 screens to
  `docs/android/chat-app-mockups.html` (list, session, prompt card, composer with
  voice) before F17, or record "no mockup" deviations as F15/F16 did.
- **Architecture D5** (screen-scoped streams, no background service) holds for
  F17–F24. Only F25 may change it, depending on §7.
- Wire↔domain seam (D6): a new `PiEvent` parser beside `RunEvent.kt`; do not
  reuse the chat run parser — the frames differ.

---

## 6. Web dashboard view (smaller)

- `/v2/pi` route: session list (live/ended) + session view with the same transcript
  components the chat page uses, composer, Stop, prompt cards, model/thinking menu.
- Reads the same endpoints; SSE through the existing authenticated fetch-stream
  helper (frontend `AGENTS.md`).
- Global kill switch and the audit log (`pi_commands`) live here (Settings card),
  not on the phone.
- Voice is phone-only in v1.

---

## 7. Notifications

Trigger set: prompt opened, `terminal_waiting`, run ended after > N s of work, run
error. Sent by `pi_remote/notifier.py`, debounced per session.

| Option | Pros | Cons |
|---|---|---|
| **Telegram bot** (already in use here) | zero app work; works when the app is dead; ready today | third party sees whatever we send → must be content-free ("pi needs you: session *x*") with a deep link; buttons there would make Telegram a control relay — excluded |
| FCM data-only "tickle" | native; app wakes and fetches content itself over 3399, so Google sees no content | Firebase project, `google-services`, server credentials, Play Services dependency; new endpoint to register device tokens |
| Foreground service holding an SSE connection | no third party at all | permanent notification, battery, Android 14/15 FGS-type limits (`dataSync` time cap), contradicts D5 |
| UnifiedPush / self-hosted ntfy | FOSS, self-hosted, content can stay local | another server to expose on the internet (or proxy under 3399), plus a distributor app on the phone |

**Recommendation**: Phase 1 = Telegram, content-free, deep link
(`llmdock://pi/<session>`) into the app — cheapest, works immediately. Phase 2, if
the Telegram hop annoys: FCM data-only tickle (content never leaves the box).
Skip the foreground service.

---

## 8. Security model

This is remote control of a shell-capable agent from the internet. The agent can do
anything the user can; a stolen dashboard token becomes a shell.

| Threat | Mitigation |
|---|---|
| Stolen / brute-forced dashboard credential | existing TOTP; **add login rate limiting** on `/api/auth/*` (verify none exists); control endpoints require a session minted via TOTP, or recently re-verified (open question) |
| Some other local process impersonates a pi session or injects events | UDS mode 0600 under the user's dir; extension endpoint never on 3399; peer-uid check (`SO_PEERCRED`) on the socket |
| Internet client reaches the extension API | it is not routed: different socket, not a Flask route |
| Phone escalates beyond chat | command allow-list (§2); `expandPromptTemplates: false`; no `!bash`, no slash commands, no session new/fork/switch/delete, no tool/extension/settings changes, no reload/shutdown, no file browsing, no spawning new pi processes (v1) |
| Silent remote control | terminal notify on every phone message/answer; status line `remote: armed`; per-session `/remote off`; global kill switch in the dashboard |
| Replay / duplicated commands | command ids idempotent; prompt answers bound to `prompt_id` and first-answer-wins |
| Flooding | per-session command rate limit (e.g. 10/min), body and attachment caps |
| Secrets in mirrored output (tool results, keys from `GET /api/services`, env dumps) | same trust as `chat.db`; size caps; retention window; delete per session; never sent to Telegram/FCM |
| Repudiation | `pi_commands` audit (who, token kind, IP, ts, result), visible in the web UI |
| Relay injection (remote_pi's weakness) | no relay exists: the dashboard terminates TLS (or the user's own proxy does) and is the trusted endpoint; signing phone commands is unnecessary unless a relay is ever added |

The phone must never: run a command directly, change what pi is allowed to do,
read files outside what the transcript already shows, or reach sessions whose
control is off.

---

## 9. Phasing

Each phase ships on its own (own branch from fresh `main`, PR, merge).

| # | Phase | Delivers | Size |
|---|---|---|---|
| P0 | Spike | verify A1–A6; prototype extension printing the event stream; boundary-delivery decision | S |
| P1 | Read-only mirror, web | extension (hello, events, outbox, reconnect), UDS listener, `pi_remote.db`, list + session SSE, `/v2/pi` read-only | M |
| P2 | Read-only on Android | F17 + F18 (+ mockups) | M |
| P3 | Control | send message, Stop, opt-in switch, audit, rate limits, kill switch; web composer, then F19 | M |
| P4 | Prompts | `ask_user` tool, `pi.events` contract, rm-gate adoption, `terminal_waiting`; web cards, then F20 | M–L |
| P5 | Notifications v1 | Telegram content-free notifier + deep link (F25 part 1) | S |
| P6 | Attachments + model/thinking | `/attachments`, images in messages, model/thinking endpoints; F21, F24 | S–M |
| P7 | Voice | `/transcribe` via whisper.cpp (checkout at `/github/ggml-org/whisper.cpp`; server not verified running), F22, F23 | S–M |
| P8 | Native push (optional) | FCM data-only tickle, device registration (F25 part 2) | M |
| P9 | History polish (optional) | retention settings, JSONL import of older sessions, search | S–M |

The smallest useful slice is P1+P3 on the web; the phone becomes useful at P2.
P4 is where the "away from keyboard" story pays off.

---

## 10. Open questions

1. **Control default**: mirror-on for every session is decided; should *control*
   be on by default (matching "every session reachable") or `ask`/off until
   `/remote on`?
   **Answered 2026-11-06: no watch-only mode.** A session is either fully remote (watch + act) or not remote at all. Default assumed **on** for every session (the original "every session reachable" requirement), with `/remote off` per session and the global kill switch; confirm when P3 starts.
2. **Step-up auth**: should control/answers require a TOTP-minted session (not the
   static password), or a re-verify after X hours?
   **Answered 2026-11-06: no step-up.** The existing login (password/TOTP session) is enough. Pocket ID (OpenID Connect, used on the user's other projects) was considered and skipped for now.
3. **Exposure path**: how does 3399 reach the internet today (reverse proxy, TLS
   where)? Needed to confirm nothing can route to the extension socket and to
   decide on login rate limiting placement.
   **Answered:** nginx at `models.ai.heapzilla.eu` terminates TLS and proxies to :3399; a Unix socket is unreachable through it by construction. Login rate limiting can live in nginx (`limit_req`) or the dashboard.
4. **Subagents**: show `pi --mode json/print` child sessions, hide by default, or
   not register them at all?
5. **Retention** for ended sessions (days) and whether to import pre-existing pi
   JSONL history.
6. **Busy-send semantics**: phone message while pi works — default follow-up
   (after the run) or steer (into the current run)?
   **Answered 2026-11-06: steer, and only steer** — `deliver_as` is dropped from the
   command and the API. #326 measured that `sendUserMessage` with either mode is
   consumed at the next turn boundary of the same run and that nothing was lost in 28
   runs, so "re-delivered as a follow-up" is not a second path but the settle-time
   re-send defined once in §2 (*Delivery identity and the settle check*) and in §0's
   delivery rule.
7. **rm-gate**: OK to modify it to use the `pi.events` ask contract, so its
   approvals become answerable from the phone?
   **Answered 2026-11-06: yes, modify rm-gate.**
8. **Notifications**: accept Telegram (content-free) as v1, and is FCM
   (Google Play Services dependency) acceptable later?
9. **Voice in**: server whisper.cpp only, or also on-device `SpeechRecognizer`?
   Which whisper model/server should the dashboard call?
10. **Mockups**: extend `chat-app-mockups.html` before F17, or build without
    mockups and record deviations?
11. **Starting new pi sessions** from the phone (spawning a process in a chosen
    cwd) — explicitly out of v1; permanently out?
12. **Where the extension lives**: this repo (e.g. `pi-extension/`) so protocol and
    server change in one PR, or `ai-toolbox` beside `ding.ts`?
    **Answered 2026-11-06: this repo.**

---

## 11. Work breakdown (issues)

Issues are created one at a time and worked through `docs/pi-dev-protocol.md`. This
list is the order; each line becomes an issue with its own acceptance criteria when it
is next. Later phases stay coarse until P1 lands.

| # | Phase | Chunk |
|---|---|---|
| 1 | P0 | Transport probe: `node:http` over a Unix socket from pi's runtime, request + long-lived SSE (A1, **verified** in #322) |
| 2 | P0 | pi API probe: steer/follow-up timing incl. the end-of-run race (A2), model list (A3), dialog abort (A4) — **verified** in #326 |
| 3 | P1 | Extension skeleton in `pi-extension/`: wire types, `hello`/heartbeat/`bye`, `/remote` status, `node --test` |
| 4 | P1 | Dashboard ingest: `dashboard/pi_remote/` socket server, `pi_remote.db` schema, session registry |
| 5 | P1 | Event mirror + outbox/ack/reconnect (extension) and event storage (dashboard) |
| 6 | P1 | Client API: `GET /api/pi/sessions`, session detail, events SSE with replay from `seq` |
| 7 | P1 | Web `/v2/pi`: session list + read-only live view |
| 8 | P2 | Android: Pi tab, session list (F17) |
| 9 | P2 | Android: read-only live session view (F18) |
| 10 | P3 | Control: `send_message` (steer + fallback) and `abort`, end to end, web first |
| 11 | P3 | Android composer + Stop (F19) |
| 12+ | P4–P7 | Prompts + rm-gate, Telegram ping, attachments, model switch, voice |

