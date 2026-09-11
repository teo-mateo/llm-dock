# Android: per-conversation reasoning level

Add the reasoning-level selector — already shipped on the web client in
`feat/chat-reasoning-level-selector-*` — to the Android client, as feature **F15**.

Backend work is done. This plan is client-only: no dashboard file changes.

## 1. Goal and scope

**User-visible outcome.** On a phone thread whose model declares reasoning
levels, the user sees the current level, can pick one of the declared levels or
"Model default", and that choice applies to the next turn. A level the model
stopped declaring is visible and clearable, never silently sent. A thread whose
model declares nothing shows no control at all.

| ID | Requirement |
|---|---|
| R1 | The ladder offered is exactly the list the server reports for the thread's service, in declaration order. Nothing is synthesised, reordered, renamed, or added ("high" is not inserted just because neighbours exist). |
| R2 | The control shows: current selection, and the full option set = "Model default" (clears) + each declared level, in order. |
| R3 | No ladder → no control, anywhere. A stored level with no ladder → the control shows, marked as not offered, tappable to clear. |
| R4 | The choice persists server-side (`conversations.reasoning_level`) and is visible in the web UI on the same thread. Survives app restart and thread re-open. |
| R5 | A ladder edited on the dashboard reaches an already-open thread with no manual refresh and no app update — at the latest by the time the user next opens the level sheet, sooner if the model picker's stream is live (§3.3 records why that is the guarantee, and why it departs from F00-R12). |
| R6 | A level the server drops for a run (ladder lost it between write and run) is reported to the user, not silently ignored. |
| R7 | Failure to write the choice is shown and the UI reverts to what the server has. Never a silent no-op (F00-R4). |
| R8 | OpenRouter threads show no control. A service without a ladder provably sends no reasoning field — i.e. no request-shape change for the 90 % of services that have no ladder. |

**Constraints (from `android/docs/Plan_TOC.md`).**

- **R-A backend parity**: everything below uses endpoints that exist today. No
  new server code.
- **R-B web parity**: the phone must not *disagree* with the web client about
  what a level means or when it applies. Placement may differ (§3.4).
- **F00-R10**: the app never writes *configuration*. `reasoning_level` is
  conversation state (written by `PUT /api/chat/conversations/<id>`, exactly
  like `main_service` and `mcp_servers_json`), not service config — so it is in
  bounds, and the app still must not touch `PUT /api/services/<name>`.
- **F00-R12 (Should)**: no polling where a stream exists. §3.3 records a
  deliberate, documented exception.

**Non-goals.** Setting a level in the new-chat sheet (web does; §6 explains the
deferral and its cost). Editing a service's ladder from the phone (F00-R10).
Token budgets (the backend rejects `name:budget` syntax outright). Level display
in the conversation list. Anything in the Models tab beyond the optional
read-only row in P5.

## 2. Verified current behaviour

Baseline: `origin/main` at `51a39e9` — **the backend half is merged** (PR #128,
"Per-service reasoning levels, declared at config time and selectable in chat").
The app work therefore has no upstream gate left; branch from a fresh
`origin/main` per `AGENTS.md`, and `git fetch` first, since a stale local
`origin/main` silently branches off pre-#128 code where the ladder does not
exist at all.

