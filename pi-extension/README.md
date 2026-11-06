# pi-remote — pi extension

Registers a pi session with the llm-dock dashboard over a Unix socket, keeps the
registration alive with heartbeats, and reports its own presence through `/remote`.

This covers `hello` / `heartbeat` / `bye`, the event mirror, the outbox and the
`/v1/events` sender, the command poller for `abort` (P3-1), and the `send_message`
handler with its delivery FIFO (P3-2). Prompts arrive in later issues. The wire contract is in `docs/plans/pi-remote.md` §3
under *Extension endpoint*.

## Layout

| Path | Purpose |
|---|---|
| `src/config.ts` | socket path + enabled flag; env `PI_REMOTE_SOCKET`, `PI_REMOTE=0`, file `~/.pi/agent/pi-remote.json`; env > file > default |
| `src/protocol.ts` | typed frames for `hello` / `heartbeat` / `bye` / `events` / `commands_poll` / `command_results`, `protocol: 1`, limits, builders, response parsing — pure |
| `src/events.ts` | event vocabulary, typed wire bodies, `EventStamper` (seq + ts) and `gapEvent` — pure, owns every event field name |
| `src/coalesce.ts` | delta coalescer (~100 ms / 2 KB) — pure |
| `src/throttle.ts` | tool-update throttle (≤ 4/s per call) — pure |
| `src/tool-text.ts` | JSON serialization + 64 KB UTF-8 truncation of tool args/results — pure |
| `src/outbox.ts` | bounded unacked-event queue, ack, oldest-delta drops, `discard`, and immutable per-range `gap` markers — pure |
| `src/sender.ts` | batches unacked events to `/v1/events`, shared backoff, rejoin on 404, `onOnline(ackedSeq)` flush, `bad_frame` discard + backoff, stop waits for in-flight |
| `src/mirror.ts` + `src/message-content.ts` | pi event → wire event mapping and content/usage extraction — pure |
| `src/index.ts` | pi lifecycle subscriptions, session setup, `/remote` handler and forwarding only |
| `src/transport.ts` | the only `node:http` module; `POST` over the socket with a timeout |
| `src/presence.ts` + `src/presence-types.ts` | presence state machine: offline → registering → online, heartbeat timer, backoff, idempotent `start()` / `stop()` / `rejoin()`, `onOnline(ackedSeq)`, injected clock and request |
| `src/session.ts` | derive a session id from pi's session file name — pure |
| `src/backoff.ts` | the 1 s → 30 s retry policy — pure, reused by later reconnects |
| `src/commands.ts` | command types, `dispatch`, and the 200-entry `CommandDedupe` — pure |
| `src/command-poller.ts` | owns the online-only long poll, results posting, backoff, 404 rejoin, start/pause/stop |
| `src/delivery.ts` | busy-send FIFO, content hash, head-only observe, settle/re-send selection — pure |
| `src/send-message.ts` | `send_message` validation and idle/steer handler over a small `SendPort` — pure |
| `src/activity.ts` | the working flag set by the mirror and read by the heartbeat |
| `src/pi-adapter.ts` | `ExtensionContext` → protocol frames (the `contextWindow` → `window` rename lives here) |
| `src/remote-command.ts` | `/remote` argument parsing and the status formatter — pure |
| `src/remote-command-handler.ts` | the `/remote` command's effects (stop/start/status) |
| `src/session-runtime.ts` | builds Presence + Sender + Mirror + command poller + delivery for one `session_start` with a fresh `instance_id`; owns `handle`, `pause`, `resume`, `stop` |
| `src/subscriptions.ts` | registers the pi event subscriptions used by the mirror |
| `test/` | `node --test` suites, the fake clock, fake server, fake-events and fake-commands handlers |
| `test/contract/frames.json` | golden presence-contract fixtures shared with the dashboard's pytest |
| `test/contract/events.json` | golden events-contract fixtures shared with the dashboard |
| `test/contract/commands.json` | golden command-contract fixtures shared with the dashboard |

## Load it

```
pi --model mistral/mistral-small-latest \
   --no-extensions \
   -e /path/to/llm-dock/pi-extension/src/index.ts
```

`-e` only, deliberately: installing this into `~/.pi/agent/extensions/` would register
**every** pi session on the machine, including the one you are using.

## Config

1. `PI_REMOTE=0` disables the extension.
2. `PI_REMOTE_SOCKET` sets the socket path.
3. `~/.pi/agent/pi-remote.json`: `{"enabled": true, "socket": "/path/to.sock"}`.
4. Default socket: `~/.cache/pi-remote/pi-remote.sock`.

Precedence is env > file > default. A malformed config file is ignored. A config-level
disable is authoritative: `/remote on` does not override `PI_REMOTE=0` or
`{"enabled": false}`.

## `/remote`

| Command | Does |
|---|---|
| `/remote` or `/remote status` | state (online / offline / disabled), socket path, session id, last heartbeat, next retry |
| `/remote off` | sends `bye` and stops registering for this session |
| `/remote on` | resumes registering (unless disabled by config) |

While the dashboard is absent, pi works normally: one warning when presence goes
offline, one notice when it returns, and retries at 1 s → 2 s → 4 s → … up to 30 s.

## Tests

```
cd pi-extension
npm test
```

The suite covers config precedence, the protocol builders, the presence state machine
with a fake clock (register, heartbeats, server restart, backoff schedule, stop during
backoff, `onOnline`/`rejoin`), event builders, coalescing/caps, outbox overflow/gap,
sender batching/backoff/rejoin, mirror mapping, command dispatch/dedupe, the poller
(online-only, results, repeat dedupe, error backoff, 404 rejoin, pause/stop), the
golden presence, events and commands contracts, delivery FIFO/settle rules,
send-message validation and idle/steer behaviour, and integration tests against an
in-process fake server on a temp Unix socket (including a restart that resends
unacked events).

Run the fake server by hand:

```
node --experimental-strip-types test/fake-server.ts --socket /tmp/pi-remote-fake.sock
```

`kill -USR1 <pid>` clears its session registry, which simulates a dashboard restart
(the next heartbeat gets `unknown_session` and the extension re-registers).
`kill -USR2 <pid>` enqueues an `abort` command for every registered session.
`kill -HUP <pid>` enqueues the fixed `send_message` text `Reply with exactly
REMOTE_OK and nothing else.`; the fake logs the `user_message origin: extension`
and the result. These are the live-check hooks.
