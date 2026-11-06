# pi-remote — pi extension

Registers a pi session with the llm-dock dashboard over a Unix socket, keeps the
registration alive with heartbeats, and reports its own presence through `/remote`.

This is P1-3a: `hello` / `heartbeat` / `bye`, the event mirror, the outbox and the
`/v1/events` sender. Commands and prompts arrive in later issues. The dashboard's
presence ingest exists; event storage is the next issue. The wire contract is in
`docs/plans/pi-remote.md` §3 under *Extension endpoint*.

## Layout

| Path | Purpose |
|---|---|
| `src/config.ts` | socket path + enabled flag; env `PI_REMOTE_SOCKET`, `PI_REMOTE=0`, file `~/.pi/agent/pi-remote.json`; env > file > default |
| `src/protocol.ts` | typed frames for `hello` / `heartbeat` / `bye` / `events`, `protocol: 1`, batch/body limits, builders, response parsing — pure |
| `src/events.ts` | event vocabulary, wire types, builders and the `EventSequencer` — pure, owns every event field name |
| `src/coalesce.ts` | delta coalescer (~100 ms / 2 KB), tool-update throttle (≤ 4/s), 64 KB tool-text truncation — pure |
| `src/outbox.ts` | bounded unacked-event queue, ack, oldest-delta drops and `gap` marker — pure |
| `src/sender.ts` | batches unacked events to `/v1/events`, shared backoff, rejoin on 404, `onOnline` flush |
| `src/mirror.ts` + `src/message-content.ts` | pi event → wire event mapping and content/usage extraction — pure |
| `src/index.ts` | pi lifecycle subscriptions, session setup, `/remote` handler and forwarding only |
| `src/transport.ts` | the only `node:http` module; `POST` over the socket with a timeout |
| `src/presence.ts` + `src/presence-types.ts` | presence state machine: offline → registering → online, heartbeat timer, backoff, idempotent `start()` / `stop()`, injected clock and request |
| `src/session.ts` | derive a session id from pi's session file name — pure |
| `src/backoff.ts` | the 1 s → 30 s retry policy — pure, reused by later reconnects |
| `src/activity.ts` | the idle/working flag fed to heartbeats |
| `src/pi-adapter.ts` | `ExtensionContext` → protocol frames (the `contextWindow` → `window` rename lives here) |
| `src/remote-command.ts` | `/remote` argument parsing and the status formatter — pure |
| `src/remote-command-handler.ts` | the `/remote` command's effects (stop/start/status) |
| `src/session-runtime.ts` | builds and starts Presence + Sender + Mirror for one `session_start`; owns their stop |
| `src/subscriptions.ts` | registers the pi event subscriptions used by the mirror |
| `test/` | `node --test` suites, the fake clock and the fake server |
| `test/contract/frames.json` | golden presence-contract fixtures shared with the dashboard's pytest |
| `test/contract/events.json` | golden events-contract fixtures shared with the dashboard's next issue |

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
sender batching/backoff/rejoin, mirror mapping, the golden presence and events
contracts, and integration tests against an in-process fake server on a temp Unix
socket (including a restart that resends unacked events).

Run the fake server by hand:

```
node --experimental-strip-types test/fake-server.ts --socket /tmp/pi-remote-fake.sock
```

`kill -USR1 <pid>` clears its session registry, which simulates a dashboard restart
(the next heartbeat gets `unknown_session` and the extension re-registers).
