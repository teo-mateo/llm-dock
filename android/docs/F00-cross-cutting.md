# F00 · Cross-cutting requirements

**Mockup:** applies to all screens · **Depends on:** nothing · **Blocks:** everything

Requirements that are not owned by one screen. Every other feature file
assumes these hold and does not restate them.

---

## F00-R1 · One configured server, one base URL (Must)

Every request the app makes is built from a single stored base URL. No
endpoint is hardcoded to a host, port or scheme. Both `http://host:3399`
(LAN, emulator via `10.0.2.2`) and `https://host` (behind the proxy) must
work, including the SSE endpoints.

**Acceptance criteria**

- [ ] Changing the server URL in Settings and returning to the chat list
      makes all subsequent calls hit the new host — with no app restart.
- [ ] The app works against `http://10.0.2.2:3399` on the emulator and
      against an `https://` host, with no code change.
- [ ] A URL entered with a trailing slash, or with `/api` already on the
      end, is normalised rather than producing a broken request path.

## F00-R2 · Authorization on every request (Must)

Every call carries `Authorization: Bearer <token>`, except the three that
establish a session and so cannot depend on one: `GET /api/health`,
`POST /api/auth/login` (which authenticates with an `X-TOTP-Code` header)
and `POST /api/auth/session` (which carries the dashboard password as its
own bearer). A caller-supplied `Authorization` header is never overwritten.
If a response carries an `X-TOTP-Token` header, the app replaces its stored
token with that value. See *Deviations* for why those three are exempt.

**Acceptance criteria**

- [ ] A request made with no stored token — other than those three — never
      reaches the network; the app routes to Connect instead.
- [ ] After a response carrying `X-TOTP-Token`, the next request uses the
      new token.

## F00-R3 · 401 is a normal event (Must)

The server keeps sessions in process memory, so a dashboard restart
invalidates every token. On any 401 the app discards the token, returns to
Connect, and **preserves what the user was doing**: the server URL, the
open conversation, and any unsent draft text or attachments.

**Acceptance criteria**

- [ ] Restart the dashboard mid-session, then act in the app: it shows
      Connect, not an error toast on a dead screen.
- [ ] After re-entering a TOTP code, the app returns to the screen it was
      on and the draft is still in the composer.
- [ ] A 401 during a streaming turn does not lose the user's message from
      the thread view.

## F00-R4 · Errors are shown, never swallowed (Must)

The dashboard returns `{"error": "..."}` with a meaningful message on
every failure path. The app surfaces that message. A failed request never
leaves a blank screen, an infinite spinner, or a silently empty list.

**Acceptance criteria**

- [ ] With the dashboard stopped, every screen shows a readable failure
      state with a retry affordance — no spinner that never resolves.
- [ ] A 409 from a second concurrent send shows the server's message ("A
      run is already active for this conversation"), not a generic error.
- [ ] An error state is visually distinct from an empty state.

## F00-R5 · Loading, empty and error states everywhere (Must)

Every list and detail screen has four defined states: loading, populated,
empty, failed. The empty state says what would fill it.

**Acceptance criteria**

- [ ] Conversation list, model list, log view and project groups each
      render a distinct empty state before any data exists.
- [ ] No screen shows stale data from a previous entity while loading a
      new one.

## F00-R6 · Streaming client capabilities (Must)

Four endpoints stream Server-Sent Events over an authenticated request:
chat runs, service status, service logs and GPU stats. The app's stream
reader must:

- send the `Authorization` header (so `EventSource` is not usable);
- parse `data:` frames, ignore `:` comment keepalives, and tolerate a
  frame split across reads;
- treat a `{"type": "heartbeat"}` frame as liveness, not content;
- **not** close the connection on `data: [DONE]` — later frames follow it;
- survive a stream that ends without a terminal frame, and reconnect.

**Acceptance criteria**

- [ ] A stream left open through a quiet period (>30 s) stays connected
      through keepalives and heartbeats.
- [ ] A frame arriving split across two socket reads is parsed correctly.
- [ ] Killing the network mid-stream produces a visible reconnecting
      state, not a hang and not a crash.

## F00-R7 · Follow the system theme (Must)

The app has both palettes and switches with the device. The mockups'
palette is the dark theme, unchanged. The light theme is derived from it —
same hierarchy, same accent, same engine chip colours, inverted surfaces —
so the two read as one app rather than two designs.

Both must meet the same contrast bar: model output is long-form text read
for minutes at a time.

**Acceptance criteria**

- [ ] Dark mode matches the mockup palette; no unstyled system-default
      surfaces appear.
- [ ] Light mode is fully styled — no dark-on-dark or light-on-light text
      anywhere, including code blocks, log output, chips, sheets and
      dialogs.
- [ ] Switching the device theme while the app is open re-themes it
      without a restart and without losing screen state.
- [ ] Engine chip colours (F02-R2) stay distinguishable from each other in
      both themes.
- [ ] Log level colouring (F12-R4) stays legible in both themes.

## F00-R8 · Reading comfort (Must)

Model output is long-form text read on a phone. The app honours the
device font scale, and the text-size control in Settings (F13) applies to
message bodies.

**Acceptance criteria**

- [ ] At the largest system font scale, no message text is clipped or
      overlapped.
- [ ] The Settings text-size control changes message body size and the
      choice survives a restart.

## F00-R9 · Confirm before anything destructive or expensive (Must)

These actions require an explicit confirmation, each naming what is about
to happen: delete a conversation, delete a message, edit-and-resend
(truncates the thread), stop a container, start a container when VRAM is
contended.

**Acceptance criteria**

- [ ] Each listed action shows a confirm naming the specific target.
- [ ] Cancelling leaves server state untouched — verified by refetching.

## F00-R10 · The app never writes configuration (Must)

