# New chat must not stay enabled after its selected local model stops (issue 266)

**Issue:** #266 `[Android][P2] New chat remains enabled after its selected local model stops`
**Reviewed baseline:** `415c0ccb22964181546d46ffed0926e7963c1bc9`; `git log 415c0ccb..HEAD -- feature/newchat/` is empty, so the analysis below holds unchanged at `c404ca67` (current `main`).
**Owner surface:** Android client only — no dashboard change. All claims are `Source inspected` at that revision; no builds or device runs were performed for this plan (§6 lists what must run).

---

## 1. Problem statement

The new-chat sheet can create a thread for a local model that stopped (or was removed, or stopped being chat-capable) while the sheet was open. The live service stream correctly shows the service as `exited`, yet the retained selection, the `Start` button, and `create()` all still behave as if it were running — so the thread the app hands the user fails on its very first send. F03-R1's fourth criterion already forbids exactly this class of dead thread for the *remembered* model at load time ("requires an explicit choice rather than creating a dead thread"); a stop that lands **after** the sheet loaded walks straight through the gap, because only the load-time path was guarded.

The acceptance bar comes from the issue itself, restated as the observable contract this plan must produce:

- A selected service going running → `exited` / `not-created` / removed disables Start and offers model reselection, with the prompt, tool, shared-URL and summarize intent untouched.
- The same service starting again becomes selectable, and a fresh selection re-enables Start.
- `create()` refuses an invalid local selection even when invoked directly, not just via the disabled button.
- Remote (OpenRouter) selections are never invalidated by local service deltas.

## 2. Root cause

Three facts compose into the bug:

**(a) The stream collector updates only the raw row list.**
`NewChatViewModel.kt:186-190` — the F07-R1 live collector is

```kotlin
servicesStreamRepository.stream().collect { live ->
    updateLoaded { it.copy(services = live) }
}
```

Every other row of `Loaded` keeps its value from the one-shot `load()`: `localServices` is built once from the initial `GET /api/services` (`NewChatViewModel.kt:134-136`), `selectedModel` from the remembered-model resolution (`NewChatViewModel.kt:156-170`), and `rememberedModelUnavailable` with it (`NewChatViewModel.kt:163`). Nothing reconciles them against `live`.

**(b) The selection captures its status at pick time.**
`ModelOption.LocalService` carries a `status` string (`ModelOption.kt:6-9`) copied from whichever row was current when the state was built — the load snapshot, or the picker row at tap time (`ModelPickerSheet.kt:102`; since F07-RO the picker only ever renders running rows, `ModelPickerSheet.kt:193-194`, so the captured value is always `"running"`). It is a photograph, and the review probe in the issue shows it frozen at `status=running` while the live row already reads `exited`.

**(c) Eligibility reads the photograph, never the live list.**
`NewChatUiState.Loaded.canStart` (`NewChatViewModel.kt:73-74`) is `selectedModel != null` plus the creating / tools-failure / summarize gates — nothing about status. `create()` (`NewChatViewModel.kt:210-213`) likewise checks only selection non-null and `!creating`. The button already binds to `canStart` (`NewChatScreen.kt:210-215`), so it inherits the hole, and the reselection hint (`NewChatScreen.kt:151-158`) fires only off `rememberedModelUnavailable`, which no post-load event ever sets.

`ServicesStreamRepository` itself is fine and unchanged: snapshot replaces wholesale, delta patches the one named row in place (`ServicesStreamRepository.kt:109-124`), a removal arrives as absence from the next snapshot (a `delta` merges into existing rows only). The defect is purely that `NewChatViewModel` ignores what that repository hands it.

## 3. Design

**One sentence:** make the live row set the single source of truth for what may start a chat — reconcile the selection against every stream emission through one pure function, derive `canStart` from the same predicate, and guard `create()` with it too.

### 3.1 One pure reconciler, JVM-testable

A top-level `internal` function in `NewChatViewModel.kt` (same pattern as `mergeServiceEvent` in `ServicesStreamRepository.kt` and `runningChatCapable` in `ModelPickerSheet.kt` — the repo already pulls pure decision logic out of composables/collectors so it is testable without Compose):

