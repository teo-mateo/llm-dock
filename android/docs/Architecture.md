# Technical foundation

Architecture decisions for the llm-dock Android client. Companion to
[Plan_TOC.md](Plan_TOC.md), which says *what* the app does; this says
*how it is put together*.

Scope is deliberately narrow: the spine that F00–F04 establish and every
later feature inherits. Decisions that only affect one screen belong in
that screen's commit, not here.

---

## 0. How to read this

Architectural mistakes are expensive, but not uniformly so. Most choices
here are cheap to reverse; a few are not. The way to avoid an
unrecoverable mistake is **not** to be certain about everything — it is
to make sure the things you are uncertain about are isolated behind a
seam.

So the decisions are split:

**Expensive to reverse** — D1–D6. These shape the data flow. Getting one
wrong means rewriting features, not swapping a file. Spend the thinking
here.

**Cheap to reverse** — D7–D12. Library and layout choices. Each sits
behind an interface or is local enough that changing it is an afternoon.
Pick something sane and move on.

Each decision states what it costs to undo, so a future reader knows
whether to argue or just change it.

**Who decides what.** Everything in this file is a technical call and is
already made — nothing here is waiting on the project owner, who is not
an Android developer and should not be asked to arbitrate between
libraries. Decisions that genuinely need them are *product* decisions and
live in `Plan_TOC.md` §8. If a technical choice here turns out to be
wrong, the fix is a commit, not a conversation.

---

## Part I — Expensive decisions

### D1 · The server is the only source of truth for conversation content

**Decision.** No local database. No Room. Nothing on the device stores
messages, conversations, runs or services. The phone stores only: the
server URL, the credential (encrypted), and a handful of UI preferences.

**Why.** Three things converge on this. The offline reading cache was
dropped (F09, Dropped-Features). `chat.db` is shared live with the web
UI, so a local copy is stale the moment the desktop touches a thread.
And — the decisive one — the client's own streamed text is *not*
authoritative: a cancelled run persists nothing server-side, while a
failed run persists its partial. A local store would bake in the
assumption that what the client saw is what exists.

**If wrong.** Adding a cache later is additive — a repository already
mediates every read, so a cache slots in underneath. That is the
asymmetry that makes this the safe direction: building on a local store
and later removing it means rewriting every screen.

**Cost to reverse:** low in the add-a-cache direction, very high in the
other. Choose the cheap direction now.

---

### D2 · The run stream is a pure parser behind a transport interface

**Decision.** Two separate things:

```
interface SseTransport {                       // the only part that touches the network
    fun open(request: StreamRequest): Flow<String>   // emits raw `data:` payloads
}

fun parseFrame(payload: String): RunEvent      // pure, total, no Android, no IO
```

`RunEvent` is a sealed type covering every frame in F04's wire table —
`RunStarted`, `Delta`, `ToolCallPending`, `ToolCall`, `ToolResult`,
`Artifact`, `ParseWarning`, `Heartbeat`, `Done`, `MessageSaved`,
`ConversationUpdated`, `Failed`, `RunStatus` — **plus `Unknown(raw)`**.

**Why the `Unknown` case is not optional.** The dashboard is under active
development and typed frames are added without a client release. A parser
that throws on an unrecognised `type` turns a harmless new server frame
into a crashed chat screen. Same reason every DTO uses
`ignoreUnknownKeys = true`: the delta frames are raw upstream model
chunks whose shape is not ours to control.

**Why the split matters.** Everything hard about F04 and F09 — `[DONE]`
not ending the stream, `message_saved` arriving after it,
`conversation_updated` arriving after *that*, heartbeats, frames split
across socket reads, replay-then-live ordering — is testable as pure
functions over recorded fixtures, with no device and no server. That is
what makes "verified" mean something.

**Cost to reverse:** high. Every feature from F04 on consumes `RunEvent`.

---

### D3 · Streamed text and persisted messages are separate state

**Decision.** A thread's UI state is:

```
data class ThreadState(
    val messages: List<Message>,      // from the server, always
    val streaming: StreamingTurn?,    // ephemeral, never appended to `messages`
)
```

The streaming turn is **never** merged into the message list by the
client. On a terminal event:

