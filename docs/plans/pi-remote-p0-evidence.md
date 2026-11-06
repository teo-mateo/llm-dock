# pi-remote P0 evidence (#322, #326)

Measurements, log excerpts and source citations behind the A1–A4 verdicts in
[`pi-remote.md`](pi-remote.md) §0. The plan carries the decisions; this file carries the
numbers and the commands that produced them. Nothing here is a contract.

## A1: UDS transport from a pi extension (#322)

A pi extension reaches a Unix-domain socket with `node:http`
`request({socketPath})` — a plain POST and a long-lived `GET` SSE stream both work,
with **no new npm dependency**. Global `fetch` is not the route: it cannot take a
socket path without the `undici` package, while `node:http` is available because pi
loads extensions through `jiti` inside the Node process (pi's own code already
imports `node:net`). Killing the server mid-stream neither hangs nor crashes pi: the
extension reports `ECONNREFUSED`, backs off 1→2→4→8→15 s and reconnects when the
server returns; quitting pi closes the stream and the server logs the client
disconnect. The loopback-TCP fallback is not needed.

Gotchas found while building the probe:

- `~/.cache/llm-dock` is **root-owned** on this host (`drwxr-xr-x root root`), so the
  original socket path could not be bound as `teodor` (`PermissionError: [Errno 13]`).
  The socket lives in `~/.cache/pi-remote/` — directory `0700`, socket `0600`, both
  created by the binder. §1 uses that path.
- `BaseHTTPRequestHandler.address_string()` raises `IndexError` under `AF_UNIX`
  because `client_address` is a string, not a tuple; override `log_message` and do
  not call it.
- `ctx.ui.notify` info messages are a single replaceable status line: back-to-back
  notifications overwrite each other, so an event log must not rely on them.
- A killed stream fires both `error` and `end`; reconnect scheduling must be
  idempotent or the retry timer doubles.

```
python3 pi-extension/spike/uds-probe/server.py [--socket PATH]
pi --model mistral/mistral-small-latest --no-extensions -e pi-extension/spike/uds-probe/probe.ts
curl -s --unix-socket ~/.cache/pi-remote/pi-remote-spike.sock -X POST \
  -H 'content-type: application/json' -d '{"session_id":"curl-test","cwd":"/tmp"}' \
  http://localhost/hello
curl -s -N --unix-socket ~/.cache/pi-remote/pi-remote-spike.sock http://localhost/events
```

Stub log over one session (stale file removed, hello from the real extension, SSE
stream, then the disconnect after `/quit`):

```
removed stale socket /home/teodor/.cache/pi-remote/pi-remote-spike.sock
listening on /home/teodor/.cache/pi-remote/pi-remote-spike.sock (mode 0o600)
POST /hello body={"session_id":"01a1b090-...","cwd":"/tmp","model":"mistral-small-latest"}
uds "POST /hello HTTP/1.1" 200 -
GET /events stream opened
sent event seq=1
sent event seq=2
sent event seq=3
client disconnected: BrokenPipeError: [Errno 32] Broken pipe
GET /events stream closed
```

Cadence, measured with timestamps on the client side (events 1 s apart, comment
heartbeats every 5 s, stream held open):

```
12:18:23.038 | data: {"seq": 1, "kind": "hello", "text": "event one"}
12:18:24.039 | data: {"seq": 2, "kind": "state", "text": "event two"}
12:18:25.040 | data: {"seq": 3, "kind": "bye", "text": "event three"}
12:18:26.040 | : heartbeat
12:18:31.046 | : heartbeat
```

## A2: busy-time delivery (#326)

Probe: `pi-extension/spike/api-probe/` (wiring in `index.ts`, pure helpers in
`transcript.ts` + `scenarios.ts`, dialogs in `dialogs.ts`). One log per pi session in
`/tmp/pi-api-probe/<session-id>.log`; the excerpts below come from sessions
`01a1b09a`, `01a1b09d` and `01a1b09e`.

```
pi --model mistral/mistral-small-latest --no-extensions [-nt] -e pi-extension/spike/api-probe/index.ts
/probe-scenario <idle|stream|tool|turnend|settle|agentend>-<steer|followup>
/probe-dialog select|confirm|input [abortMs|none] [timeoutMs]
/probe-models
/probe-set-model provider/model-id
```

Every injected message carries a unique token, so "delivered" means the token appeared
in a `message_start` event rather than "the model seemed to notice". `run` is pi's
agent-run counter at the moment of delivery (`agent_start` increments it), which is how
"same run" and "new run" are decided. Text-only runs used `--no-tools` so a tool call
could not swallow the stream; the tool rows used a normal session.

| Situation | deliverAs | Runs | Delivered | Where | Delay after inject |
|---|---|---|---|---|---|
| idle (send starts a turn) | steer | 3 | 3/3 | new run | 1–5 ms |
| idle | followUp | 2 | 2/2 | new run | 1 ms |
| mid-stream, text answer | steer | 3 | 3/3 | same run, next turn | 1.6–1.7 s |
| mid-stream, text answer | followUp | 2 | 2/2 | same run, next turn | 0.3–1.1 s |
| while a tool call runs | steer | 2 | 2/2 | same run, after the tool turn | 4.3–6.7 s |
| while a tool call runs | followUp | 2 | 2/2 | same run, after the tool turn | 5.0–5.1 s |
| at the final `turn_end` | steer | 2 | 2/2 | same run (continuation) | 0–1 ms |
| at the final `turn_end` | followUp | 2 | 2/2 | same run (continuation) | 0–1 ms |
| at `agent_before_settle` | steer | 2 | 2/2 | continuation run, no settle in between | 0–1 ms |
| at `agent_before_settle` | followUp | 2 | 2/2 | continuation run, no settle in between | 0–1 ms |
| at `agent_end` | steer | 2 | 2/2 | continuation run | 1 ms |
| at `agent_end` | followUp | 2 | 2/2 | continuation run | 1 ms |