| Claim | Evidence | Kind |
|---|---|---|
| A service declares levels as a CSV string in `services.json`; `off` is reserved, ≤8 levels, ≤120 chars, no `:` | `dashboard/reasoning_levels.py: validate_levels`, `LEVEL_NAME_RE`, `MAX_LEVELS` | source inspected |
| `GET /api/services` and the SSE snapshot expose the ladder **parsed** as `[{"id": "low", "effort": "low"}]`, `[]` when undeclared, in **both** payload branches (container exists / `not-created`) | `dashboard/docker_utils.py: get_docker_services` lines 217 and 247; built by `_parsed_reasoning_levels`, tolerant (invalid → `[]`, warns once) | source inspected |
| Every successful service config write broadcasts `{"type":"delta"…, "action":"metadata-changed", "status": null, "metadata": {"reasoning_levels": [...]}}` with the post-update ladder (so an unrelated param edit refreshes it too) | `dashboard/routes/services.py: update_service` (~line 355-365, after `existing.update(data)`) | source inspected |
| The favourite toggle emits the **same** `metadata-changed` action with `metadata: {"favorite": …}` and **no** `reasoning_levels` key | `dashboard/routes/services.py` ~line 700-706 | source inspected |
| `POST /api/chat/conversations` accepts `reasoning_level`, rejects one the service doesn't declare with 400 `code: "invalid_reasoning_level"`-carrying error; absent key = `NULL` = send nothing | `dashboard/chat/routes.py: create_conversation`, `_reasoning_level_error` | source inspected |
| `PUT /api/chat/conversations/<id>` validates a non-null `reasoning_level` against `data.main_service or existing.main_service`, so a combined model+level write is checked against the **new** service; `null` always clears | `dashboard/chat/routes.py: update_conversation` | source inspected |
| Both the detail **and** the list payload carry `reasoning_level`: `list_conversations` renders `[c.to_dict() for c in convs]` over full `Conversation` objects, and `to_dict` includes the key. This client still reads it off the detail only — `ConversationDto` (the **Android** DTO, not a backend type) simply does not model the list field, so the ladder-adjacent list payload is untouched here | `dashboard/chat/models.py: Conversation.to_dict` line 201, `dashboard/chat/routes.py: list_conversations`, `android/…/data/dto/ConversationDto.kt` | source inspected |
| At run creation the level is re-checked and dropped per-run if no longer offered; the resolved value and a `reasoning_level_note` ride the **synthesized** `run_started` frame | `dashboard/chat/routes.py: _effective_reasoning_level`, `_start_run_response`; `dashboard/chat/run_manager.py: ChatRunManager.observe(run_started_extra=…)` | source inspected |
| A **reattaching** client gets a plain `run_started` with no extras — the note is send-path only | `dashboard/chat/run_manager.py: observe` docstring + call site | source inspected |
| Request mapping is per-engine and lives only server-side; `ik_llamacpp`, `tabbyapi`, `ds4`, OpenRouter send nothing | `dashboard/reasoning_levels.py: request_fields` | source inspected |
| An OpenRouter thread can never hold a level: `_service_reasoning_levels` returns `[]` for an `openrouter:` name, so any non-null level is rejected at write | `dashboard/chat/routes.py: _service_reasoning_levels` | source inspected |
| The app has no ladder anywhere in its wire types: `ServiceDto` carries name/status/kind/host_port/favorite/exit_code/model_size_str/created only | `android/src/app/src/main/java/com/hpz/llmdockchat/data/dto/ServiceDto.kt` | source inspected |
| `ServiceStreamEvent.Delta` reads only `service_name`, `status`, `metadata.favorite` — a ladder-carrying delta currently decodes to `Delta(name, null, null)` and the ladder is dropped | `core/net/ServiceStreamEvent.kt: deltaFrame`, `data/ServicesStreamRepository.kt: mergeServiceEvent` | source inspected |
| `ConversationDetailDto` has no `reasoning_level`; `ConversationDetail` has no such field | `data/dto/ChatThreadDto.kt`, `data/model/ChatMessage.kt: ConversationDetail` | source inspected |
| `RunEvent.RunStarted` carries `runId` only; the parser is `ignoreUnknownKeys`, so the extra frame fields are silently dropped today rather than breaking | `core/net/RunEvent.kt: parseFrame/typedFrame` | source inspected |
| `ApiJson` is `explicitNulls = false`, so a `null` field on a `@Serializable` DTO is **omitted**, not sent as JSON null | `core/net/ApiJson.kt` | source inspected |
| `ApiClient.request(method, path, deserializer, body: String, headers)` takes a raw body string — a hand-built JSON body is available without touching `ApiJson` | `core/net/ApiClient.kt: request` | source inspected |
| All per-thread settings live in `ChatSettingsSheet` (model row, prompt rows, tool rows); the thread header shows title + model name; the composer row is attach + field + send/stop | `feature/thread/ChatSettingsSheet.kt`, `feature/thread/ThreadScreen.kt: ThreadHeader`, `feature/thread/ComposerRow.kt` | source inspected |
| Writes are ordered by an explicit lock because a whole-array PUT can be lost to a concurrent one | `feature/thread/ThreadViewModel.kt: toolsWriteLock`, `latestToolsToggle` | source inspected |
| This rig declares a ladder for exactly one service today: `vllm-qwen3-8-flash-next-mixed-nvfp4-fp8` = `off,low,medium,xhigh`, `template_type: "vllm"`, port 3301 | `services.json` (read at baseline) | probe run (`python3 -c` over `services.json`) |
| The **running** dashboard already serves the ladder on the live endpoint, so no environment gate remains: 22 services, one with a non-empty `reasoning_levels`, and `template_type` present on every row | `GET /api/services` against `localhost:3399` at baseline | probe run (`curl` + `python3`) |
| That ladder-bearing container is up (`Up 7 hours`), so D1/D2 can send a turn without starting or stopping anything | `docker ps` at baseline | probe run |