| Terminal | What the server has | What the client does |
|---|---|---|
| `message_saved` | the assistant message, durable | refetch conversation, drop `streaming` |
| `{"error":…}` | partial content **plus** the error, persisted | refetch conversation, drop `streaming` |
| cancelled (stream just ends) | **nothing** — no assistant message | drop `streaming`, refetch |

**Why.** This one rule makes F04-R6, F04-R8 and F09-R2 fall out for free
instead of being three hand-written special cases. The tempting design —
accumulate deltas into a `Message` and keep it — is wrong in all three
directions at once: it invents a message that does not exist after a
cancel, it misses the error the server attached after a failure, and it
duplicates text when a reattach replays content the client already has.

**The reattach corollary.** Because the client keeps no authoritative
copy of in-flight text, replay is idempotent: drop `streaming`, rebuild
it from the replayed frames. No dedup logic anywhere.

**Cost to reverse:** high — it is the shape of the chat screen's state.

---

### D4 · Authentication is a transport layer, not a call-site concern

**Decision.** Three pieces, all in the HTTP stack, none visible to
features:

1. **Interceptor** — attaches `Authorization: Bearer <session>`.
2. **Authenticator** — on 401, silently re-authenticates from the stored
   credential and retries once (F01-R6). Bounded; on repeated failure it
   surfaces `AppError.Unauthenticated` and the app routes to Connect.
3. **Response interceptor** — stores a rotated `X-TOTP-Token` if one
   appears.

**Why retry-on-401 is safe here.** `require_auth` in `dashboard/auth.py`
returns 401 *before* invoking the route function, so a 401 on
`POST …/messages` means no run was created and no user message was
persisted. Retrying cannot double-send a turn. The request bodies are
small JSON and replayable.

Piece 3 is cheap insurance rather than a hot path: the dashboard only
emits `X-TOTP-Token` when a request authenticates via the `X-TOTP-Code`
header, which this app never does outside login. Handle it, don't
design around it.

**If this leaks into ViewModels,** every feature grows its own 401
handling and F01-R6 becomes unenforceable. That is the failure mode to
avoid.

**Cost to reverse:** high — it is cross-cutting by construction.

---

### D5 · Stream collection is screen-scoped. No background service.

**Decision.** The SSE collection lives in the chat screen's ViewModel.
Navigating away cancels the collection. There is **no** foreground
service, **no** app-scoped run manager, **no** WorkManager.

**Why this is not a compromise.** F04-R10 explicitly says the app should
unsubscribe on navigation — the server keeps generating and persists the
reply regardless. F09-R2 reattaches with full replay on return. And
notifications are dropped (F09-R6), which removes the only requirement
that would have forced background execution.

The instinct for a chat client is "background work needs a service". Here
the server *is* the background worker. Building a service would add
process lifecycle, notification permissions and battery accounting for no
requirement.

A ViewModel survives configuration change, so rotation does not drop the
stream; leaving the screen does. That is exactly the specified
behaviour.

**One accepted gap.** If the user leaves during the drain phase — after
`message_saved`, before `conversation_updated` — the auto-generated title
is missed. F02-R1 already requires refreshing the list on return, which
recovers it.

**Cost to reverse:** moderate. Adding a service later is additive if
D2/D3 hold, because the run layer does not assume who is collecting.

---

### D6 · One wire↔domain seam, and only one

**Decision.** kotlinx.serialization DTOs at the network boundary, mapped
once into domain models. Features never see a DTO.

**Why — these are not hypothetical quirks:**

- `mcp_servers` is a read-only array in the payload; writes go through
  `mcp_servers_json`, a JSON **string** (F08-R2). Two names, one concept.
- `main_service` is either a service name or `openrouter:<model-id>`
  (F07). Parsing that prefix in each screen guarantees inconsistency.
- Timestamps are UTC ISO strings needing local rendering (F00-R11).
- Deltas are raw OpenAI chunks: `choices[0].delta.content`, with
  reasoning arriving as either `reasoning_content` **or** `reasoning`
  depending on the model.
- `active_run` and `last_run` are trimmed shapes, not full run objects.

