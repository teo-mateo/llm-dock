# Consumed ACTION_SEND shares stop replaying after activity recreation (issue 261)

**Issue:** #261 `[Android][P2] Consumed ACTION_SEND shares replay after activity recreation`
**Baseline:** issue reports `main` at `415c0cc`; this plan was written against `main` at `6b9d19c` — `git diff 415c0cc..HEAD` over `MainActivity.kt`, `navigation/AppNavHost.kt`, `feature/share/` and `core/AppContainer.kt` is empty, so every line cited here reads the same at both revisions.
**Owner surfaces:** Android app only (`android/`). No dashboard change, no new endpoint (Plan_TOC rule R-A holds); no web counterpart (R-B: the web client has no intent).

Every file:line below was read in the working tree at the stated revision. No builds or
test runs were performed for this plan — §7 lists what must be run.

---

## 1. Problem statement

F14 shares are **consume-once**: the picker's row tap moves the content into a thread
(`AppNavHost.kt:241`) and Back throws it away (`AppNavHost.kt:261`), and either way the
pending record is deleted so the user never sees a share they already dealt with. The
*record* is gone; the **intent that produced it is not**. `MainActivity` stages whatever
`getIntent()` holds on every `onCreate` (`MainActivity.kt:50`), and Android hands the same
`ACTION_SEND` intent back on every recreation — rotation, `singleTask` re-activation from
Recents, process-death restore. So the app re-reads a delivery it already handled, writes
a brand-new `pending.json`, and the navigation observer that exists to *resume* an
unfinished share (`AppNavHost.kt:81-87`) drives the user back to the picker:

```text
rotate to landscape → UIAutomator: share_target_screen, "Shared text",
                      ANDROID_REVIEW_SECOND_SHARE
```

with no second share delivered. The same replay re-arms F14-R7's Summarize action for a
URL whose summary was already filed, which is the difference between an annoyance and a
duplicate write to the server.

**Acceptance criteria from the issue** (all six are addressed; mapping in §5):

- Assigning or dismissing a text, image or file share, then rotating, keeps the
  destination and does not recreate the pending record.
- Recreation while the picker is still open preserves exactly one pending share.
- A genuinely new `ACTION_SEND` while the app is open still replaces the pending share.
- Background process recreation does not replay a consumed share.
- A handled URL cannot cause another summarize submission through recreation alone.
- Back/cancel leaves no empty duplicate share-picker destination.

**Decision — gate the intake, don't clear the store.** `SharedDraftStore`'s hydration at
construction (`SharedDraftStore.kt:32`) is the mechanism F14-R5 (survives process death)
and F14-R4 (survives the Connect round trip) are built on, and `android-share-summarize.md`
documents the `pending.json` + `AppNavHost` observer pair as *"the app's existing resume
mechanism"*. Clearing or ignoring the durable record on restore would break those
requirements to fix this one. The bug is that the app consults a **handled intent** as a
source of truth at all; the fix belongs in the one seam that reads it.

## 2. Root cause

### 2.1 The replay: `onCreate` re-stages the activity's intent unconditionally

```kotlin
override fun onCreate(savedInstanceState: Bundle?) {          // MainActivity.kt:46
    ...
    stageShareIfAny(intent)                                   // :50 — no gate of any kind
}
```

`stageShareIfAny` (`MainActivity.kt:92`) bails only when the action is not
`ACTION_SEND` (`:93`). It classifies (`:97-105`), reads the stream **again** (`:96`,
`:110`, `:119`), builds a `StagedShare` (`:107-126`) and calls `store.stage(share)`
(`:128`) — which rewrites `cacheDir/shared-drafts/pending.json` and publishes a fresh
non-null `pending` value (`SharedDraftStore.kt:36-39`). Nothing in the chain knows the
difference between *"the share sheet just handed me this"* and *"the OS is redelivering
the launch intent of an activity I already served"*.

There is no `onSaveInstanceState` override in `MainActivity`, and the activity's intent is
never neutralized after handling, so the `ACTION_SEND` intent stays the activity's launch
intent for the lifetime of the task.

### 2.2 The amplifier: the resume observer turns a re-stage into a visible jump

`AppNavHost.kt:78-87` is F14's resume path: it observes `sharedDraftStore.pending` and
navigates to `Destinations.SHARE_PICKER` whenever the value is non-null and the current
route is neither Connect nor the picker. It was written to catch *"hydration found an
unfinished share"*; because §2.1 manufactures a new emission on every recreation, it fires
on consumed shares too. Three properties make it worse than a plain re-navigation:

