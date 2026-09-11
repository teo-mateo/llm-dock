# F15.1 — Reasoning levels for OpenRouter models on Android

**Status:** built on `feat/android-openrouter-reasoning-ladders`. Verification in §5.
**Depends on:** #132 (`openrouter-reasoning-levels`, merged), which put ladders on the
OpenRouter shortlist payload, and #130 (F15 delta, merged).

## 1. What is true today

Three walls, each verified on `main`:

| # | Where | Fact |
|---|---|---|
| 1 | `data/dto/OpenRouterModelDto.kt` | declares `id`/`label` only, so `reasoning_levels` is dropped at parse time by `ignoreUnknownKeys` (`ApiJson.kt:10`) |
| 2 | `feature/thread/ThreadState.kt` — the `ladder` getter | resolved via `conversation.modelRef as? ModelRef.Local`, so an OpenRouter thread was empty whatever the map held (F15-R8) |
| 3 | `feature/thread/ReasoningLevelSheet.kt` — `showsReasoningControl` | was `!onOpenRouter && (…)` — chip never composed for a remote model |

Observable behaviour: an OpenRouter conversation carrying `reasoning_level` — settable from
the browser, and now honoured by the server — shows **nothing** on the phone. Not a false
warning: `reasoningStale` computes `true` for a level outside an empty ladder, but the chip
that would render it is never composed, so the flag is unreachable. Silent gap.