Normalise each once, in the mapper. The domain model should make illegal
states hard to express — e.g. a `ModelRef` sealed type of
`Local(name)` / `OpenRouter(id)` rather than a bare `String`.

**Cost to reverse:** high once features consume domain types.

---

## Part II — Cheap decisions

### D7 · Dependencies — verified, not guessed

Every version below was resolved and built against this exact toolchain
(AGP 9.3.1 / Gradle 9.5.1 / Kotlin 2.4.10 / compileSdk 37 / minSdk 26)
before being written down. `checkDebugAarMetadata` — the gate that failed
during project setup — passes, and a JVM test using serialization,
coroutines-test and turbine runs green.

| Purpose | Artifact | Version |
|---|---|---|
| HTTP + streaming | `com.squareup.okhttp3:okhttp` | 5.4.0 |
| JSON | `org.jetbrains.kotlinx:kotlinx-serialization-json` | 1.11.0 |
| Coroutines | `org.jetbrains.kotlinx:kotlinx-coroutines-android` | 1.11.0 |
| Preferences | `androidx.datastore:datastore-preferences` | 1.2.1 |
| Credential storage | ~~`androidx.security:security-crypto`~~ | **Do not use — deprecated. See U1.** |
| Navigation | `androidx.navigation:navigation-compose` | 2.9.8 |
| ViewModel in Compose | `androidx.lifecycle:lifecycle-viewmodel-compose` | 2.11.0 |
| Images | `io.coil-kt.coil3:coil-compose` + `coil-network-okhttp` | 3.5.0 |
| Test — HTTP | `com.squareup.okhttp3:mockwebserver3-junit4` | 5.4.0 |
| Test — Flow | `app.cash.turbine:turbine` | 1.2.1 |
| Test — coroutines | `kotlinx-coroutines-test` | 1.11.0 |

Plugin `org.jetbrains.kotlin.plugin.serialization` (version = `kotlin`)
applies cleanly alongside AGP 9's built-in Kotlin — verified, since AGP 9
rejects `org.jetbrains.kotlin.android` and it was not obvious the
compiler plugins would still work.

**Rule for anything added later:** resolve and build it before writing it
into the catalog. The androidx trio (`core` 1.19 / `lifecycle` 2.11 /
compileSdk 37) moves together and drags AGP with it.

**OkHttp over Ktor** for streaming maturity and because `Authenticator`
maps directly onto D4. Both would work. It sits behind `SseTransport`
(D2) and the repository interfaces, so swapping it touches the transport
implementation only.

### D8 · Package layout — single module, package-by-feature

```
com.hpz.llmdockchat/
  core/
    net/     OkHttp setup, AuthInterceptor, AuthAuthenticator, SseTransport
    auth/    CredentialStore, SessionManager
    error/   AppError
    ui/      theme tokens, shared composables
  data/
    dto/     wire types
    ChatRepository, ServicesRepository, mappers
  feature/
    connect/ conversations/ chat/ models/ logs/ settings/
```

Multi-module is premature for one app built serially by one contributor.
Repositories are shared, so they live in `data/`, not inside a feature.

### D9 · Dependency injection — manual container

A single `AppContainer` constructed in `Application`, handed to
ViewModels through a factory. Hilt adds annotation processing and build
time for a graph this small; it stays available if the app grows.

Dispatchers are injected, never hardcoded, so tests control time.

### D10 · Error model — one sealed type carrying the server's words

```
sealed interface AppError {
    data class Http(val status: Int, val message: String) : AppError   // server's {"error": …}
    data object Unauthenticated : AppError
    data class Network(val cause: Throwable) : AppError
    data class Unexpected(val cause: Throwable) : AppError
}
```

F00-R4 requires the server's message to reach the user everywhere. If
each feature parses error bodies itself, some will forget and show
"Something went wrong" over a perfectly good explanation. The 409 cases
(concurrent run, delete during run) depend on this.

### D11 · Theme — semantic tokens defined once

Both palettes (F00-R7) derive from one token set lifted from the mockups:
surfaces, text tiers, accent, and the four engine chip colours. Screens
reference tokens, never literals. A screen that hardcodes a hex becomes a
light-mode bug.