**Unknown / to verify during implementation.** Whether the running dashboard
build the emulator talks to (`http://10.0.2.2:3399`) already serves
`reasoning_levels` on `/api/services` — it does only if the host process is
running this branch. Verify with
`curl -s -H "Authorization: Bearer $TOKEN" localhost:3399/api/services | jq '.services[] | select(.reasoning_levels != [])'`
before starting device verification; a stale dashboard makes every criterion
unreproducible, not failing.

## 3. Design and contracts

### 3.1 Representation

Canonical client value: `List<String>` of level ids, **declaration order
preserved**, deduplicated, empty when the ladder is absent, unparsable, or the
thread is on OpenRouter.

- Wire form on `/api/services` and its snapshot: `[{"id","effort"}, …]`. Only
  `id` is used by the client (`effort` is the request-side token and the server
  sets it equal to `id` today); it is parsed and discarded, not modeled further.
- `missing` vs `[]` are the same thing to this client's **domain** type: no
  control. The server already collapses "invalid" to `[]`, so the client never
  sees malformed data and needs **no grammar parser of its own** — this is why
  the ladder is read off the service payload rather than off
  `GET /api/services/<name>`'s raw config string, which would force a Kotlin
  re-implementation of `validate_levels` and could then disagree with the
  enforcement point.
- **The wire event type is tri-state even though the domain value is not.**
  `ServiceStreamEvent.Delta` gains `reasoningLevels: List<String>? = null`
  where `null` means *this frame said nothing about the ladder* and
  `emptyList()` means *this service declares none*. Collapsing the two is what
  makes a favourite toggle on the dashboard empty a ladder (T2's anti-clear
  test is the guard), and the collapse cannot happen at parse time — it has to
  survive to `mergeServiceEvent`, which is the only place that knows whether to
  write the field.
- Selection is tri-state in the client: `null` = "Model default" (server `NULL`,
  sends no reasoning field), `"off"` = an *active* instruction to stop thinking,
  `"low"`/etc. = a declared token. **`null` and `"off"` are never interchangeable.**
- Order is display order and is never sorted client-side; the operator's
  declaration order is the ladder's meaning.

### 3.2 Write contract, including the null problem

`PUT /api/chat/conversations/<id>` with `{"reasoning_level": <id>}` sets it;
`{"reasoning_level": null}` clears it. Because `ApiJson.explicitNulls = false`,
a `@Serializable` DTO field set to `null` is **omitted** — which means a naive
`UpdateReasoningLevelRequestDto(reasoningLevel = null)` is a no-op request that
returns 200 and clears nothing. Two body builders, one repository method:

```kotlin
// proposed: data/ConversationsRepository.kt
suspend fun setReasoningLevel(id: String, level: String?): Result<Unit>
// body = buildJsonObject { put("reasoning_level", level?.let { JsonPrimitive(it) } ?: JsonNull) }
```

The body is built as a `JsonObject` literal, not via `ApiJson.encodeToString` of
a data class, so clearing really does put `"reasoning_level": null` on the wire.
This must be pinned by a test that asserts the exact body string for the clear
case (§5 T3) — it is the single easiest way to ship a "clear" button that
silently does nothing.

Server-side failure modes the client must handle: 400 when the level is not
offered (possible when the ladder changed between render and tap — the same
window the web client handles), 401 (transparent re-auth, already automatic),
network. All map through the existing `appError`/`displayMessage` path.

### 3.3 Where the ladder comes from

`GET /api/services` once per thread load, through the existing
`ServicesRepository.list()` (which already returns every service unfiltered),
stored on `ThreadUiState.Loaded` as a **map** — `laddersByService:
Map<String, List<String>>` — with `ladder: List<String>` exposed as a derived
property, `laddersByService[conversation.mainService].orEmpty()`.
`ServicesRepository` becomes a new constructor dependency of `ThreadViewModel`
(`core/AppContainer.kt` wires it).

