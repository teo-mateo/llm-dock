# pi-remote — pi extension

Registers a pi session with the llm-dock dashboard over a Unix socket, keeps the
registration alive with heartbeats, and reports its own presence through `/remote`.

This is the P1 skeleton: `hello` / `heartbeat` / `bye` and `/remote` only. Event
mirroring, the outbox, commands and prompts arrive in later issues. The dashboard
side does not exist yet; the wire contract it must implement is in
`docs/plans/pi-remote.md` §3 under *Extension endpoint*.

## Layout

| Path | Purpose |
|---|---|
| `src/config.ts` | socket path + enabled flag; env `PI_REMOTE_SOCKET`, `PI_REMOTE=0`, file `~/.pi/agent/pi-remote.json`; env > file > default |
| `src/protocol.ts` | typed frames for `hello` / `heartbeat` / `bye`, `protocol: 1`, builders, response parsing — pure |
| `src/transport.ts` | the only `node:http` module; `POST` over the socket with a timeout |
| `src/presence.ts` + `src/presence-types.ts` | presence state machine: offline → registering → online, heartbeat timer, backoff, idempotent `start()` / `stop()`, injected clock and request |
| `src/session.ts` | derive a session id from pi's session file name — pure |
| `src/backoff.ts` | the 1 s → 30 s retry policy — pure, reused by later reconnects |
| `src/activity.ts` | the idle/working flag fed to heartbeats |
| `src/pi-adapter.ts` | `ExtensionContext` → protocol frames (the `contextWindow` → `window` rename lives here) |
| `src/remote-command.ts` | `/remote` argument parsing and the status formatter — pure |
| `src/index.ts` | pi lifecycle subscriptions plus a short `/remote` handler |
| `test/` | `node --test` suites, the fake clock and the fake server |
| `test/contract/frames.json` | golden wire-contract fixtures shared with the dashboard's pytest |

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
backoff), and an integration test against an in-process fake server on a temp Unix
socket.

Run the fake server by hand:

```
node --experimental-strip-types test/fake-server.ts --socket /tmp/pi-remote-fake.sock
```

`kill -USR1 <pid>` clears its session registry, which simulates a dashboard restart
(the next heartbeat gets `unknown_session` and the extension re-registers).