The stated justification for the exclusion — that the server resolves no ladder for an `openrouter:`
service and rejects any level written to one — held when written. #132 ended both halves of it. (The
comment itself was removed from the source in the comment strip recorded below, so this plan is
where that reasoning survives.)

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
(`ThreadViewModel`'s constructor, wired in `AppNavHost.kt`), so none of the 10 test files that
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

**One transient this opens, and it is longer than F15's.** Between the first frame and the settings
read landing, a remote conversation holding a level has a stored value against an empty ladder,
which `isReasoningLevelStale` reports as stranded — so the chip can flash amber for a moment
before resolving. F15 has the same window for local services, but this is **not** the same length:
`refreshLadders()` awaits `GET /api/services` before it issues `GET /api/chat/settings/openrouter-models`,
so a remote ladder arrives after two serial round-trips where a local one arrives after one. The
stale-amber window is therefore roughly doubled for a remote thread. Review caught that the plan
had described it as "the same shape as F15", which understated it. Left as is rather than fixed,
because the fix (fetch both concurrently, or track "unknown" separately from "declares nothing")
buys a sub-second flicker of a control that is about to be correct, at the cost of either an
ungated request or a tri-state threaded through `ThreadState`. A test caught the same ambiguity
while it was still a test bug: `awaitState { it.reasoningStale }` resolves on the first frame.

## 5. Verification record

`./gradlew compileDebugKotlin` → `BUILD SUCCESSFUL`; `./gradlew testDebugUnitTest` →
`BUILD SUCCESSFUL`, the full Android suite green including the new cases. No ktlint or detekt
is configured in this project, so compile + tests are the whole of the static gate.

| Case | Result |
|---|---|
| DTO → domain ladder, present and absent | `NewChatMapperTest` — `[{id, effort}]` yields `listOf("low","high")`; a key-free entry yields `emptyList()` and compares equal to `ModelOption.Remote("a/b", "A B", emptyList())` |
| Remote thread resolves its ladder | `ThreadReasoningLevelTest` — `low,high,max` on an `openrouter:` thread, control visible |
| Local ladder does not leak onto a remote thread | the exact-equality assertion in `an openrouter thread resolves its ladder from the curated list` — the local row declares `off,low`, so an exact match on `low,high,max` proves the lookup used the whole service string. Review confirmed it is load-bearing: a fallback-to-first-map-entry mutant fails three tests, this one among them. A separate `contains("off")` line was dead weight inside that test and was deleted |
| Nothing published → nothing offered | new case; the surviving half of the old R8 |
| Stranded remote level reads amber and stays visible | new case, because the chip is how it gets cleared |
| Remote **write** path | added after the PR was opened: choosing `high` on an `openrouter:` thread sends `{"reasoning_level":"high"}`. F15's own write test uses a local conversation, and the three remote cases above stop at the ladder, so nothing covered the client actually issuing the write — which the PR description had been letting the server-side probe stand in for. It also pins request order (`thread`, `services`, curated list, `PUT`), perturbed by the gated read |
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

## 7. Review round

`dev-verifier` reviewed `1c9fbd6` independently and posted findings on PR #133. Verdict: the
implementation held up — it could not break it — but **two of the tests were not testing what
they claimed**, and it proved that by building mutants in a throwaway copy of the tree:

| Finding | Evidence it was real | Fix | Evidence the fix works |
|---|---|---|---|
| `an openrouter model with no published ladder shows no control` asserted nothing about the feature | `awaitLoaded()` resolves on the conversation frame, *before* the curated read is issued. Mutating the client to invent `low,high` where the server published nothing left the class **14/14 green** | Wait on the curated entry *existing* in `laddersByService` — the read having been applied is the precondition the old wait never established | Re-ran that mutant: now fails exactly this one test, 16 completed / 1 failed |
| The two-map design's invariant had no test | The rejected design (`mergedLadders = ladders` **plus** routing remote writes into `ladders`, which keeps every remote test passing) left 546 tests green | New case: remote ladder resolved → picker's services snapshot wholesale-replaces the local map → assert the `openrouter:` key survives | Re-ran that exact mutant: fails only the new case, 16 / 1 |

Also fixed from review: a duplicated `wireValue` import that compiled silently with no lint to catch it
(this project has neither ktlint nor detekt, and no CI at all), and a redundant `contains("off")`
assertion that review showed was dead weight beside the equality check it duplicated.

Review converted two of its own hedges into measurements in a follow-up, which are worth keeping
because both are load-bearing facts about this feature:

- **The request gate is enforced, not merely intended.** Removing the gate (so every thread pays the
  curated-list read) fails **35 tests** — not because they care about ladders, but because MockWebServer
  serves a fixed response queue and the extra request shifts it for every `Thread*Test`. "A local thread
  issues exactly the requests it issued before" is therefore held by the suite's request-order
  discipline, not just by reading the code.
- **The flake is real and bounded:** the `Dispatchers.Main is used concurrently` teardown race appears on
  mutant runs, not on the baseline. "548 green" is reproducible but not immune to it.

Review's non-blocking point about §4 was accepted and corrected there rather than argued: the remote
amber window is inherited *in kind* but **doubled in duration**, because the local read is awaited
before the curated read is even issued.

A third mutant worth recording, because it is the honest limit of mutation testing: the cruder version
of the single-map mutation (`mergedLadders = ladders` alone) kills 5 tests and would have been an easy
"we're covered" — it was the *sophisticated* mutation that mattered.

## 8. Comment strip

Repo convention is no comments unless requested. Every comment was therefore removed from the nine
Kotlin files this PR touches — 750 comment lines: `ThreadViewModel.kt` -384, `ThreadState.kt` -143,
`ThreadReasoningLevelTest.kt` -92, `ReasoningLevelSheet.kt` -72, and five smaller files.

Done by one agent per file, sequentially (nine concurrent writers in one tree is how edits disappear),
each instructed to remove comments and change nothing else. **Their reports are not the evidence.**
A three-way audit ran against a pre-strip snapshot:

1. **No comments left** — a string-aware scanner, not a grep.
2. **Nothing but comments removed** — every deleted line is a comment line or a blank line it left behind.
3. **String literals byte-identical** — 261 literals compared in order across the nine files (166 in
   `ThreadReasoningLevelTest.kt` alone). This is the check that matters: these files sit next to code
   that parses `//` and `https://` as data, and a stripper that eats a URL turns green tests red in a
   way that looks like a real bug.

All nine clean, then `compileDebugKotlin` + the full unit suite green.

Two caveats the strip creates, recorded rather than smoothed over:

- **The rationale now lives only in these docs.** The comments were where the two-map argument, the
  gating rule and the tri-state decision were written down; the code no longer explains itself. That is
  the trade the convention asks for, but it means these plan docs are load-bearing, not decorative.
- The audit tooling itself had a bug first: it read `` `… the server's order` `` as a char literal and
  desynced, reporting two files as string-damaged when they were intact. Worth stating because a
  validator that cries wolf is how a real regression gets waved through — the check was fixed
  (backtick identifiers) and re-run, not worked around.

Uncommitted work that was in the tree when the strip ran — a remote-write test and two KDoc trims, not
mine — was preserved through it and lands in the same commit.