The map, not a single list, is the contract, because the thread's service is not
fixed: `switchModel` (`ThreadViewModel`) closes the picker and calls
`reloadConversation()`, which refetches the *conversation* only. A materialized
`ladder` copied at load time would therefore keep describing the service the
user just left — offering levels the new model does not declare (a 400 on tap)
and judging staleness against the wrong ladder. Keying the fetched snapshot by
service name makes the switch correct with no extra request: the one `list()`
call already contains every service's ladder, and `mainService` changing is
enough to re-derive.

A failed ladder fetch must **keep** the previous map rather than clear it: an
empty map hides the chip, and the chip is the only entry point to the sheet, so
a clear-on-failure would make the control unrecoverable without leaving the
screen. No error banner for the read path (R7 is about writes); a later
`list()` (sheet open, re-open, picker) replaces it.

Deliberately **not** a permanent `GET /api/services/stream` subscription for the
thread's lifetime: a thread screen stays open indefinitely and one rarely-read
field does not justify a held connection — the app already scopes that stream to
the model picker's visible lifetime for the same reason
(`ThreadViewModel.openModelPicker`). This is a documented departure from F00-R12
(Should).

R5 is satisfied without a permanent subscription by two cheap refreshes:

1. When the level sheet opens, refetch the snapshot (mirrors the sheet's own
   "re-fetch on open" rule for the MCP registry, `ChatSettingsState`'s doc).
2. `ThreadViewModel` already re-fetches services for the model picker; when that
   stream is live, its `ServiceSummary` list updates `laddersByService` too —
   which also means the switch itself lands, since the picker's list is what the
   user picked the new service out of.

Plus the general path: any reconnect of the picker stream, thread reload, or
re-open lands a fresh snapshot. The safety net is that a stale ladder is never
*dangerous* — the server re-checks per run (R6) — it is only briefly
inaccurate in the UI.

### 3.4 UI: one control, in the thread header

A chip in the header's second row, beside the model name, shown only when
`ladder.isNotEmpty() || storedLevel != null`:

- label = the current level id, or `default`;
- accent styling when a level is set, muted when not, **warning colour when
  stale** (stored level not in the current ladder);
- tap → `ReasoningLevelSheet`: "Model default" + each declared level; the stored
  but unoffered level appears last, labelled "not offered by this model",
  selectable only to be replaced;
- hidden for `ModelRef.OpenRouter` unconditionally (R8);
- disabled while a run is active (same rule as `canSwitchModel`/`canToggleTools`
  — the turn in flight already read the previous value), with the existing
  "unavailable while a run is active" wording pattern.

Why the header and not the composer (web) or the settings sheet (phone):

- The composer has three elements on a 411 dp-wide screen
  (`ComposerRow`); a fourth chip row competes with the text field at exactly the
  viewport that can least afford it. This is a layout deviation from the web
  client, allowed by R-B (parity is about behaviour, not pixel placement), and
  it goes in F15's *Deviations from the mockups* section.
- The settings sheet is the wrong verb: it holds durable per-thread settings
  (prompt, tools, text size). Which ladder rung the *next answer* uses is
  turn-adjacent state, and the header already carries its peer — the model name,
  kept visible for the whole turn per F04-R3. Putting the level there keeps the
  two facts that jointly determine an answer side by side.
- Burying it behind settings → scroll → row → sheet makes it a three-tap control
  for a knob the desktop exposes in one click.

Layout note: `ThreadHeader` is one fixed 64 dp `Row` — back button, then a
`Column(weight(1f))` holding title over the monospace model label, then the
settings `action()` slot. The chip takes a fixed width at the end of the second
row (label capped like the web trigger's `max-w-[10ch]`) and the model label
keeps `weight(1f)`, so it ellipsizes instead of the header growing; the chip
label is a level id (`off`, `xhigh`) or `default`, i.e. ≤ ~64 dp.

The settings sheet gets nothing new in v1: the header chip is reachable from
where the model row's information already lives, and duplicating the control
would create two sources of truth for one value.

### 3.5 State transitions

| Trigger | Behaviour |
|---|---|
| Level tapped | Optimistic: update `conversation.reasoningLevel` immediately, then PUT. On failure, revert **only if the stored value is still the one we wrote** (a later tap owns the value by then), and surface `actionError`. |
| Rapid successive taps | Last write wins by ordering, same as `toolsWriteLock`: writes go through one `Mutex`, and only the newest write's failure reverts. A rolled-back older write must never overwrite the newer choice. |
| Model switched to a service with no ladder | Client sends `main_service` **only**, exactly as today (`updateMainService`). The stored level is left alone server-side, and `ladder` re-derives from `laddersByService[newService]` → `[]`, so the chip goes stale-coloured rather than vanishing (R3: a stored level always has a control, so the state is never invisible). The next turn reports the drop through R6. |
| Model switched **to** a service that does declare a ladder | Same single PUT; the chip appears with `default` selected even though no ladder existed for the previous service — again by re-derivation, not a new fetch. |
| Model switched to a service that doesn't offer the current level | Same single `main_service` PUT. Chip re-renders as **stale**, so the state is visible rather than hidden, and R6's note explains it on the turn. Matching the web client: the stored choice survives, so switching back restores it. Do **not** auto-clear, and do not send a combined `{main_service, reasoning_level: null}` — that would silently destroy a choice the user still owns. |
| Ladder gains a level (dashboard edit) | Appears on the next snapshot refetch (sheet open, picker stream tick, or re-open). |
| Ladder loses the stored level | Chip goes stale-colored; clearable; never sent. |
| Thread on OpenRouter | No chip, whatever is stored. |
| App backgrounded / process killed | Nothing client-side to lose — the value is server state; re-load reads it back from `GET /api/chat/conversations/<id>`. |
| Submit immediately after choosing | Send is disabled while the PUT is in flight? **No** — instead the run reads the server's committed value, so a send issued before the PUT lands uses the *old* level. To keep the UI honest, the chip's pending state is rendered (spinner-free: dimmed) while the write is in flight and the sheet stays open until the write succeeds. Choosing then instantly sending is therefore allowed and well-defined: the PUT completes before the sheet dismisses, so the next run uses the new level. |

The last row is the reason the sheet closes on **write success**, not on tap:
it removes the "did my first message use the new level?" ambiguity entirely
rather than trying to display it.

### 3.6 R6: the dropped-level note

`RunEvent.RunStarted` gains `reasoningLevel: String?` and
`reasoningLevelNote: String?` (both optional; the parser's `ignoreUnknownKeys`
keeps old servers working), and **the note reaches `Loaded.reasoningNotice`** —
written when the frame arrives, cleared by the next send. `ThreadScreen` renders
it as a one-line notice directly above the composer row — a **new** slot, matching
where the web client renders `runNotice` (`ChatArea.jsx`), test tag
`thread_reasoning_notice`. *Implemented location, corrected at the device pass:*
the first version put it on `StreamingTurn`, and a capture showed a completed
turn with no notice — the turn is discarded at its terminal and refetched, so the
notice was readable only while the answer happened to stream. Hoisting it to the
screen state also matches the web client, whose `runNotice` is hook state and
outlives the run. It is *not* the `ReattachedBanner` slot: that one is a
`LazyColumn` item above the streaming bubble (`ThreadScreen.kt`, `item(key =
"reattached_banner")`), which scrolls away with the turn, whereas this explains
the next turn and must stay put beside the control that named the level.

The note is **best effort by construction**: it exists only on the fresh-send
path, and the accumulator is rebuilt per reattach attempt (F09's no-duplication
rule), so a reconnect loses it. The always-available equivalent is the stale
chip, derived client-side from ladder vs stored level — which is why R3's stale
state is a requirement rather than polish: it is the durable half of R6.

### 3.7 Proving the untouched 90 % (R8)

- No ladder + no stored level → chip not composed at all; the send request body
  is byte-identical to today's (`SendMessageRequestDto` is unchanged — the level
  is never in the send body, it is conversation state read server-side).
- The app never sends a reasoning field anywhere. All request mapping stays
  server-side; the client's job ends at `conversations.reasoning_level`.
- `ReasoningLevelDto` is additive on `ServiceDto`, so every existing screen
  decodes exactly as before.

## 4. Implementation sequence

| Step / reqs | Files and symbols | Behaviour and responsibility | Depends on | Acceptance |
|---|---|---|---|---|
| P0 · spec | `android/docs/F15-reasoning-level.md` (new), `android/docs/Plan_TOC.md` §6 index row + §5 Chat table note on `PUT /api/chat/conversations/<id>` accepting `reasoning_level` | R1–R8 as requirements with acceptance criteria; deviation from the mockups recorded | — | Feature file reviewable; index shows `F15 [WIP]` |
| P1 · wire + domain | `data/dto/ServiceDto.kt` (+`reasoningLevels: JsonElement?`, **not** a typed `List<ReasoningLevelDto>` — see §5 T1 for why), `data/model/ServiceSummary.kt` (`reasoningLevels: List<String>`), `data/mapper/NewChatMapper.kt: ServiceDto.toDomain` (tolerant id extraction), `core/net/ServiceStreamEvent.kt: Delta` (`reasoningLevels: List<String>?`) + `deltaFrame`, `data/ServicesStreamRepository.kt: mergeServiceEvent` | Ladder parsed from snapshot and from a `metadata-changed` delta; a delta carrying `null` leaves the ladder untouched (favourite toggles must not clear it), `[]` clears it; malformed ladder entries dropped one by one, valid ones kept, **and a malformed ladder must never degrade a whole snapshot frame to `Unknown`** | P0 | T1, T2, T6 |
| P2 · conversation state + write | `data/dto/ChatThreadDto.kt: ConversationDetailDto.reasoningLevel`, `data/mapper/ChatThreadMapper.kt`, `data/model/ChatMessage.kt: ConversationDetail.reasoningLevel`, `data/ConversationsRepository.kt: setReasoningLevel` (raw `buildJsonObject` body) | Read the stored level; write id-or-explicit-null | P0 | T3, T4 |
| P3 · stream note | `core/net/RunEvent.kt: RunStarted` + `typedFrame`, `feature/thread/ThreadViewModel.kt: TurnAccumulator.apply/snapshot`, `feature/thread/ThreadState.kt: StreamingTurn.reasoningNote`, `feature/thread/ThreadScreen.kt` notice row | R6 | P0 | T5, T9 |
| P4 · control | new `feature/thread/ReasoningLevelSheet.kt` (+ a pure `reasoningLevelOptions(...)`/`showsReasoningControl(...)` pair beside it, see §5 T7); `feature/thread/ThreadScreen.kt: ThreadHeader` (chip in the model row, widened signature); `feature/thread/ThreadViewModel.kt`: new `servicesRepository` dep, `Loaded.laddersByService` + derived `ladder`, `reasoningPicker: ReasoningPickerState?`, `openReasoningPicker`/`closeReasoningPicker`/`selectReasoningLevel`, `updateLadders(...)` (the one place a fetched or streamed ladder is written into the map), `levelWriteLock: Mutex`, `latestLevelWrite`; `feature/thread/ThreadState.kt: ReasoningPickerState`; `core/AppContainer.kt` wiring; the eight `Thread*Test` files that build `ThreadViewModel` gain the new dependency; `feature/models/…` untouched | R1–R5, R7: chip visibility/staleness/disabled rules, sheet option list, ordered write with guarded revert, snapshot refresh on open, sheet closes on write success | P1, P2 | T7, T8, T10, T11, device pass |
| P5 · optional (Should) | `data/dto/ServiceDto.kt`→`ServiceConfigDto.reasoningLevels` + `feature/models/ModelDetailScreen.kt` | Read-only "Reasoning: off,low,…" row on the model detail screen, from the raw config string; helps an operator see whether a model is worth switching to | P4 | T12 |
| P6 · close out | `Plan_TOC.md` index → `[DONE]`, F15 verification notes | Record what was device-verified vs fixture-only | all | — |

P1 and P2 are independent of each other and of any UI; each is a shippable,
testable slice that changes no visible behaviour. P4 is the only phase with a UI
change. No phase depends on a later phase's helper.

Branch per `AGENTS.md`: new branch from a **fresh `main`** — available now,
`origin/main` at `51a39e9`, which carries PR #128.

## 5. Verification

Checks run so far: the source survey, the `services.json` read, a live
`GET /api/services` probe, and `docker ps` (all in §2). Everything below is
**proposed**.

| # | Requirement | Test (location) | Setup → action → expect |
|---|---|---|---|
| T1 | R1 | `data/mapper/NewChatMapperTest.kt`, `core/net/ServiceStreamEventParserTest.kt` | Snapshot JSON with `reasoning_levels: [{id:"off",…},{id:"xhigh",…}]` → `ServiceSummary.reasoningLevels == ["off","xhigh"]`, order kept; absent key and `[]` → `emptyList()`; `[{id:null}]`, `["junk"]`, `{}` → those entries dropped, valid ones kept. **Modelled as `JsonElement?` deliberately**: as a typed `List<ReasoningLevelDto>` both malformed cases throw at *decode*, one layer above the mapper, and `ServiceStreamEvent.snapshotFrame`'s `runCatching` would then swallow the **whole** payload into `Unknown` — a frozen model picker, not a missing chip (`ServiceStreamJson` has no `coerceInputValues`, so even `{"id": null}` throws there). Hence the parser-level criterion: a snapshot whose ladder is garbage still decodes, and every *other* field of every row survives |
| T2 | R1, R5 | `core/net/ServiceStreamEventParserTest.kt`, `data/ServicesStreamRepositoryTest.kt` | `metadata-changed` frame with `metadata.reasoning_levels` → `Delta` carries them, `mergeServiceEvent` replaces only that service's ladder and leaves `status`/`favorite`/other rows alone; frame with `metadata.favorite` only → ladder unchanged (the anti-clear test); frame with neither → unchanged |
| T3 | R4, R7 | new `ConversationsRepositoryTest` case | `setReasoningLevel("c1","low")` → body contains `"reasoning_level":"low"`; `setReasoningLevel("c1",null)` → **body string contains `"reasoning_level":null`** (exact-body assertion; guards `explicitNulls=false`) |
| T4 | R4 | `data/mapper/ChatThreadMapperTest.kt` | Detail DTO with `reasoning_level: "medium"` → domain carries it; absent → `null` (not `""`) |
| T5 | R6 | `core/net/RunEventParserTest.kt` / `RunEventParserAdversarialTest.kt` | `{"type":"run_started","run_id":"r1","reasoning_level":null,"reasoning_level_note":"…"}` → `RunStarted("r1", null, note)`; plain `run_started` → note `null`; frame with an unknown extra key still parses |
| T6 | R8 | `data/model/ServiceSummaryTest.kt` | A service with no ladder and no new fields round-trips to the same `ServiceSummary` equality as before the change (additive field defaults keep every existing assertion green) |
| T7 | R1, R2, R3 | new `feature/thread/ReasoningLevelSheetTest.kt` — **plain JUnit over extracted pure helpers**, the pattern `feature/modelpicker/ModelPickerSheetTest.kt` actually uses (it tests `runningChatCapable`/`NOTHING_RUNNING_TEXT` and its own docstring says it exists to be testable *without* Compose; there is no Robolectric dependency and no compose rule in `app/src/test`, `ui-test-junit4` is `androidTestImplementation` only) | `reasoningLevelOptions([off,low,xhigh], null)` → exactly default, off, low, xhigh, with default selected; `reasoningLevelOptions([off,low], "high")` → a stale row last, labelled "not offered by this model", selectable only to be replaced; `showsReasoningControl([], null)` → false; `([], "low")` → true; `([off], null)` on OpenRouter → false. Rendering itself is device-covered by D1/D3 |
| T8 | R1, R5, R3 | new `feature/thread/ThreadReasoningLevelTest.kt` (same harness as `ThreadViewModelTest.kt`, fake repos) | Load a thread whose service has a ladder → `Loaded.ladder` non-empty; service missing from the payload → `ladder == []`; OpenRouter thread → `ladder == []` even when the payload has levels; a failed `ServicesRepository.list()` → the previous map **kept**, not cleared; `updateLadders` from a delta → `ladder` changes with no reload; **and the switch case: thread on service A (ladder `off,low`), `switchModel` to service B (no ladder) → `ladder == []` with no second `GET /api/services`, and back to A → `off,low` again without a fetch** |
| T9 | R6 | `feature/thread/ThreadViewModelTest.kt` extension | Stream scripted with `run_started` + note → `Loaded.reasoningNotice == note`; note absent → null; the note survives the turn's terminal (it is screen state, cleared by the next send, not by the refetch) |
| T10 | R4, R7 | `ThreadReasoningLevelTest.kt` | Choose `"low"` → PUT issued, state updated optimistically, sheet closes on success; repository fails → state back to the previous value **and** `actionError` non-null; a failing *superseded* write (second write already queued) does **not** revert the newest value |
| T11 | R3, R6 interaction | `ThreadReasoningLevelTest.kt` | `selectReasoningLevel` refused while `runActive` (state unchanged, no request) — mirrors `toggleTool`'s guard |
| T12 | P5 | `feature/models/ModelDetailViewModelTest.kt` or mapper test | Config with a raw `reasoning_levels` string renders the row; a config without it renders no row |
| D1 | R4, R5, R2, R6 | **device** (emulator, `android/scripts/dev.sh`) | On the rig's one ladder-bearing service (`vllm-qwen3-8-flash-next-mixed-nvfp4-fp8`, ladder `off,low,medium,xhigh`): pick `off`, send, screenshot the chip; confirm the web UI on the same thread shows the same level; edit the ladder on the dashboard and confirm the phone's sheet changes on reopen; ask for a level the ladder lost and read the notice. Screenshot each into `$SHOT_DIR`. |
| D2 | R8 | **device + curl** | Thread on a no-ladder service: chip absent; then `tail` the dashboard log (or the model's `/v1/chat/completions` request via `docker logs`) for one turn and confirm no `reasoning_effort` / `chat_template_kwargs` key appears. Absence is the assertion. |
| D3 | R3 | **device** | Thread carrying a level whose ladder was removed → warning-coloured chip, "not offered" label, tap → clear → chip back to `default`. Needs no container start/stop, so it is closable by an agent under the `android/CLAUDE.md` rule. |

**Not verifiable by this project's agents**: any criterion requiring a container
start/stop (the standing prohibition). Nothing in F15 as scoped requires one —
the ladder is `services.json`-and-dashboard-driven, not container-driven, which
is the point of the feature's design.

## 6. Rollout, risks, open items

- **Gate: closed.** PR #128 is merged (`51a39e9`) and the host dashboard serves
  `reasoning_levels` today, with one ladder-bearing service whose container is
  already up — so D1–D3 need no container start or stop. Two environment traps
  remain, and neither is a design question: branch off a **fetched**
  `origin/main` (a stale local ref predates the ladder entirely), and re-run the
  §2 probe before the device pass, since an empty result there is an environment
  problem rather than a failing test.
- **New-chat preselect is deferred.** Web offers the level in the empty-state
  composer and carries it onto `POST /api/chat/conversations`. On the phone the
  new-chat sheet is a modal with rows for model/prompt/tools; adding a fourth
  row means the create path grows a *second* follow-up PUT beside the tools PUT,
  which already has its own failure mode (`ToolsFailure`, "open anyway"). The
  deferral costs one extra trip (open the thread, then set the level) and loses
  no data. If it is later wanted, the clean shape is to extend
  `CreateConversationRequestDto` with `reasoningLevel: String?` (omitted when
  null, which the server reads as "no level" — exactly right) rather than a
  post-create PUT. Recorded as F15's one *Later* item.
- **Placement deviates from the mockups and from web** (header chip, not the
  composer). Must be written into F15's *Deviations from the mockups* in the same
  commit as P4, per `android/CLAUDE.md` ("never leave the plan describing
  something the app doesn't do").
- **`metadata-changed` carries the ladder on *every* service config write**, not
  only on a ladder edit: `update_service` emits it unconditionally after the
  write with the post-update ladder, so an alias or port edit refreshes it too
  (always accurate — a free extra refresh, not a hazard). The *other* emitter is
  the favourite route, which reuses the same action and sends `favorite` only —
  hence the "absent means unchanged" rule (§3.1) and T2's anti-clear test.
  Getting that wrong produces a ladder that empties whenever someone stars a
  model on the dashboard.
- **`explicitNulls = false`** is the sharpest client-side trap in the plan
  (T3). A "Model default" option that silently no-ops would look like a working
  feature forever, since the server answers 200.
- **No numeric budgets, no invented levels.** If a user asks for "high" on a
  model that declares only `low,medium,xhigh`, the answer is that the model does
  not offer it — the client never adds options
  (`docs/reasoning-level-sweep-qwen3.8-27b.md` documents a template that answers
  an undeclared token with HTTP 500).
- **Reattach loses the note** by construction (§3.6); the stale chip covers it.
  Accept, and say so in F15's verification notes rather than claiming R6 is
  device-proven on the reattach path.
- **Rollback** is a client revert; nothing persisted changes shape, and a
  downgrade of the app leaves the stored `reasoning_level` readable by the web
  client (which keeps honouring it) — an old app version simply never edits it.

## 7. Readiness

**Ready for implementation.** The gate this plan previously carried is closed
(§6), and what remains is implementation work rather than open design
questions: P0's header-chip deviation text needs accepting, since placement is
the one decision a reviewer may want argued differently. Everything else follows
from the verified wire contracts.