| Property | Where | Effect |
|---|---|---|
| Keyed on the flow value only | `:81` `LaunchedEffect(pendingShare)` | Any re-stage re-navigates; a re-stage with an *equal* value re-navigates too, because `stage` assigns a new value |
| No `launchSingleTop` | `:86` `navController.navigate(Destinations.SHARE_PICKER)` | A picker entry can be pushed on top of a restored picker entry — issue criterion 6 |
| Route read at composition, not at decision | `:80` `currentRoute`, captured before the NavHost's graph is restored | During a restore `currentRoute` is `null`, so both guards pass and navigation can fire before the graph is ready |

### 2.3 Why the obvious one-line fix is not enough

`if (savedInstanceState == null) stageShareIfAny(intent)` would kill the issue's exact
rotation repro, and it is wrong in both directions:

- **Over-eager**: a share arrives while the process is alive and the activity record was
  destroyed (the developer option "Don't keep activities", or the system trimming the
  back stack). Android recreates with a non-null bundle and *then* delivers the pending
  intent through `onNewIntent` — the gate loses nothing there. But a cold delivery to a
  task whose saved state was discarded arrives with `savedInstanceState == null` **and**
  an already-handled intent — the issue's "Background process recreation" and
  "force-stop then relaunch" shapes. The bundle cannot separate those, so the bundle
  cannot be the only gate.
- **Not the point**: when a restore *should* surface a share, it is the one on disk, not
  the one in the intent. Re-reading the intent is a second copy of the content — for an
  image, a second decode of a `content://` grant that may already be dead — and a second
  `pending.json` write racing the record hydration already owns.

`onNewIntent` (`MainActivity.kt:78-81`) is a **different** path and must stay a
**different** decision: it is called only when someone actually started this activity with
a new intent, so it must always replace the pending share (criterion 3), even for a
byte-identical payload. But it also fires for task re-activation under `singleTask`
(`AndroidManifest.xml:23`) carrying the *previous* share intent, which is the same replay
through a different door. Both callers therefore need the same gate, parameterised on how
the intent arrived — which is exactly the issue's step 1.

### 2.4 What is *not* the cause

`SharedDraftStore` is correct: `clearPending` deletes the file (`:42-45`, `:144-146`),
`reassign` consumes it (`:54-59`), and `readPending` treats a corrupt record as absent
(`:130-134`). The summarize claim is already consume-once (`stageForAutoSend` `:69`,
`takeAutoSend` `:79`). The store is being *written again* by the activity; it is not
resurrecting anything.

## 3. Verified current behaviour

| Path | Entry | State owner | Final consumer |
|---|---|---|---|
| Share arrives (cold) | `MainActivity.kt:50` | `SharedDraftStore.pending` + `pending.json` | `AppNavHost.kt:81` → `ShareTargetScreen` |
| Share arrives (warm) | `MainActivity.kt:81` (after `setIntent` `:80`) | same | same |
| Pick a conversation | `AppNavHost.kt:241` `reassign` | record deleted, text → `DraftStore` | `ThreadViewModel.load()` merges the draft |
| Dismiss (back / X) | `AppNavHost.kt:261` + `ShareTargetScreen.kt:76` `BackHandler` | record deleted | nothing |
| Summarize a URL | `AppNavHost.kt:253` → `ShareTargetViewModel.summarize` → `SummarizeCoordinator.createAndClaim` (`:76-88`) | claim file, pending deleted | `ThreadViewModel` auto-send, `takeAutoSend` `:115` |
| **Recreation of any kind** | **`MainActivity.kt:50`** | **record rewritten** | **`AppNavHost.kt:81` navigates to the picker** |

Baseline facts the fix leans on, each read at `6b9d19c`:

- `AppContainer.sharedDraftStore` is built once per process over
  `cacheDir/shared-drafts` (`AppContainer.kt:134-136`), so the ledger added below has the
  same lifetime and the same atomic-write idiom as `pending.json`
  (`SharedDraftStore.kt:136-142`: tmp file then rename).
- `AppRoot` renders nothing until the three stored values come off disk and only then
  mounts `AppNavHost` (`MainActivity.kt:169-197`) — so the observer can genuinely run
  before the NavHost's graph has a current destination, which is §2.2's third row.
- The Connect handoff already routes a pending share (`AppNavHost.kt:114-118`), so the
  signed-out case does not depend on the observer's null-route window.
- The JVM suite is plain JUnit4 + `coroutines-test` + `mockwebserver3` + `turbine`
  (`app/build.gradle.kts:17-20`): **no Robolectric**, so no existing test can call
  `onCreate`/`onNewIntent`. `androidTest` has `androidx.test.ext:junit`, Espresso, and
  Compose `ui-test-junit4` under the BOM (`:21-25`), with `ui-test-manifest` in debug
  (`:27`) — an `ActivityScenario` test needs **no new dependency**.