Endpoints exist to create and edit services, rotate keys, edit the MCP
registry, the default system prompt and the OpenRouter list. The app must
never call any of them. Managed prompts and the OpenRouter list are
read-only on the phone; the project endpoints are not called at all.

**Acceptance criteria**

- [ ] No code path issues POST/PUT/DELETE to `/api/services` (collection),
      `/api/services/<name>` (PUT/DELETE), `/api/chat/prompts`,
      `/api/chat/mcp-registry/*`, `/api/chat/settings/*` or
      `/api/default-api-key/*`.
- [ ] No code path touches `/api/chat/projects*` by any method.
- [ ] The only service mutations in the app are `.../start` and
      `.../stop`.

## F00-R11 · Timestamps (Must)

Server timestamps are UTC ISO-8601. The app renders them in device local
time, relative for recent items ("14:32", "yesterday").

**Acceptance criteria**

- [ ] A conversation updated a minute ago shows a relative time, not a
      UTC wall-clock that is off by the device's offset.

## F00-R12 · No polling where a stream exists (Should)

Service status, GPU stats and logs each have an SSE endpoint. Use them.
Fall back to the one-shot GET only when a stream cannot be established.

**Acceptance criteria**

- [ ] With the Models tab open and idle, the app issues no repeated
      `GET /api/services` requests — verified in the dashboard log.

---

## Out of scope

- Offline caching of conversations (see Dropped-Features).
- Background work of any kind — the app does nothing while closed.
- Analytics, crash reporting, remote config.

## Deviations from the mockups

None. These requirements are additive to the screens.

## Deviations

**F00-R2 — two more endpoints go out without a session token.** As written,
`GET /api/health` is the only call that does not carry
`Authorization: Bearer <token>`. Implementing it that literally makes signing in
impossible, because neither login route is decorated with `require_auth` in
`dashboard/routes/system.py`:

- `POST /api/auth/login` authenticates with an `X-TOTP-Code` header and no
  `Authorization` at all. On a cold install there is no token to attach, so
  requiring one would reject the request before it left the device.
- `POST /api/auth/session` authenticates with the dashboard password as its
  bearer. Overwriting that with a session token — the very thing the call
  exists to obtain — would break it.

So the rule the transport implements is: a request that already carries an
`Authorization` header is left untouched, and `GET /api/health`,
`POST /api/auth/login` and `POST /api/auth/session` are exempt from needing a
stored token (`Endpoints.establishesSession`). Every other call is unchanged.
The same three are exempt from the 401 re-authentication path, so a wrong
password reports itself rather than looping through the credential exchange.

**F00-R2 — narrowed by F01-R6: a request with no stored token may now reach
the network.** The first criterion above ("never reaches the network; the app
routes to Connect instead") describes what F00 shipped, and F01 changed it:
the transport now mints a token from the stored credential first, and fails
the request locally only when it cannot. Without that, a dashboard restart
would send a signed-in user to Connect, which F01-R6 forbids. See F01's
*Deviations*.

**F00-R2 — `X-TOTP-Token` cannot be exercised against the real dashboard.**
`require_auth` emits that header only when a request authenticates via the
`X-TOTP-Code` header, and the two login routes bypass `require_auth` entirely
and return their token in the JSON body. No request this app is permitted to
make will therefore ever receive an `X-TOTP-Token`. The handling is implemented
and tested against MockWebServer, and is best read as insurance against a
future server change rather than a live code path.

---

## Carried-forward criteria

F00 is marked `[DONE]`: every Must requirement's **mechanism** is
implemented and tested. But many of F00's acceptance criteria are
screen-level, and F00 deliberately builds no screens — so they cannot be
verified here. Per `WORK_INSTRUCTIONS.md` §7 they are carried forward,
recorded below, and must be verified in the feature that introduces the
screen. **Do not treat this table as optional.**

| Criterion | Verify in |
|---|---|
| R1 · changing the URL *in Settings* retargets calls with no restart | F13 |
| R3 · server URL, open conversation and draft preserved across a 401; user's message not lost mid-stream | **CLOSED.** Routing landed in F01; the draft survives rotation, backgrounding and a force-stop, verified in F04. The 401-specific round trip is largely moot now: F01-R6 supersedes F00-R3, so a 401 re-authenticates silently and the screen — and its draft — never changes. Connect is reached only when re-auth itself fails. |
| R4 · readable failure state with a retry affordance, distinct from empty | **CLOSED in F02** — verified on device with the network down. The 409-specific wording lands with F04's concurrent-send path. |
| R5 · loading / populated / empty / failed | **CLOSED for the conversation list in F02.** Still to check on each further list/detail screen: F10, F12. |
| R6 · a stream quiet for >30 s stays connected; a visible reconnecting state | F09 (chat runs), F12 (logs) |
| R7 · theme switch preserves screen state | **CLOSED in F02** — scroll position survives a live `dev.sh theme` switch. |
| R8 · Settings text-size control changes message bodies and survives restart | F13, against F05 message bodies |
| R9 · every destructive action confirms, naming its target | F06 (delete message, edit-and-resend), F11 (stop container) |
| R11 · a recently-updated conversation shows a relative local time | **CLOSED in F02** — "just now", "yesterday", "Wed", "14 Jul" seen live. |
| R12 · no repeated `GET /api/services` while the Models tab idles | F10 |

Verified and complete in F00, needing no later confirmation: R1
normalisation and resolution, R2, R6's framing behaviour (split reads,
comment keepalives, opaque payloads, cancellation and socket teardown),
R7's palettes and live theme switching, R10, and R11's formatter.

R8's first criterion is **partly satisfied already**: typography is `sp`
throughout and the review confirmed at 1.5x system font scale that text
reflows with nothing clipped or overlapped.
