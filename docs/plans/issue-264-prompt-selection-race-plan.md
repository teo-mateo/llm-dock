# Android: prompt-selection writes must not roll back a newer selection

Issue [#264](https://github.com/teo-mateo/llm-dock/issues/264) —
`[Android][P2] Prompt selection responses can roll back a newer successful
selection`. Client-only fix: one ViewModel, one test file, no dashboard
changes.

Baseline reviewed: `main` at `415c0ccb` (the issue's baseline) — re-read at
`6b9d19cc`, the code path is unchanged. Line references below are against the
current tree.

## 1. Problem

`ThreadViewModel.selectPrompt`
([`android/src/app/src/main/java/com/hpz/llmdockchat/feature/thread/ThreadViewModel.kt:377-397`](../../android/src/app/src/main/java/com/hpz/llmdockchat/feature/thread/ThreadViewModel.kt#L377))
is the only per-thread setting write in the app with neither ordering nor a
staleness guard:

- Each selection launches an independent `viewModelScope.launch` PUT
  (`ConversationsRepository.setPrompt`,
  [`data/ConversationsRepository.kt:118`](../../android/src/app/src/main/java/com/hpz/llmdockchat/data/ConversationsRepository.kt#L118)).
  Two launches race on the dispatcher, so the requests can reach the server out
  of selection order — the final server value can be the older pick.
- The failure handler captures `previous` at click time and restores it
  *unconditionally*. A late failure for a superseded selection A overwrites a
  newer successful selection B: the server holds B, the UI shows `previous`.
  The issue's probe recorded exactly this —
  `REVIEW_PROMPT: last successful server write=B, displayed=null`.

## 2. Root cause

The same file already solves this shape twice, and prompt selection is the one
writer that never adopted it:

| Writer | Ordering | Staleness guard | Rollback target |
|---|---|---|---|
| `toggleTool` — ThreadViewModel.kt:399-422 | `toolsWriteLock` Mutex (:63) | `if (toggle != latestToolsToggle) return@fold` (:412) | `previous` captured at click |
| `selectReasoningLevel` — ThreadViewModel.kt:174-203 | `levelWriteLock` Mutex (:67) | `if (write != latestLevelWrite) return@fold` (:192) | `previous` captured at click |
| `selectPrompt` — ThreadViewModel.kt:377-397 | none | none | `previous` captured at click, applied always |

Two independent defects follow from that gap:

1. **No serialization** — concurrent launches mean the server can observe B
   before A (a successful request out of selection order; the whole-array
   `mcp_servers_json` race the tools lock exists for, in single-field form).
2. **No staleness check on rollback** — A's failure handler cannot know B has
   moved past it, and its `previous` restore is unconditional.

A third, subtler point the tools/level pattern does **not** already solve:
their rollback target is `previous` captured at click time, which is the
*optimistic* value of the prior click, not necessarily the confirmed server
value (prior click still in flight, or already failed while a newer click was
queued). Issue acceptance criterion 3 — "a failed newest write returns to the
actual confirmed server value" — needs a **confirmed-state tracker** layered on
top of the Mutex + token pattern, not just the pattern itself.

The frontend precedent named in `AGENTS.md` is the same discipline:
`dashboard/frontend/AGENTS.md` — "`useChat` race discipline is load-bearing",
refs/generations fixing A→B→A navigation and stale-fetch clobbering. Last
write wins at the server, generation token at the client, revert only for the
generation that is still current.

## 3. Proposed change

All production edits are inside `ThreadViewModel.kt`. No wire change:
`setPrompt` keeps its body (`{"prompt_id":"…"}`, detach
`{"prompt_id":null,"main_system_prompt":""}`), no new endpoints, no DTO change.

### 3.1 State

New fields next to the tools/level ones (ThreadViewModel.kt:63-68):

```kotlin
private val promptWriteLock = Mutex()
private var latestPromptWrite = 0L
private var promptConfirmedId: String? = null
```

`promptConfirmedId` is the last value this client knows the server holds.
It is seeded from every wholesale server read of the conversation, so the
three points where `conversation` is replaced by a fetched
`ConversationDetail`:

- `loadedFrom` (:121-139) — the `load()` path,
- `reloadConversation` (:275-285),
- `finishRun`'s refetch success branch (:736-741).

Each gets `promptConfirmedId = <fetched>.promptId`. `applyTitle` (:744-748)
touches only the title and must not touch confirmed state (a prompt write in
flight across an auto-title frame must keep its confirmation).

### 3.2 Selection

```kotlin
fun selectPrompt(promptId: String?) {
    val current = loaded() ?: return
    if (!current.canToggleTools) return
    if (current.conversation.promptId == promptId) return
    _state.value = current.copy(
        conversation = current.conversation.copy(promptId = promptId),
    )
    val write = ++latestPromptWrite
    viewModelScope.launch {
        promptWriteLock.withLock {
            if (write != latestPromptWrite) return@withLock
            conversationsRepository.setPrompt(conversationId, promptId).fold(
                onSuccess = {
                    promptConfirmedId = promptId
                    val latest = loaded() ?: return@fold
                    if (write == latestPromptWrite && latest.conversation.promptId != promptId) {
                        _state.value = latest.copy(
                            conversation = latest.conversation.copy(promptId = promptId),
                        )
                    }
                },
                onFailure = { failure ->
                    if (write != latestPromptWrite) return@fold
                    val latest = loaded() ?: return@fold
                    _state.value = latest.copy(
                        conversation = latest.conversation.copy(promptId = promptConfirmedId),
                        actionError = failure.appError.displayMessage,
                    )
                },
            )
        }
    }
}
```

Reading of each rule:

- **`promptWriteLock`** — one PUT on the wire at a time, requests leave in
  selection order. Same role as `toolsWriteLock`.
- **`write != latestPromptWrite` before sending** — a selection superseded
  while still waiting for the lock is dropped, never sent. The newest
  selection always sends (its token is current at its own lock acquisition),
  so the server always converges on the latest pick. This is the issue plan's
  "superseded unsent selections are coalesced explicitly" — coalescing falls
  out of the token check instead of needing a queue: rapid A → B → C leaves
  exactly one PUT, `C`.
- **`onSuccess` sets `promptConfirmedId = promptId` for every settled
  success, latest or not.** With the Mutex, sends complete in click order, so
  "last success wins" *is* "the newest success wins", and a stale success that
  did reach the server is genuinely what it holds until the next send settles.
  Skipping this would make the criterion-3 rollback wrong in one case: A
  succeeds, B (newer) fails — the server holds A, but without recording A the
  restore would go back past it.
- **`onSuccess` re-asserts the display only when still latest.** A newer
  optimistic pick already owns the display; a mid-write server read may have
  clobbered it — in that case re-asserting our succeeded value is correct
  because the server now holds it.
- **`onFailure` restores `promptConfirmedId`, not click-time `previous`.**
  That is acceptance criterion 3: the restore target is provably the server's
  state — the last confirmed value, updated by every completed write and by
  every full conversation read.
- **A stale failure is silent** (`return@fold` before anything). The tools
  handler (:412) does the same: a superseded write's verdict is irrelevant,
  the newest op will settle the UI and report its own error if it fails.
  Showing A's late 404 after B succeeded would be exactly the lie the issue
  is about.

Why restore-to-confirmed rather than the plan's alternative "reconcile by
GET": a GET races the user's next click and needs its own sequencing, while
confirmed-state tracking is already required for criterion 3 and makes the
restore provably correct without a new request. (Recorded as a rejected
alternative, §6.)

The captured `previous` local disappears; the failure path no longer needs
it.

### 3.3 Comments

One KDoc on `promptConfirmedId` — it is a contract (`the last value the server
confirmed; the rollback target for a failed latest write, updated on every
settled success and every full conversation read`), which is the permitted
kind and is what distinguishes it from the tools/level `previous` captures.
Everything else is carried by names and by tests (§5).

## 4. Edge cases

- **Detach (`null`) as newest** — the type is `String?` end to end; a
  superseded detach is skipped like any other, a failed newest detach restores
  the confirmed id. The detach body (explicit `JsonNull` +
  `main_system_prompt: ""`) is untouched — wire semantics preserved.
- **Two identical picks with a failure between** — after a failed latest write
  the display is the confirmed value ≠ the failed pick, so re-selecting it
  passes the `promptId == promptId` no-op guard and retries. The existing
  no-op guard itself is unchanged (it compares against the latest optimistic
  value, matching the existing `reselecting the current reference sends
  nothing` test).
- **Server read while a write is in flight** (`reloadConversation` after
  stop/switch-model, `finishRun` refetch after a turn, re-open via `load()`) —
  confirmed state is re-seeded from the fetch, which is a fresh GET of the
  truth, so a subsequent rollback uses the post-read value. If our in-flight
  write then succeeds it re-asserts display and confirmation.
- **Refused during a run** — `canToggleTools` guard kept; the refusal test
  shape carries over unchanged.
- **`promptConfirmedId` before first load** — unreachable: `selectPrompt` and
  every rollback require `loaded()`, and `loadedFrom` seeds the field before
  any Loaded state exists.
- **Cancelled ViewModel** — a PUT already on the wire still lands (OkHttp
  blocking call, same as the tools fake's `NonCancellable` note); no state
  write survives the scope. No behavior change from today.
- **Out of scope deliberately:** `toggleTool`/`selectReasoningLevel` keep
  their click-time-`previous` rollback. Their token guard already prevents
  the P2 class of bug; the confirmed-tracker upgrade for them is a follow-up,
  not this issue — issue scope is prompt selection, and the tools rollback
  semantics (`previous` = last click-time value) are what F08 was verified
  against.

## 5. Test plan

JVM suite (`./gradlew testDebugUnitTest` with `JAVA_HOME=/opt/android-studio/jbr`),
all in
[`ThreadPromptSelectionTest.kt`](../../android/src/app/src/test/java/com/hpz/llmdockchat/feature/thread/ThreadPromptSelectionTest.kt)
extending the existing file; the race tests copy the shape of
`ThreadToolsTest`'s `OutOfOrderMcpWrites` gate (subclass of
`ConversationsRepository`, `NonCancellable` park, bounded gate timeouts).

New private fake — `GatedPromptWrites(api) : ConversationsRepository(api)`:
overrides `setPrompt`, parks call *n* on gate *n* (call order = send order once
the Mutex holds), then applies a per-index scripted outcome
(`Success(value)` / `Failure(code, message)`) to a `@Volatile stored: String?`
— the fake's server copy — and signals arrival + settlement on channels. No
clock sleeps anywhere; ordering is signalled, matching the tools test's
"nothing here waits on the clock" rule.

Tests (existing five regressions must pass unedited):

1. **`a late failure for a superseded select cannot erase the newer success`**
   — the issue probe. Load with `prompt_id = null`; select A (fails, gate 0);
   `drainMain()` (A on the wire); select B; release gate 0 → A's failure
   handler must be a no-op (display still B, no `actionError`); gate 1 settles
   success. Assert displayed `promptId == B` and `stored == B`. Pins
   acceptance criteria 1 and 2.
2. **`prompt writes settle in selection order`** — select A, `drainMain()`,
   select B: gate 1 has no arrival until gate 0 releases. With the pre-fix
   code both writes park at once; with the Mutex the second cannot even start.
   Pins "requests stay ordered".
3. **`a failed newest write restores the last confirmed prompt, not the
   prior optimistic pick`** — two variants, fixture
   `conversation_with_prompt.json` (confirms P1 at load).
   *(a) Superseded-skip shape:* select P2, then P3 while P2 waits on the
   lock; P2 never reaches the fake, P3 fails as latest. Assert display P1,
   one `actionError`, and exactly one call arrived — the click-time-`previous`
   pattern would restore P2 here, which the server never held.
   *(b) Confirmed-advances shape:* select P2 and let it settle success, then
   select P3 and let it fail as latest. Assert display P2 (the advanced
   confirmed value) and `stored == P2`. Pins acceptance criterion 3 both ways.
4. **`multiple failed selects, including a detach, leave the confirmed
   selection displayed`** — confirmed P1; select P2 (404), select `null`
   (404), each latest at its own failure. Final display P1, one `actionError`
   carrying the last failure's message, `stored` P1. Covers the issue's
   "multiple failed selections" and "include selecting None".
5. **`rapid selects coalesce to one PUT carrying the last pick`** — select
   A, B, C with `drainMain()` between (gates 0-1 keep any send that does
   start parked); after release, exactly one call reached the fake and it
   carries `C`. Pins the coalescing acceptance criterion.
6. Wire-shape regressions already in the file (`id`-alone PUT, detach body,
   no-op reselect, single-select failure revert) guard "existing prompt-id
   wire semantics and None detachment are preserved".

Device pass (android/CLAUDE.md quality gate): logic criteria are JVM-proven
above; one emulator check that rapid prompt changes in the settings sheet end
showing the last pick, via `dev.sh ui`/`shot`, recorded in the PR.

## 6. Rejected alternatives

- **Single-writer coalescing queue** (one long-lived writer loop consuming a
  latest-intent slot). Equivalent outcome, more moving parts (writer-liveness
  flag, pending slot) than Mutex + token-skip, which gets coalescing for free.
- **Reconcile by GET on latest failure.** Extra request, races the next click,
  needs its own token; confirmed tracking already keeps the server value
  locally without it.
- **Restore click-time `previous` behind the token guard (pure tools pattern).**
  Fails acceptance criterion 3: `previous` is the prior click's optimistic
  value, not the server's. Test 3 is written to kill this variant.
- **Version/revision precondition on the conversation PUT.** The dashboard's
  update endpoint has no If-Match/revision support (R-A backend parity forbids
  new server code here anyway).