- F14 is `[DONE]` in `android/docs/Plan_TOC.md:192`, and `F14-share-into-app.md:383`
  carries the feature's Deviations list — the home for the one sentence this fix adds (§8).

## 4. Proposed change

One new seam, three small edits. The activity stops deciding anything about shares; it
hands the delivery to a gate and obeys.

### 4.1 `feature/share/ShareIntake.kt` (new) — the gate, pure

The decision is a function of six primitives, all readable off an `Intent` plus the
durable record, so it is JVM-testable without Robolectric (the `SharedKindParser` pattern:
the gate takes strings and booleans rather than an `Intent`, so the rules can be tested
at all). Two of them carry the whole distinction the issue asks for: `marked`, whether the
intent carries the mark this intake stamped into it last time it was served — which only
this app can write, so it means *redelivered* and not *arrived* — and `viaNewIntent`, which
separates a live delivery from a restoration even when the mark did not survive.

```kotlin
package com.hpz.llmdockchat.feature.share

enum class ShareIntake { Stage, KeepHydrated, IgnoreRedelivery }

object ShareDeliveryToken {
    const val EXTRA_MARK = "com.hpz.llmdockchat.extra.SHARE_DELIVERY_TOKEN"

    fun of(
        action: String,
        mimeType: String?,
        text: String?,
        streamUri: String?,
        title: String?,
        subject: String?,
    ): String                                     // sha-256 over NUL-joined fields, 16 hex

    fun mark(intent: Intent, token: String)        // putExtra(EXTRA_MARK, token)
}

object ShareIntakeGate {
    fun decide(
        action: String?,
        viaNewIntent: Boolean,
        marked: Boolean,
        launchedFromHistory: Boolean,
        hasSavedState: Boolean,
        token: String,
        handledToken: String?,
    ): ShareIntake = when {
        action != SharedKindParser.ACTION_SEND -> ShareIntake.IgnoreRedelivery
        marked -> ShareIntake.IgnoreRedelivery
        viaNewIntent && !launchedFromHistory -> ShareIntake.Stage
        token == handledToken -> ShareIntake.IgnoreRedelivery
        hasSavedState || launchedFromHistory -> ShareIntake.KeepHydrated
        else -> ShareIntake.Stage
    }
}
```

Reading of the six arms, in order:

1. Not a share. Nothing to decide.
2. **This very `Intent` was already served** — it carries the mark §4.3 stamps into it.
   Only this app ever writes that extra, so a mark is unambiguous evidence of redelivery
   rather than arrival: the framework hands the launch intent back on recreation, and under
   `singleTask` (`AndroidManifest.xml:23`) again on a task re-activation from Recents. This
   arm fixes the issue's reproduction — rotation after assign or dismiss.
