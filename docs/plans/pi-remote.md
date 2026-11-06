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
| Send input | `pi.sendUserMessage(text \| (TextContent\|ImageContent)[], {deliverAs: "steer"\|"followUp", expandPromptTemplates})` — images supported | ExtensionAPI |
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
- **The steering queue can lose a message.** `chatterbox/README.md` ("Why not
  Pi's steering queue") documents a message queued after the loop's last poll
  sitting there until the next run. Phone messages sent while busy must use the
  boundary delivery chatterbox uses (`turn_end` / `agent_before_settle` continue,
  start a turn on `agent_settled`), or be proven safe with `deliverAs`.

Assumed, to verify in Phase 0:

- A1 Node's `fetch` in pi's runtime can dial a Unix socket (undici `Agent({connect:
  {socketPath}})`), or we fall back to loopback TCP + secret.
- A2 `pi.sendUserMessage(..., {deliverAs: "followUp"})` while streaming, and the
  idle case, behave as documented; the chatterbox race reproduces or not.
- A3 `ctx.modelRegistry` exposes a list of available models we can offer.
- A4 Aborting a `ctx.ui.select` via its signal leaves the TUI clean.
- A5 The `llm-dock` systemd unit runs as `teodor` (relevant only if the dashboard
  ever reads pi JSONL files directly — the plan does not require it).
- A6 How 3399 reaches the internet — **answered 2026-11-06:** `https://models.ai.heapzilla.eu`, nginx 1.24 terminating TLS in front of :3399 (`/api/health` answers 200 over HTTP/2).

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
  (`~/.cache/llm-dock/pi-remote.sock`, mode 0600) served by a stdlib server
  inside the dashboard process — same in-process pattern as `inspector/proxy.py`
  and `model_proxy/proxy.py`. Filesystem permissions are the extension's
  authentication; a reverse proxy in front of 3399 cannot route to it by
  construction. Fallback if A1 fails: `127.0.0.1:<port>` + a 0600 secret file.
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

**Registration & heartbeat**
- On `session_start`: connect, send `hello {session_id, instance_id, session_file,
  cwd, name, pid, model, thinking, reason, previous_session_file, pi_version,
  ext_version}`. `instance_id` = random per runtime, so the same session resumed in
  two terminals is two instances, not one.
- Snapshot on hello: the active branch (`getBranch()`), rendered to wire events,
  so a session that started before the dashboard (or before the extension
  connected) still shows its history. Capped (last N turns + "earlier history in
  session file").
- Heartbeat every ~15 s with `state` (`idle | working | waiting_prompt`), context
  usage (`ctx.getContextUsage()`), queued-message flag.
- On `session_shutdown`: `bye {reason, target_session_file}`; on `new/resume/fork`
  the next `session_start` registers the new id and links `previous_session`.

**Event mirror** — subscribes to the events in §0 and emits the vocabulary in §3.
Each event gets a per-instance monotonic `seq`. Token deltas are coalesced (~100 ms
or ~2 KB batches) before leaving the process; tool updates throttled and truncated
(e.g. 64 KB per result, with `truncated: true`).

**Outbox & reconnect** — bounded in-memory outbox; events stay until the dashboard
acks their `seq`. On reconnect: re-`hello`, resend unacked. Overflow drops the oldest
deltas first, never prompts/state events, and records a `gap` event.

**Inbound commands** (SSE stream from the dashboard, each with `command_id`, result
returned as `command_result {command_id, ok, error}`; ids are idempotent):

| Command | Executes |
|---|---|
| `send_message {text, images, deliver_as}` | idle → `pi.sendUserMessage`; busy → boundary delivery (chatterbox pattern) or `deliverAs` per A2 |
| `abort` | `ctx.abort()` |
| `answer_prompt {prompt_id, value}` | resolves a pending prompt (§4) |
| `set_model {provider, id}` / `set_thinking {level}` | `pi.setModel` / `pi.setThinkingLevel`; result reports clamping/auth failure |
| `list_models` | from `ctx.modelRegistry` / `ctx.scopedModels` (A3) |

`expandPromptTemplates` is always **false**: phone text never dispatches slash
commands. Phone messages are echoed into the terminal via `ctx.ui.notify("📱 …")`
so the person at the keyboard sees remote input.

**Opt-in switch** — the requirement is "every session reachable", so mirroring is on
by default; *control* is gated separately:
- `~/.pi/agent/pi-remote.json`: `{mirror: true, control: "on"|"off"|"ask"}`.
- `/remote on|off|status` per session, `--no-remote` flag, `PI_REMOTE=0` env.
- Status line item: `remote: mirror` / `remote: armed` / `remote: offline`.
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
| `user_message` | text, images (refs), `origin: terminal\|phone\|extension` | input / message_start(user) |
| `assistant_delta` | text and thinking chunks | message_update |
| `assistant_message` | final content, usage, model | message_end |
| `tool_start` / `tool_update` / `tool_end` | id, name, args, partial/result, isError, durationMs | tool_execution_* |
| `turn_end` / `run_end` | outcome `completed\|aborted\|error` | turn_end / agent_settled |
| `model_changed` / `thinking_changed` | new + previous | model_select / thinking_level_select |
| `compaction` | summary flag, tokens | session_compact |
| `prompt_open` / `prompt_closed` | §4 | broker |
| `terminal_waiting` | kind, title (unanswerable) | ui_prompt_start from other extensions |
| `notice` / `gap` | text / dropped range | extension |

Client frames on SSE are the same events, plus `heartbeat` and `command_result`.
Unlike chat, there is no raw OpenAI delta — every frame is typed.

**Storage — separate `pi_remote.db`** (`LLM_DOCK_PI_REMOTE_DB`, default
`dashboard/pi_remote.db`, forced to tmp in `conftest.py` like the others). Not
`chat.db`: the shape is an append-only event log keyed by a foreign id, retention
differs, and keeping it apart avoids touching chat migrations. Precedent:
`inspector.db`.

| Table | Holds |
|---|---|
| `pi_sessions` | session_id, instance_id, cwd, name, session_file, model, first/last seen, ended_at, end_reason, previous_session_id |
| `pi_events` | (session_id, instance_id, seq) PK, type, payload_json, ts — dedup on retry |
| `pi_prompts` | prompt_id, session, kind, question, options, status, answered_by, value, opened/closed |
| `pi_commands` | audit log: command_id, session, type, payload digest, client token kind, IP, ts, result |
| `pi_attachments` | uploaded images/audio, size-capped, by id |

Histories survive pi exit because they are the event log. Retention: keep ended
sessions N days (setting), delete per session from UI. Optional later: import
pre-existing JSONL files from `~/.pi/agent/sessions/` as read-only history.

**Client API** (on :3399, `@require_auth`, all under `/api/pi/`):

| Method | Path | Use |
|---|---|---|
| GET | `/sessions?state=live\|ended\|all` | list with state, cwd, name, model, pending-prompt count |
| GET | `/sessions/stream` | SSE: list deltas (up/down/state/attention) — feeds the list screen |
| GET | `/sessions/<id>` | meta + current state + open prompts |
| GET | `/sessions/<id>/events?before_seq&limit` | history paging |
| GET | `/sessions/<id>/stream?after_seq=N` | SSE: replay from N, then live tail, heartbeats (pattern of `run_manager.observe()` + `event_bus` replay) |
| POST | `/sessions/<id>/messages` | `{text, attachment_ids, deliver_as}` → 202 + command_id |
| POST | `/sessions/<id>/abort` | stop the current run |
| POST | `/sessions/<id>/prompts/<pid>/answer` | `{value}` → 200, or 409 if already answered |
| GET / PUT | `/sessions/<id>/model`, `/sessions/<id>/thinking` | list / set |
| POST | `/attachments` | image/audio upload → id |
| POST | `/transcribe` | audio → text via local whisper.cpp |
| DELETE | `/sessions/<id>` | delete stored history (ended sessions only) |

Command flow: client POST → broker records audit row → queues to the live
instance's command stream → waits briefly for `command_result` (e.g. 5 s) → returns
it, or `202 pending` and the result arrives as an SSE frame. Session offline → 409
`code: "pi_session_offline"`. Error codes are typed like the model proxy's.

**Extension API** (UDS only): `POST /v1/hello`, `POST /v1/events` (batch, returns
acked seq), `GET /v1/commands` (SSE), `POST /v1/command-results`.

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

New feature files, in the existing process (one feature, one commit, one PR, merged,
via implementer + reviewer agents; `Plan_TOC.md` §6 index). Numbers are proposals:

| F | Feature | Must |
|---|---|---|
| F17 | Sessions tab — list | third bottom tab "Pi"; live first (state chip, cwd, name, model, ⚠ pending prompt), ended below; `/sessions/stream` |
| F18 | Session view — live transcript | reuse F05 rendering for markdown and tool calls (collapsed tool output), replay from `after_seq`, history paging; read-only |
| F19 | Composer + Stop | send text; Stop button while `working`; follow-up vs steer toggle; "terminal: control off" disabled state |
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
   **Answered 2026-11-06: steer.** The lost-steer case above must be handled: a steer that the run never consumed is re-delivered as a follow-up.
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
| 1 | P0 | Transport probe: Node `fetch`/undici over a Unix socket from pi's runtime, request + long-lived SSE (A1) |
| 2 | P0 | pi API probe: steer/follow-up timing incl. the end-of-run race (A2), model list (A3), dialog abort (A4) |
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