What the log showed, per row:

- **idle** — `sendUserMessage` starts a turn whatever `deliverAs` says; `idle=true` at
  the injection, `agent_start` within the same millisecond.
- **mid-stream** — `idle=false`, `pendingBefore=false`; the following `turn_end` logs
  `pending=true`, i.e. the message is queued and not yet consumed, and delivery lands
  in the next turn of the same run. A steer does **not** interrupt the in-flight
  assistant message; it is appended after it.
- **tool running** — injection inside `tool_execution_start`…`tool_execution_end`;
  consumed at the turn boundary that follows the tool result.
- **final `turn_end`** — `ctx.isIdle()` is `false` in that handler, so "final" is
  identified structurally: the turn's assistant message contains no `toolCall` part.
  The injected message is consumed immediately and the run continues.
- **`agent_before_settle` / `agent_end`** — the message is consumed immediately and a
  **new agent run starts without the previous one settling** (no `agent_settled` for
  the injecting run). This is the safest place to inject.
- **nothing was lost or delayed past the run**: no row ended with
  `hasPendingMessages() === true` at `agent_settled`.
- Early runs with a short answer settled before the 1.5 s timer fired; the probe logs
  those as `inject_skipped … settled_before_timer` and they are excluded from the
  table. `ctx.isIdle()` is `true` only at `agent_settled` (and when idle), never in
  `turn_end`, `agent_end` or `agent_before_settle`.

**Recommended delivery rule for P3 (A2 decision).**

1. `ctx.isIdle()` → send with `pi.sendUserMessage(text)`; `deliverAs` is irrelevant,
   the call starts a turn.
2. Busy → `pi.sendUserMessage(text, {deliverAs: "steer"})`. pi consumes it at the next
   turn boundary of the same run, measured 0.3–6.7 s depending on what is in flight.
3. **Detecting a steer that was not consumed**: `ctx.hasPendingMessages()` is the
   field — it is `true` at the `turn_end` / `agent_before_settle` where the message is
   still queued and `false` once consumed. A run that settles with it still `true` lost
   the message; the transcript check the probe used (`token` in
   `ctx.sessionManager.getBranch()`) is the belt-and-braces version and also catches a
   message that never reached the queue. If either says "not consumed", re-send once as
   a user message from `agent_settled` (the agent is idle there, so it starts a turn);
   key the re-send on the command id so a duplicate cannot be sent twice.
4. Chatterbox's dedicated boundary delivery (`{entries, continue: true}` at `turn_end`
   and `agent_before_settle`) is **not required** for `sendUserMessage`. Keep it as the
   fallback for any command that has to use `pi.sendMessage` custom messages — the
   steering-queue loss in chatterbox's README is about that path, not about
   `sendUserMessage`, which always triggers a turn.

## A3: model catalogue (#326)

```
models available=544 all=1580 current=mistral/mistral-small-latest scoped=0 error=none
model available mistral/mistral-small-latest name="Mistral Small (latest)" api=mistral-conversations contextWindow=262144 maxTokens=256000 reasoning=true input=text+image hasAuth=true
model available mistral/ministral-3b-latest name="Ministral 3B (latest)" api=mistral-conversations contextWindow=131072 maxTokens=128000 reasoning=false input=text+image hasAuth=true
model unavailable zai/glm-5.3 name="GLM-5.3" hasAuth=false
find mistral/mistral-small-latest -> mistral/mistral-small-latest
set_model request=mistral/ministral-3b-latest found=mistral/ministral-3b-latest before=mistral/mistral-small-latest
set_model result=true requested=mistral/ministral-3b-latest
set_model request=mistral/does-not-exist found=none before=mistral/mistral-small-latest
```

`ctx.modelRegistry.getAll()` includes models whose provider has no key
(`hasAuth=false`) — the picker must use `getAvailable()` or filter on
`hasConfiguredAuth(model)`, otherwise it offers models that fail at request time. The
`Model` object carries `id`, `name`, `api`, `provider`, `input`, `contextWindow`,
`maxTokens`, `reasoning`, `cost`; `pi.setModel(model)` takes that object whole and
returns a boolean (no throwing on a bad reference — a missing model is simply absent
from `find`).

## A4: dialog abort and timeout (#326)

```
dialog_start kind=select abortMs=2500 timeoutMs=none
dialog_end kind=select mode=abort result=undefined elapsedMs=2502
dialog_start kind=confirm abortMs=2500 timeoutMs=none
dialog_end kind=confirm mode=abort result=false elapsedMs=2502
dialog_start kind=input abortMs=2500 timeoutMs=none
dialog_end kind=input mode=abort result=undefined elapsedMs=2503
dialog_start kind=select abortMs=none timeoutMs=3000
dialog_end kind=select mode=timeout result=undefined elapsedMs=3001
```

`capture-pane` during the abort shows the dialog (`↑↓ navigate  enter select
escape/ctrl+c cancel`), after it the normal composer, and the next `/probe-log` command
runs — no stray prompt, editor still live. Source: `interactive-mode.ts:2681-2710`
(select resolves `undefined` on abort), `:2738-2745` (confirm → `result === "Yes"`),
`:2758-2792` (input → `undefined`), and the countdown/timeout path in
`components/extension-selector.ts:56-63` (timeout calls the same cancel callback). This
is what §4 needs for `ask_user`: aborting a remote-answered prompt is a normal cancel,
not an error, and no cleanup beyond resolving the promise is required.

