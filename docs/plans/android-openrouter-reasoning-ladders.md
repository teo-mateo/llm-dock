# F15.1 — Reasoning levels for OpenRouter models on Android

**Status:** built on `feat/android-openrouter-reasoning-ladders`. Verification in §5.
**Depends on:** #132 (`openrouter-reasoning-levels`, merged), which put ladders on the
OpenRouter shortlist payload, and #130 (F15 delta, merged).

## 1. What is true today

Three walls, each verified on `main`:

| # | Where | Fact |
|---|---|---|
| 1 | `data/dto/OpenRouterModelDto.kt` | declares `id`/`label` only, so `reasoning_levels` is dropped at parse time by `ignoreUnknownKeys` (`ApiJson.kt:10`) |
| 2 | `feature/thread/ThreadState.kt:210` | `ladder` resolves via `conversation.modelRef as? ModelRef.Local`, so an OpenRouter thread is empty whatever the map holds (F15-R8) |
| 3 | `feature/thread/ReasoningLevelSheet.kt:94` | `showsReasoningControl` is `!onOpenRouter && (…)` — chip never composed for a remote model |

Observable behaviour: an OpenRouter conversation carrying `reasoning_level` — settable from
the browser, and now honoured by the server — shows **nothing** on the phone. Not a false
warning: `reasoningStale` computes `true` for a level outside an empty ladder, but the chip
that would render it is never composed, so the flag is unreachable. Silent gap.

The justification comment at `ReasoningLevelSheet.kt:89-92` — "the server resolves no ladder
for an `openrouter:` service and rejects any level written to one" — was true when written.
#132 ended both halves of it, so the comment now argues for a constraint that no longer exists.

## 2. The decision: a parallel map, merged at the state boundary

`laddersByService` is already the seam, and `ModelRef.wireValue` is already the canonical
service string for **both** providers (`Local → name`, `OpenRouter → "openrouter:<id>"`). So
remote ladders go into a second map keyed by `wireValue`, and the two are concatenated only
when published into `ThreadUiState.Loaded`.

Why not one map: `updateLadders()` replaces the map **wholesale** — that is what makes a
service that stopped declaring levels disappear. A single map written by both sources would
mean every `/api/services` refresh wipes the OpenRouter entries, reintroducing the gap as an
intermittent bug that only shows up after a picker stream event. Two maps preserve each
source's own replacement semantics, and the keys cannot collide because local keys are bare
service names and remote keys carry the `openrouter:` prefix.

Why not a field on `ModelRef.OpenRouter`: `ModelRef` is a value type parsed from the
`main_service` string and used for routing and display. Server state on it would mean
constructing a `ModelRef` differently depending on whether a settings read happened, and the
composer would need a second source to consult. Same result, more coupling.

Consequence: `ThreadState.ladder` gets *simpler* — one lookup, no provider branch.

## 3. Changes

1. `OpenRouterModelDto` — `@SerialName("reasoning_levels") val reasoningLevels: JsonElement? = null`.
   Typed `JsonElement?` because that is what `ServiceDto` already uses for the same wire field,
   and it lets the existing `parseReasoningLevels()` handle both: no new parsing code.
2. `ModelOption.Remote` — `reasoningLevels: List<String> = emptyList()`, defaulted so the
   existing construction sites and the picker keep compiling.
3. `NewChatMapper.toDomain()` for the OR DTO — fills it through `parseReasoningLevels`.
4. `ThreadViewModel` — `remoteLadders` field + `updateRemoteLadders(models)`; called from
   `openModelPicker()`'s existing read (free, no extra request) and from `refreshLadders()`
   when the conversation is OpenRouter. `updateLadders()` and `updateRemoteLadders()` both
   publish the merged map through one helper.
5. `ThreadState.ladder` — `laddersByService[conversation.modelRef.wireValue]`.
6. `showsReasoningControl(ladder, stored)` — third parameter deleted, comment rewritten to
   the rule that is now true.
7. Docs — `android/docs/F15-reasoning-level.md` gets an amendment replacing the R8 exclusion.

No constructor change: `openRouterModelsRepository` is already injected
(`ThreadViewModel.kt:66`, wired at `AppNavHost.kt:269`), so none of the 10 test files that
construct `ThreadViewModel` need touching.

## 4. Cost

One extra `GET /api/chat/settings/openrouter-models` per thread open **on OpenRouter
conversations only** — local threads issue exactly the requests they issue today, because the
read is gated on `modelRef` being remote. Opening the model-switch sheet refreshes remote
ladders with no additional request, since that sheet already fetches the list.

No SSE for remote models: the OR list is not on the service stream, so a ladder edit made in
the dashboard reaches an open thread on the next sheet-open or picker-open rather than
instantly. Accepted — it is the same shape as every other non-streamed read in F15, and the
server re-validates the level at run creation regardless, so a stale ladder cannot cause a
wrong request to be sent.

**One transient this opens, and it is inherited rather than new.** Between the first frame and
the settings read landing, a remote conversation holding a level has a stored value against an
empty ladder, which `isReasoningLevelStale` reports as stranded — so the chip can flash amber
for a moment before resolving. F15 already had exactly this window for local services, where
`ladders` likewise starts empty and is filled after the first render, so the behaviour is not
newly introduced and is left alone: distinguishing "unknown" from "declares nothing" would
mean threading a tri-state through `ThreadState`, which is a larger change than a sub-second
flicker of a control that is about to be right anyway. A test caught this while it was still a
test bug — `awaitState { it.reasoningStale }` resolved on the first frame, which is precisely
the ambiguity described here.

## 5. Verification record

`./gradlew compileDebugKotlin` → `BUILD SUCCESSFUL`; `./gradlew testDebugUnitTest` →
`BUILD SUCCESSFUL`, the full Android suite green including the new cases. No ktlint or detekt
is configured in this project, so compile + tests are the whole of the static gate.

| Case | Result |
|---|---|
| DTO → domain ladder, present and absent | `NewChatMapperTest` — `[{id, effort}]` yields `listOf("low","high")`; a key-free entry yields `emptyList()` and compares equal to `ModelOption.Remote("a/b", "A B", emptyList())` |
| Remote thread resolves its ladder | `ThreadReasoningLevelTest` — `low,high,max` on an `openrouter:` thread, control visible |
| Local ladder does not leak onto a remote thread | same test asserts `"off"` from the local row is absent — the key is the whole service string |
| Nothing published → nothing offered | new case; the surviving half of the old R8 |
| Stranded remote level reads amber and stays visible | new case, because the chip is how it gets cleared |
| Predicate is no longer provider-branchable | `ReasoningLevelSheetTest` rewritten: the case that asserted "hidden on OpenRouter" became one asserting a declared ladder *shows* the control |
| Server accepts a level on an OpenRouter conversation | probed against the running dashboard: create with `high` → created; `PUT low` → 200; `PUT ultra` → 400 `invalid_reasoning_level`, the exact code F15-R7's revert branches on; `PUT null` → 200. Probe conversation deleted after |

One bug the tests found rather than the reading: `awaitState { it.reasoningStale }` as a wait
predicate resolves on the first frame, because a stored level reads stale against an empty
ladder too — §4's ambiguity surfacing as a test failure. It reported `expected:<[low, high]>`
`but was:<[]>` before the predicate was changed to wait on the ladder itself.

## 6. Deliberately out of scope

New-chat composer support. F15 put no reasoning control in the new-chat flow (verified: no
`reasoningLevel` reference under `feature/newchat/`), so a level is chosen after the
conversation exists — on either provider. Adding it there is its own feature.

`reasoning_details` round-tripping: server-side, pre-existing, and still unverified.