### D12 · Navigation — Navigation Compose, two-tab scaffold

Bottom bar on the two list screens; thread, model detail and logs are
pushed destinations without it (F02-R7). Nav3 exists and is stable, but
Navigation Compose 2.9.8 is better documented for a graph this simple.

---

## Part III — Performance traps to design around

Two are foreseeable now and cheap to prevent, expensive to retrofit.

### P1 · Coalesce deltas before they reach UI state

Tokens arrive faster than the display refreshes. Pushing every delta
straight into Compose state recomposes the message column dozens of times
a second and will jank on a long answer — which F04-R3 forbids.

**Decision.** The run layer buffers deltas and emits accumulated text on
a short time window (~16–32 ms). The UI sees a smooth text stream, not a
token firehose.

Note the server already coalesces in its replay buffer, so a reattach
delivers a few large chunks then live tokens. The client must not assume
one delta equals one token in either case.

### P2 · Markdown is re-parsed on every emission

F05-R1 requires rendering *during* streaming without flicker. With P1 in
place this is roughly 30–60 parses a second of a growing string — enough
to matter. Keep the streaming turn's rendering isolated from the
persisted message list so recomposition is scoped to one element, and
key list items stably.

---

## Part IV — Testing

The strategy that makes a "[DONE]" mark trustworthy.

**JVM unit tests carry the load.** Everything in D2/D3/D4 is testable
with no device and no server:

- frame parsing, including unknown frames and split reads
- `[DONE]` not terminating; `message_saved` then `conversation_updated`
- terminal handling for completed / failed / cancelled (D3's table)
- reattach replay producing no duplicate text
- 401 → silent re-auth → retry, and the bounded-failure path
- the `mcp_servers` / `mcp_servers_json` asymmetry
- `openrouter:` prefix round-tripping

**Fixtures are recorded from the real dashboard**, not hand-written —
hand-written fixtures encode what you *think* the server sends.

```bash
T=$(android/scripts/dev.sh token)
curl -N -s -X POST "http://localhost:3399/api/chat/conversations/$CONV/messages" \
  -H "Authorization: Bearer $T" -H 'Content-Type: application/json' \
  -d '{"content":"count to five"}' \
  > android/src/app/src/test/resources/fixtures/send-simple.sse
```

Capture one per scenario: plain answer, reasoning model, tool call,
failure, cancel, reattach-with-replay. Replay through MockWebServer.
These also catch the day the wire format changes.

**Device tests only for what needs a device** — layout, gestures, and the
four levers in `scripts/dev.sh`: theme switch (F00-R7), font scale
(F00-R8), airplane mode (F09-R4), clear-data (F01). Compose UI tests are
slow; use them where a JVM test genuinely cannot reach.

**A feature is done when its Must criteria are backed by a passing test
or a screenshot** — not by an assertion that it works.

---

## Part V — Known uncertainties

Honest list. Each is isolated so being wrong is survivable.

**U1 · `androidx.security:security-crypto` status. RESOLVED 2026-07-25 —
the library is deprecated; do not use it.** The release notes for
1.1.0-beta01 (4 June 2025) say: *"Deprecated all APIs in favour of
existing platform APIs and direct use of Android Keystore."* That covers
`EncryptedSharedPreferences`, `EncryptedFile`, `MasterKey` and
`MasterKeys`. Version 1.1.0 stable (30 July 2025) ships the deprecation,
so resolving and building says nothing about whether it should be used.

**Consequence for F01:** back `CredentialStore` with the platform
Keystore directly — a Keystore-held AES/GCM key, ciphertext in DataStore.
The interface mitigation held: F00 added no dependency on the library, so
nothing has to be unwound.

**U2 · Emulator-only verification.** No physical device. Layout at other
densities, real camera input and real network transitions are unverified
until someone runs it on a phone.

**U3 · Coalescing window.** 16–32 ms is a starting point, not a measured
value. Tune against a real long answer from the gemma service on :3301.

---

## Out of scope for this document

Per-screen composition, list item design, animation, string resources,
and anything specific to F10–F13. The Models tab is straightforward and
specifying it before writing it would be guessing. This document grows
when a decision turns out to be cross-cutting — not before.