```kotlin
internal fun reconcileLiveServices(
    current: NewChatUiState.Loaded,
    live: List<ServiceSummary>,
): NewChatUiState.Loaded
```

For every emission:

- `services = live` always (today's behaviour).
- A `ModelOption.LocalService` selection is **live-valid** iff the live set carries its row by name, the row `isChatCapable` (`ServiceSummary.kt:40`), and the row `isRunning` (`ServiceSummary.kt:42`).
  - Valid → keep the selection and refresh the captured status (`option.copy(status = row.status)`) so `ModelOption.LocalService.status` can never be stale — the exact wrongness the issue's probe printed.
  - Invalid (stopped, `not-created`, no longer chat-capable, or absent) → invalidate: `selectedModel = null`, `modelUnavailable = true`. Every other field — `selectedPromptId`, `selectedMcpServerIds`, `summarizeUrl`, `requiredMcpServerIds`, `creating`, `createError`, `toolsFailure` — is copied untouched.
- A `ModelOption.Remote` selection is never touched (OpenRouter models have no local stopped state to lose; the curated list is a picker, not an allowlist — F07-R3).

The collector becomes:

```kotlin
servicesStreamRepository.stream().collect { live ->
    updateLoaded { reconcileLiveServices(it, live) }
}
```

`localServices` deliberately stays the untouched load-time snapshot — its KDoc (`NewChatViewModel.kt:34-41`) already scopes it to the remembered-model resolution, it has no post-load consumer, and the reconciler works purely off `services`.

### 3.2 One name for one state: `rememberedModelUnavailable` → `modelUnavailable`

Both paths — "remembered model wasn't running at load" (F03-R1 fourth criterion) and "the selected model died while the sheet was open" (#266) — demand the same answer: Start off, the Model row back to *Choose a model*, an amber line asking an explicit choice. Two fields rendering two hints would let the messages drift while meaning the same thing, so the flag widens and renames (call sites: `NewChatViewModel.kt:46-47` KDoc, `NewChatViewModel.kt:163`/`171`, `NewChatScreen.kt:151`, six assertions in `NewChatViewModelTest.kt`). The hint keeps its testTag `new_chat_model_unavailable` and generalizes its wording to cover both origins — proposed: `"That model isn't running any more — pick one to continue."` `selectModel` already clears the flag on an explicit pick (`NewChatViewModel.kt:199-201`), which is what makes reselection the single way back.

### 3.3 Start eligibility derived from the live list

`canStart` replaces `selectedModel != null` with a shared predicate:

```kotlin
val canStart: Boolean
    get() = selectedModel.isLiveSelectable(services) && !creating &&
        toolsFailure == null && !blockedForSummarize
```

`isLiveSelectable` is a small pure extension (`ModelOption?` × `List<ServiceSummary>`) implementing exactly §3.1's validity rule — `null` false, `Remote` true, `LocalService` true only for a live chat-capable running row. It sits next to the reconciler, and both the state property and `create()` call it, so the button and the method cannot disagree. (Reconcile-driven invalidation makes `selectedModel != null` already imply live-valid; the derivation is deliberate belt-and-suspenders — it is what the issue's plan items 2 and 3 ask for, and it means a future code path that forgets to reconcile still cannot start a dead thread. The repo applies the same double-filter posture to the picker itself, `ModelPickerSheet.kt:48-53`.)

### 3.4 `create()` guards with the same rule

At the top of `create()`, after the existing `creating` check:

```kotlin
if (!model.isLiveSelectable(current.services)) {
    _state.value = current.copy(selectedModel = null, modelUnavailable = true)
    return
}
```

A direct call with a stale selection refuses (no POST), and leaves the sheet in the same "pick a model" state a live delta would have produced. The check uses the `Loaded` snapshot read at call time, which the collector keeps current — the eligibility instant is the tap instant. A stop landing between the tap and the server seeing the request is server-side truth the client cannot outrun; the create either succeeds (thread works) or the server rejects it into today's `createError` path (F03-R1 fifth criterion) — unchanged.

### 3.5 Comments

Per the repo rule: none added inside bodies. The two places a line is warranted are contract boundaries — the `modelUnavailable` KDoc (the state contract: set by load-time unavailability *and* live invalidation, cleared only by an explicit pick) and a one-line note on the `isLiveSelectable` call in `create()` naming the invariant it defends. Behaviour that must hold lives in tests named for the behaviour, §6.

### 3.6 Ground rules

- **R-A** — no new endpoint; this consumes the existing `/api/services/stream` the sheet already holds open.
- **R-B** — the web client has no equivalent gate because it has no pre-create sheet: `/v2` picks `runningServices[0]` and a stale send just fails server-side (`ChatPage.jsx:29,148-155`). The phone's stricter gate is the sheet's own existing F03-R1 promise, extended in time, not invented divergence.
- **R-C** — screen 03 is unchanged; the hint reuses the row already drawn for F03-R1's fourth criterion.

## 4. Edge cases

| Case | Behaviour after the fix | Why |
|---|---|---|
| Delta flips the selected service to `exited` / `not-created` | Selection cleared, hint shown, Start disabled | §3.1; the issue's probe scenario |
| Service renamed/deleted while sheet open | Next snapshot lacks the row → same invalidation | Delta can only patch existing rows (`ServicesStreamRepository.kt:112-122`); removal travels by snapshot absence |
| Snapshot reclassifies the row (e.g. `kind` becomes `embedding`) | Invalidated via `isChatCapable` | capability, not just status, decides validity — the picker filter and this predicate must stay the same filter |
| Service starts again later | Row reappears in the picker (it renders live `services`), selecting it re-enables Start | F07-RO picker filters on the live list; `selectModel` clears the flag — issue acceptance criterion 2 |
| OpenRouter selected, any local delta | Untouched | §3.1; issue acceptance criterion 4 |
| Favourite / reasoning-ladder delta on the selected service | Selection stays, flag untouched | Delta carries no status → still running |
| Delta on an unrelated service | Selection stays | reconcile is selection-identity based |
| Summarize mode, model dies | URL, `requiredMcpServerIds` and tool picks survive; Start stays gated by the existing summarize rule until a model is re-picked | reconcile copies them; acceptance criterion 5 |
| Preselected service (F10-R6 "New chat from a model") stops before first snapshot | First stream emission reconciles it away like any other | the stream's opening frame is always a snapshot |
| Stop lands while `toolsFailure` banner is up | Services update, selection may invalidate; banner remains the way out | orthogonal — banner already replaces Start |
| Stop lands while `creating` | State reconciles behind the in-flight POST; the conversation was created with the tap-time-valid service, `onCreated` still fires | a created thread is server-side fact, out of this issue's scope |
| Stream reconnect | Repository keeps the last list and re-emits a fresh snapshot on reconnect; reconcile is idempotent, and a genuinely changed fleet invalidates truthfully | `ServicesStreamRepository.kt:33-56` |
| Remembered-model-at-load path | Unchanged — resolver still runs on the load snapshot | existing six tests in `NewChatViewModelTest.kt` keep this honest |

## 5. Files to change

| File | Change |
|---|---|
| `android/src/app/src/main/java/com/hpz/llmdockchat/feature/newchat/NewChatViewModel.kt` | rename flag (§3.2); `canStart` via `isLiveSelectable` (§3.3); collector calls `reconcileLiveServices` (§3.1); `create()` guard (§3.4); two new pure helpers, file-`internal` |
| `android/src/app/src/main/java/com/hpz/llmdockchat/feature/newchat/NewChatScreen.kt` | hint condition renamed, wording generalized (line 151-158); nothing else — the button already binds `canStart` |
| `android/src/app/src/test/java/com/hpz/llmdockchat/feature/newchat/NewChatViewModelTest.kt` | rename the six flag assertions; add the tests of §6 |
| `android/docs/F03-new-conversation.md` | add the stop-while-open acceptance criterion under F03-R1 and a *Deviations* note (issue 266) — plan and app must not disagree |
| `android/docs/Plan_TOC.md` | F03 index row gains an "(issue 266)" note, same shape as F14's "(issue 255)" |

No changes to `ModelOption`, `ServiceSummary`, `ModelPickerSheet`, `ServicesStreamRepository`, the wire types, or the navigation graph. The diff is one screen's state layer plus one hint line.

## 6. Verification

JVM suite: `cd android/src && JAVA_HOME=/opt/android-studio/jbr ./gradlew testDebugUnitTest` — read it, don't count it (`ThreadToolsTest` is a known intermittent per `android/CLAUDE.md`). The existing `FakeSseTransport` (payloads list, `Fakes.kt:129`) is already wired into `NewChatViewModelTest`; the new stream tests are existing-test-shaped, just with scripted frames.

| # | Test | Given / when / then |
|---|---|---|
| T1 | `a delta stopping the selected service disables Start and asks for a new model` | fixture load, `selectModel(llamacpp-gemma…q8)`, transport snapshot-running + delta-`exited` → `selectedModel == null`, `modelUnavailable`, `!canStart` |
| T2 | `…and preserves the prompt and tool selections` | T1 plus `selectPrompt`, `toggleMcpServer` beforehand → prompt id and MCP set unchanged after invalidation |
| T3 | `a service absent from a later snapshot invalidates the selection` | second snapshot without the row → same as T1 (covers rename/delete) |
| T4 | `a snapshot making the selected service non-chat invalidates the selection` | second snapshot flips `kind` to `embedding` → invalid despite `status:"running"` |
| T5 | `a remote selection survives local status deltas` | `selectModel(Remote)` + stop delta → selection unchanged, `canStart` true, flag false |
| T6 | `the same service starting again is selectable and Start re-enables` | delta-`exited` then delta-`running`; `runningChatCapable(live services)` contains the row again; `selectModel` → `canStart` true |
| T7 | `create sends nothing when the selection is stale` | T1's state, then `create {}` → `server.requestCount` unchanged (four load GETs), no `creating` transition |
| T8 | `isLiveSelectable refuses a captured running status against an exited live row` | pure: `LocalService(name, "running")` vs live row `exited` → false; same vs live row `running` → true; `Remote` vs empty live → true; `null` → false — this is the probe's exact shape as a permanent test |
| T9 | pure `reconcileLiveServices` copies the live status onto a valid selection and leaves `summarizeUrl` / `requiredMcpServerIds` / `toolsFailure` untouched | constructed `Loaded` rows, no network |
| T10 | existing suite green after the rename | `NewChatViewModelTest` remembered-model tests unchanged in meaning |

Device (the two criteria a JVM test cannot prove): with the sheet open on a running model, stop that service from the dashboard (owner's fixture choice — do not disturb containers beyond the one under test), `dev.sh shot` → hint visible, Start visibly disabled; start it again, open the picker, reselect, screenshot → Start enabled. Summarize variant: share a URL, stop the preselected model, screenshot → URL intent and tool row intact with the reselection hint.

## 7. Rejected alternatives

- **Auto-switch to another running model.** Silent — the user typed against one model's sheet and gets another thread. F03-R1's stance is "requires an explicit choice"; #266's AC 1 names reselection. Rejected.
- **Keep the selection and disable Start in place (status badge on the row).** Leaves a dead name in the Model row, and `selectModel`-style clearing already owns the hint path; the picker cannot offer the dead row again anyway (F07-RO). More state, same outcome.
- **Recompute `selectedModel` from `preferences` instead of reconciling.** Would discard an explicit mid-session pick on every delta.
- **Filter in the composable only.** `NewChatScreen` could check `services` — but AC 3 requires the ViewModel's `create()` itself to refuse, and a composable-side check leaves exactly the direct-call hole the issue names.
- **Two flags / reason enum with distinct hint texts.** Both invalidation paths ask the identical action of the user; one state and one string cannot drift. The enum is the shape to revisit only if a future hint needs to differ.

## 8. Readiness

Ready for implementation as one branch off fresh `main`, one commit, one PR. No backend change, no migration, no new permission or endpoint; rollback is reverting the PR. Open only for the implementer and reviewer to settle: the exact hint sentence (§3.2).