3. **An unmarked intent delivered to `onNewIntent`, not through Recents** — somebody really
   did start this activity just now, so the payload replaces the pending share even when it
   is byte-identical to the previous one (criterion 3; F14-R1's "a share arriving while the
   app is already open"). This arm is why identity gates *redelivery* and never *delivery*:
   a content comparison alone cannot tell a replay from a user who shared the same line
   twice, and guessing wrong in this direction loses a share the user can see they sent.
4. **Already handled in an earlier life of this task** — the token matches what the store
   recorded, and the intent arrived without a mark, i.e. the platform rebuilt it from the
   task record rather than from the object we stamped. This is the durable half of the fix:
   it covers the issue's process-death and force-stop criteria, where `savedInstanceState`
   is absent (state loss, §2.3) and the mark may be gone. Checking it after arm 3 means it
   can only ever refuse a *restore*, never a live share.
5. **This activity is being restored** and nothing above settled it — a recreation of an
   *unfinished* share (criterion 2), or history re-activation of one whose `pending.json`
   still exists. `KeepHydrated` means: touch nothing, publish nothing, but record the claim.
   The content the user is entitled to keep is already on disk and already in the flow's
   hands; re-reading the intent would only make a second copy of it, and for an image a
   second read of a grant that may already be revoked.
6. A cold `onCreate`, unmarked, unhandled, no restoration in sight: the genuine first
   delivery. Stage it — the case `dev.sh share-text` drives (F14-R1's first criterion).

`launchedFromHistory` is `intent.flags and Intent.FLAG_ACTIVITY_LAUNCHED_FROM_HISTORY != 0`.
It is deliberately *not* load-bearing on its own (see Risks): it and the token are
independent layers over the same fact.

### 4.2 `feature/share/SharedDraftStore.kt` — one more durable file, the handled token

```kotlin
private val _handled = MutableStateFlow(readHandledToken())        // handled.json
val handledToken: String? get() = _handled.value
fun rememberHandled(token: String)                                 // write + publish
fun stage(share: StagedShare, token: String? = null)                // default keeps callers intact
```

`stage` gains a defaulted token so the eight existing JVM call sites
(`SharedDraftStoreTest`, `SummarizeCoordinatorTest`, `ShareTargetViewModelTest`,
`SharedDraftStoreAutoSendTest`) compile untouched, and writes `handled.json` **before**
`pending.json` — the crash window between the two then loses a share (the user re-shares)
rather than replaying one, which is the safe direction for a consume-once flow.
`clearPending`, `reassign` and `clear` deliberately **do not** clear the handled token: the
whole point is that the claim outlives the record it refers to. The claim writes
(`stageForAutoSend`, `takeAutoSend`) are not intent deliveries and stay token-free.

`handled.json` holds one token, not a set: only the activity's *current* launch intent can
be redelivered, so one slot covers every replay, and the file cannot grow. Same
`runCatching`-decode-corrupt-to-null discipline as `readPending` (`:130-134`).

### 4.3 `MainActivity.kt` — obey the gate, and never leave a share intent unmarked

`stageShareIfAny(intent)` at `:50` and `:81` is replaced by one private `intakeShare` called
from both places, told how the intent arrived (`viaNewIntent`) and whether the activity is
being restored (the bundle):

```kotlin
// onCreate:  intakeShare(intent, viaNewIntent = false, savedInstanceState != null)
// onNewIntent: setIntent(intent); intakeShare(intent, viaNewIntent = true, false)

private fun intakeShare(intent: Intent, viaNewIntent: Boolean, hasSavedState: Boolean) {
    val store = (application as LlmDockApplication).container.sharedDraftStore
    val marked = intent.getStringExtra(ShareDeliveryToken.EXTRA_MARK)
    val token = marked ?: ShareDeliveryToken.of(/* action, type, extras, stream uri */)
    val decision = ShareIntakeGate.decide(
        action = intent.action,
        viaNewIntent = viaNewIntent,
        marked = marked != null,
        launchedFromHistory =
            intent.flags and Intent.FLAG_ACTIVITY_LAUNCHED_FROM_HISTORY != 0,
        hasSavedState = hasSavedState,
        token = token,
        handledToken = store.handledToken,
    )
    ShareDeliveryToken.mark(intent, token)
    setIntent(intent)
    when (decision) {
        ShareIntake.IgnoreRedelivery -> return
        ShareIntake.KeepHydrated -> store.rememberHandled(token)
        ShareIntake.Stage -> Unit
    }
    val share = ...                                   // the current :95-127 body, verbatim
    store.stage(share, token)
}
```

Two rules of the seam are worth a comment each at their declaration (stable constraints,
per AGENTS *Comments*): why the token is marked *before* the content read (a stream read
can throw or fail, and a handled delivery must stay handled whatever the read did), and why
`mark` + `setIntent` happen on every decision including `IgnoreRedelivery` (the activity's
own launch intent must stop looking unhandled to the *next* recreation, independent of
whether the durable ledger is still on disk — cache is reclaimable). The classification and
stream-reading body (`:95-127`) is unchanged, so the diff is the gate, not the share
handling; `parcelableStream` (`:131`) and `readSharedTextFile` are untouched.

`onSaveInstanceState` gets nothing: the gate's inputs come from the intent, the bundle
pointer and the durable ledger, so no new instance state is introduced to lose.

### 4.4 `navigation/AppNavHost.kt` — navigate once the graph is ready, never twice

`:78-88` becomes: decide *inside* the effect, after the graph has a current destination,
and go `launchSingleTop`:

```kotlin
val pendingShare by container.sharedDraftStore.pending.collectAsState()
LaunchedEffect(pendingShare) {
    val share = pendingShare ?: return@LaunchedEffect
    val route = navController.awaitReadyDestination(SHARE_NAV_READY_TIMEOUT_MS) ?: return@LaunchedEffect
    if (route == Destinations.CONNECT || route == Destinations.SHARE_PICKER ||
        route == Destinations.NEW_CHAT || route == Destinations.NEW_CHAT_SUMMARIZE
    ) return@LaunchedEffect
    navController.navigate(Destinations.SHARE_PICKER) { launchSingleTop = true }
}
```

`awaitReadyDestination` is a file-private suspend helper: `callbackFlow` over
`addOnDestinationChangedListener`, seeded with `currentDestination?.route`, `firstOrNull`
under `withTimeoutOrNull`, listener removed in `awaitClose`. It resolves on the first
frame in the ordinary case and returns `null` while the app is sitting on Connect with no
graph at all — where `onSignedIn` (`:114-118`) is the path that navigates anyway, which is
why the timeout is a safe answer rather than a lost share.

`NEW_CHAT` / `NEW_CHAT_SUMMARIZE` join the skip set because the new-chat sheet *is* the
share flow's continuation screen (F14-R6, `onConversationCreated` → `reassign` `:360`; and
`NEW_CHAT_SUMMARIZE` was itself reached from the picker): navigating to the picker again
while it is open is what puts a second picker on the stack. The cost is recorded in §8 —
a share that arrives while the sheet is open updates the staged record the sheet will
consume, and does not force a screen change. `launchSingleTop` closes the duplicate-push
window that §2.2's first row opens.

### 4.5 Deliberately not changed

- The manifest intent filters (`AndroidManifest.xml:32-53`) — `singleTask` and the three
  declared SEND filters are what F14-R1 asked for; PDF/octet-stream stay excluded.
- `SharedKindParser`, `SharedInlineFormatter`, `SharedUrlExtractor` — pure and already
  tested; untouched.
- The store's attachment half and the summarize claim (`:69-129`) — already consume-once.
- `AppRoot`'s hydration gate (`MainActivity.kt:169-197`) and `startDestination(...)` — the
  resume design is F14's; §4.4 only makes the observer wait for the graph.
- `SharedDraft`'s serializable shape — no field is added to the payload the UI renders
  (`ShareTargetUiState.Loaded.share`). The provenance record lives beside it, in a file of
  its own, so the UI model stays the UI model.

## 5. Edge cases, against the six criteria

| # | Scenario | Which rule answers |
|---|---|---|
| 1 | Assign a text/image/file share → rotate | `onCreate` is handed the intent the intake marked when it served it → arm 2, `IgnoreRedelivery`: `:50` never re-stages, and the record `reassign` (`AppNavHost.kt:241`) deleted stays deleted. Nothing is published → the observer never runs → the destination is the restored one. |
| 1b | **Dismiss** a share → rotate | Same arm. `clearPending` (`AppNavHost.kt:261`) deletes `pending.json` and keeps `handled.json`, so a later cold redelivery is refused by arm 4 even once the mark is gone, and a same-task re-entry by arm 2 even once the cache dir is reclaimed. |
| 2 | Picker open (share unfinished) → rotate | Marked → `IgnoreRedelivery`, and hydration already put the same record back in `pending` (`SharedDraftStore.kt:32`). Exactly one record, no rewrite, no second decode of a possibly-dead grant. The observer sees the restored `share_picker` route and skips it. |
| 2b | Share staged, process killed, cold start with `pending.json` present and an **unmarked** intent (the platform rebuilt the task's launch intent) | Arm 4: the token is the one `stage` recorded alongside the record, so `IgnoreRedelivery` — and the record survives untouched instead of being rewritten from a second read of the intent. |
| 3 | Share A assigned, then share B arrives while the app is open | `onNewIntent` with a fresh, unmarked intent and a different token → `Stage`, replacing the record (F14-R1). |
| 3b | Share A assigned, then the **identical** share A′ arrives while the app is open | `onNewIntent` with an unmarked intent → arm 3, `Stage`: the record is replaced, so F14-R1 keeps its word even about a payload the user shared twice. Identity gates redelivery, never delivery. The same pair reaching a *cold* `onCreate` is refused by arm 4 — §8. |
| 4 | Background process recreation / force-stop then relaunch from Recents | A consumed share is refused by arm 2 (mark) or arm 4 (ledger); an unfinished one lands on arm 5, `KeepHydrated`. A launcher re-launch of a live task calls neither `onCreate` nor `onNewIntent` at all. |
| 5 | URL summarized, then rotate | Summarize clears pending (`stageForAutoSend` `:69`) *and* the token was claimed at intake; the claim is consume-once (`takeAutoSend` `:115`). No re-stage → no picker → no second action, and the claim itself is gone. |
| 6 | Back/cancel, then rotate | `clearPending` + `popBackStack` (`AppNavHost.kt:261-262`), and no new emission for the observer to act on. §4.4's `launchSingleTop` + graph-ready gate mean the picker is never pushed twice, so no empty entry is left under anything. |
| — | Corrupt or reclaimed `handled.json` | Decodes to `null`, so arm 4 cannot fire. A marked redelivery is still refused by arm 2 and a restore by arm 5, so losing the ledger alone never replays a share inside a live process — the `cacheDir` trade-off F14-R5 already documents for `pending.json`, and §8. |
| — | `ACTION_SEND_MULTIPLE` | Out of scope, unchanged (F14 4.7). |

## 6. Files to touch

| File | Change |
|---|---|
| `android/src/app/src/main/java/com/hpz/llmdockchat/feature/share/ShareIntake.kt` (new) | `ShareIntake`, `ShareDeliveryToken` (`of` / `EXTRA_MARK` / `mark`), `ShareIntakeGate.decide` |
| `android/src/app/src/main/java/com/hpz/llmdockchat/feature/share/SharedDraftStore.kt` | `_handled` + `handledToken` + `rememberHandled`; `stage(share, token = null)` writes `handled.json` first; `HANDLED_FILE` const; class KDoc gains the third record type |
| `android/src/app/src/main/java/com/hpz/llmdockchat/MainActivity.kt` | `onCreate` `:50` and `onNewIntent` `:81` call `intakeShare`; `stageShareIfAny` → `intakeShare` with gate + mark/setIntent around the unchanged `:95-127` body |
| `android/src/app/src/main/java/com/hpz/llmdockchat/navigation/AppNavHost.kt` | `:78-88` observer: decide inside the effect, `awaitReadyDestination`, `NEW_CHAT`/`NEW_CHAT_SUMMARIZE` skipped, `launchSingleTop`; file-private helper |
| `android/src/app/src/test/java/com/hpz/llmdockchat/feature/share/ShareIntakeTest.kt` (new) | §7.1 |
| `android/src/app/src/test/java/com/hpz/llmdockchat/feature/share/SharedDraftStoreTest.kt` | §7.2, appended to the existing `// -- pending` section |
| `android/src/app/src/androidTest/java/com/hpz/llmdockchat/testing/ShareIntents.kt` (new) | §7.3's `Intent` builders — in `androidTest`, because unit tests get the throwing `android.jar` stubs |
| `android/src/app/src/androidTest/java/com/hpz/llmdockchat/ShareRecreationInstrumentedTest.kt` (new) | §7.3 — the repo's first `ActivityScenario` test |
| `android/docs/F14-share-into-app.md` | one F14-R2 acceptance line (a consumed share does not return on recreation) + one Deviations entry (§8) |

No dependency changes. No `AndroidManifest.xml` change. Per root-AGENTS *Scope of
Changes*: bug-fix commit only — no reformat, re-quote or restyle of untouched lines. New
branch from a fresh `main`.

## 7. Test plan

### 7.1 JVM — `ShareIntakeTest` (the gate)

Plain JUnit4, no Android types in the call surface (`SharedKindParserTest` is the
template). One test per edge case, named for the behaviour:

1. `an unmarked cold delivery stages` — `decide(ACTION_SEND, viaNewIntent=false, marked=false, launchedFromHistory=false, hasSavedState=false, token="a", handledToken=null)` → `Stage`. → F14-R1's first criterion, unpinned today by any test.
2. `a marked intent is refused whichever callback carried it` — `marked=true`, tried with `viaNewIntent` both `true` and `false` → `IgnoreRedelivery` in both. → criteria 1, 1b, 2, and the reproduction itself.
3. `an unmarked onNewIntent replaces the record even for an identical payload` — `viaNewIntent=true`, `marked=false`, `token == handledToken` → `Stage`. This is the arm a naive identity check gets wrong, so it is pinned explicitly. → criterion 3.
4. `a cold redelivery of a handled payload is refused` — `marked=false`, `viaNewIntent=false`, `token == handledToken` → `IgnoreRedelivery`. → criteria 2b, 4: the process-death shape, which a `savedInstanceState` test cannot see.
5. `a restored activity keeps the hydrated record instead of re-reading the intent` — `hasSavedState=true`, unhandled token → `KeepHydrated`; the decision names no re-stage, which is the difference from today's unconditional path. → criterion 2.
6. `re-activation from history never stages` — `launchedFromHistory=true`, with and without `viaNewIntent` → `KeepHydrated`. → criterion 4.
7. `a non-send action is none of the gate's business` — `null` / `ACTION_MAIN` / `SEND_MULTIPLE` → `IgnoreRedelivery`.
8. `a token is stable for one delivery and differs across payloads` — `of(...)` is equal across two identical calls; differs on text, mime, stream uri, title, subject; survives the `null` combinations without throwing; length/radix shape pinned. The whole gate rests on this function's stability, so it is pinned directly and not through the decision table.

Nothing in 7.1 touches `android.jar`: unit tests run against the throwing stubs — there is
no `testOptions.unitTests.returnDefaultValues` in `app/build.gradle.kts` — so `Intent` is
not constructible here. That is the existing `SharedKindParser` arrangement (strings and
booleans in, never an `Intent`), and the reason §4.1's gate takes primitives while
`MainActivity` keeps the extraction `:96-105` already performs. The mark/`setIntent`
round-trip is therefore device-only: §7.3/1 asserts it against a live activity.

### 7.2 JVM — `SharedDraftStoreTest` additions (the ledger)

1. `a staged share records its delivery token as handled` → `stage(s, "a")` then a **fresh store over the same dir** reports `handledToken == "a"` (process death).
2. `clearPending consumes the record and keeps the claim` → after `clearPending()` the record is gone but `handledToken` still `"a"`, and a fresh store agrees. → criteria 1b, 5: this is the exact asymmetry the fix needs, so it is pinned at the store level too.
3. `reassign keeps the claim` → same after `reassign`. → criterion 1.
4. `a corrupt handled record reads as no claim` → write garbage over `handled.json`, fresh store → `handledToken == null`, and `pending` hydration is unaffected.
5. `stage with no token leaves the claim alone` — the defaulted overload used by every existing call site and by `stageForAutoSend`.
6. Regression: the existing ten-odd tests must pass without edits, which is what the defaulted `token` parameter buys.

### 7.3 Instrumented — `ShareRecreationInstrumentedTest` (the activity path nothing can reach today)

`ActivityScenario.launch<MainActivity>(shareIntent)` + `onActivity { it.recreate() }`,
asserting through the live container (`(activity.application as LlmDockApplication).container.sharedDraftStore`)
rather than the UI, so no signed-in dashboard session is needed for these three:

1. **`a consumed share does not come back on recreate`** — launch with `text/plain` +
   `EXTRA_TEXT`, assert `pending.text` is the payload, `clearPending()`, `recreate()`,
   assert `pending.value == null`. **This test is red on `6b9d19c`** — it is the issue's
   reproduction, expressed as an assertion instead of a UIAutomator dump.
2. **`a recreate while the picker is open preserves exactly one record, unwritten`** — capture
   the file's `lastModified()` after the first stage, `recreate()`, assert `pending.text` is
   unchanged and the file was not rewritten (no second `writePending`, hence no second
   decode of the stream grant).
3. **`a second share delivered to the running activity replaces the record`** — `launch` a
   second scenario with a different payload against the same task (this is what
   `singleTask` routes to `onNewIntent`), assert the new text and the new claim.
4. `the recreate after an image share keeps the staged data url` — `image/*` variant via
   `FileProvider`/MediaStore (`dev.sh share-image`'s shape, `android/scripts/dev.sh:345-357`),
   guarding the F14-R5 "bytes copied at intent time" rule against the double read.
   `Intent` + `Uri` construction lives in `testing/ShareIntents.kt`.

Device criteria (the Android bar in `android/CLAUDE.md`): a screenshot or instrumented
evidence for "recreation keeps the destination" — the store-level assertions above do not
observe the route, and route restoration is Compose Navigation's own behaviour. §7.4 covers
it on `emulator-5554`.

### 7.4 Device pass — the issue's own reproduction, inverted

```bash
android/scripts/dev.sh install
android/scripts/dev.sh share-text ANDROID_REVIEW_FIRST_SHARE
adb -s emulator-5554 shell uiautomator dump /sdcard/w.xml   # share_target_screen present
adb -s emulator-5554 shell input keyevent KEYCODE_BACK       # dismiss
adb -s emulator-5554 shell settings put system user_rotation 1
android/scripts/dev.sh ui                                     # share_target_screen ABSENT, chats route present
android/scripts/dev.sh shot
```

Then, at each stop, the same rotate/`dev.sh ui` check for: assign-then-rotate (row tap →
thread → rotate → still the thread, composer text still staged); image and file shares
(`dev.sh share-image`, `dev.sh share-file`); summarize (`ANDROID_REVIEW_URL_SHARE` →
Summarize → rotate → no picker, no second turn); force-stop-then-relaunch (`am
force-stop com.hpz.llmdockchat`, then `dev.sh emu`/launcher) with a consumed share; and a
pass with `settings put global always_finish_activities 1` set, reverted afterwards. The
issue's payload marker (`ANDROID_REVIEW_SECOND_SHARE`) is reused in the commit message so
the reproduction stays traceable.

`./gradlew testDebugUnitTest lintDebug` with `JAVA_HOME=/opt/android-studio/jbr` (the
system JDK 11 cannot run Gradle 9.5.1), and `assembleDebug`. `ThreadToolsTest` is a known
intermittent in this suite (`android/CLAUDE.md`) — read it rather than counting it.

## 8. Risks and recorded trade-offs

- **Neither the mark's reach across process death nor the history flag is contract.**
  `setIntent` is documented; that the *modified* intent is what a later task restoration
  redelivers is behaviour. Same for the flag, which no platform contract promises to a share.
  That is why the gate carries three: arm 2's mark, arm 4's durable token, arm 5's flag, each
  covering the others' absence, so a replay needs all three to fail on one delivery. The gate
  interface carries the one permitted comment; 7.1/2, 7.1/4 and 7.1/6 pin today's reading.
- **A byte-identical share reaching a cold `onCreate` after the same payload was handled is
  dropped** (5/3b, the cold shape). No signal separates it from a replay: the OS kept the
  payload and discarded the delivery. Blast radius is one share the user sends again, then
  served by `onNewIntent` (arm 3) because the app is by then running; the alternative is the
  bug being reported. Chosen deliberately, against the time-window variant (§9).
- **`handled.json` lives in `cacheDir`** and the OS can reclaim it, so the ledger is not a
  guarantee — it is one of two independent layers, with the intent mark as the other. The
  cache choice is F14's existing decision (`AppContainer.kt:133`, "cache, so the OS may
  reclaim it, and never backed up"); a replay needs both the ledger *and* the mark to be
  gone, which means an unreclaimable cache dir plus a task-intent redelivery — i.e. exactly
  the case §4.3's `setIntent` neutralization covers.
- **§4.4's skip-set grows the denylist.** A share arriving while the new-chat sheet is open
  updates the record the sheet will consume but does not navigate. That is a smaller
  deviation from F14-R1's "on any screen" than a duplicated picker stack, and it is the
  sheet's own job to show what is staged.
- **`awaitReadyDestination` adds one coroutine to the app's only global navigation
  observer.** If the graph never becomes ready within the timeout the observer does nothing
  — the same outcome as a share arriving on Connect, whose path (`:114-118`) does not go
  through it.
- **Docs**: F14 gains one acceptance line under R2 and a Deviations entry saying the
  consume-once rule is enforced at intake by a delivery token, not by clearing the store —
  so the next reader does not "simplify" it back to `savedInstanceState` or to a restore
  that wipes the store. `Plan_TOC.md:192` stays `[DONE]`.

## 9. Rejected alternatives

| Alternative | Why not |
|---|---|
| `if (savedInstanceState == null) stageShareIfAny(intent)` | Fixes the rotation repro only, and the issue itself rules it out ("insufficient for every task/process restoration case"). It also refuses a *genuine* delivery whenever the bundle is non-null, which is the "Don't keep activities" shape, and keeps a live `ACTION_SEND` launch intent that every future restore re-reads. |
| Clear the durable store on restore | Breaks F14-R5 (force-stop with staged content must survive) and F14-R4, and destroys criterion 2's "exactly one pending share" by turning it into zero. |
| `setIntent(Intent(this, MainActivity::class.java))` alone (replace, not mark) | Works for the in-process paths and keeps `getIntent()` honest for a future reader, but the platform makes no promise that a replacement reaches a later process-death redelivery, and it *hides* the handled state inside a fabricated non-share intent instead of recording it. Marking keeps the launch shape intact and is the part of the idea that composes with the ledger. |
| Flag on the pending record (`StagedShare.intentId`) instead of a sibling file | The record that needs the claim is the one about to be deleted at consumption, so a field inside it cannot outlive the consume — which is the entire requirement. It also pushes an Android-intake detail into the UI payload. |
| Content-hash set with a TTL window | A time window makes the behaviour depend on how long the user lingered on the picker, is not testable without a clock seam, and still cannot separate an identical re-share from a replay. |
| `onSaveInstanceState` marker in `MainActivity` | Adds instance state to a class that has none today, is lost on every path where the state is discarded — precisely the failing cases — and cannot be JVM-tested without Robolectric, which is not in the verified dep set (`docs/Architecture.md`). |
| `launchSingleTop` on the observer as the whole fix | Stops the double picker; leaves the re-stage, so the consumed share still returns on the next foregrounding. §4.4 ships it as the accompanying hardening, not the fix. |
| Filter on `Intent.FLAG_ACTIVITY_LAUNCHED_FROM_HISTORY` alone (no identity) | Cheapest diff that kills the reported repro and the Recents shape, but not assign-then-rotate (`savedInstanceState != null`, no history flag) — criteria 1 and 5 stay broken. Kept as a layer instead (arm 5).
| Ledger check ahead of the `onNewIntent` arm | One line earlier in the same `when`, and criterion 3 breaks: a payload shared twice while the app is open is indistinguishable from a replay by content, and F14-R1 says the second one wins. The mark is the signal that separates them, so it is arm 2 and the content check only ever refuses a *restore*. |
