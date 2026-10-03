# Android: a failed Stop must not disable the Stop button (issue #263)

**Problem.** Tapping Stop on a streaming answer, then having the cancel request
fail (HTTP 503, network loss), leaves the run's `stopping` flag set forever: the
composer shows a disabled Stop, the turn says "Stopping…", generation continues
server-side, and the only escape is leaving and reopening the thread. The
failure handler in `ThreadViewModel.stop` reports the error but never reverses
the optimistic pending-stop state the same method applied.

**Fix.** On cancel failure, clear `stopping` on the *latest* streaming turn —
guarded by run identity so a late failure cannot touch a newer run — while
keeping every token that arrived in the meantime. One method, one file, plus
JVM regression tests.

Baseline: `main` at `6b9d19c` (the issue's review baseline was `415c0cc`; the
code under discussion is identical on both).

## 1. Problem statement

F04-R6 gives the thread screen a Stop control for the active run.
`stop()` optimistically marks the streaming turn `stopping = true` before the
request, so the UI can say "Stopping…" and refuse double-taps. The pending
presentation is correct while the request is in flight and correct after
success — the server resolves the run, the stream's terminal handling clears
the turn. But when the *request itself* fails, nothing reverts the flag, even
though the run is still streaming and Stop is again the right affordance.

Issue #263's probe reproduced it: parked run, cancel returns 503
`{"error":"cancel unavailable"}`, and the state afterwards reads
`stopping=true, error=cancel unavailable` — the error is shown once and the
recovery action is permanently disabled. P2: no data loss, but the user is
stuck without navigating away.

## 2. Root cause

The pending-stop write and its un-undo live two lines apart, and only one of
them exists.

| Step | Where | What happens |
|---|---|---|
| 1 | `android/src/app/src/main/java/com/hpz/llmdockchat/feature/thread/ThreadViewModel.kt:257-273` | `stop()` resolves the target run id (`turn?.runId ?: conversation.activeRun?.id`), and at line 263 writes `turn.copy(stopping = true)` into the streaming turn. |
| 2 | `ThreadViewModel.kt:266-271` | `repository.cancelActiveRun(conversationId, runId).fold(...)`. `onSuccess` acts only in the `turn == null` case. **`onFailure` (line 268-270) re-reads the latest state and sets `actionError` only — `stopping` is never cleared.** |
| 3 | `feature/thread/ComposerRow.kt:122-130` | With a run active the composer renders the Stop button with `enabled = !stopping` (line 127) — fed by `ThreadScreen.kt:928`, `stopping = state.thread.streaming?.stopping == true`. The button stays disabled for the life of the turn. |
| 4 | `feature/thread/ThreadScreen.kt:646,709` | The waiting indicator keeps reading "Stopping…" because it renders off the same flag. |
| 5 | `ThreadViewModel.kt:750-763` | `publishTurn` rebuilds the streaming turn on every coalesced token flush *carrying the flag forward* (`stopping = existing?.stopping == true`), so the stuck state survives any number of subsequent tokens. |

`ChatRepository.cancelActiveRun`
(`data/ChatRepository.kt:96-104`) is a plain `apiCall`, so a 5xx, a 4xx or an
IOException all arrive as `Result.failure` — including the
cancellation-is-not-accepted case the issue is about. A run that already
finished is *not* a failure (200 `{"run": null}`, per F04-R6), so this handler
never fires spuriously on the happy path.

The only existing `stopping = false` writer is the dropped-stream hold path
(`ThreadViewModel.kt:716-732`), which runs when the run *stream* fails and its
refetch also fails. A failed cancel POST leaves the stream healthy, so that
path never runs, and no state transition afterwards clears the flag: the
pending presentation is permanent for that turn.

The failure handler's shape also matters for the fix: it re-reads `loaded()`
rather than reusing the pre-request `turn`, which is correct — restoring the
captured pre-request turn would erase tokens that arrived during the cancel
round-trip (the issue's plan item 2).

## 3. Proposed change

`stop()`'s failure branch gains a restore step, factored into a private
`ThreadViewModel` method:

```kotlin
fun stop() {
    val current = loaded() ?: return
    val turn = current.thread.streaming?.takeUnless { it.unconfirmed }
    val runId = turn?.runId ?: current.conversation.activeRun?.id
    if (turn == null && runId == null) return
    if (turn != null) {
        _state.value = current.copy(thread = current.thread.copy(streaming = turn.copy(stopping = true)))
    }
    viewModelScope.launch {
        repository.cancelActiveRun(conversationId, runId).fold(
            onSuccess = { if (turn == null) reloadConversation() },
            onFailure = { failure -> restoreStop(runId, failure.appError.displayMessage) },
        )
    }
}

private fun restoreStop(expectedRunId: String?, message: String) {
    val latest = loaded() ?: return
    val streaming = latest.thread.streaming
    val cancelsMarkedRun = streaming?.stopping == true &&
        (expectedRunId == null || streaming.runId == expectedRunId || streaming.runId == null)
    _state.value = latest.copy(
        thread = latest.thread.copy(
            streaming = if (cancelsMarkedRun) streaming?.copy(stopping = false) else streaming,
        ),
        actionError = message,
    )
}
```

Decisions carried by this shape:

- **Clear, don't drop.** The run is still streaming — the SSE stream is up and
  frames keep flowing — so the turn must stay on screen, just no longer marked
  as being stopped. The second tap re-arms the pending presentation and sends
  a fresh cancel with the *current* turn's run id.
- **Latest state, never the captured turn.** `restoreStop` re-reads `loaded()`
  and copies `stopping = false` onto whatever the streaming turn is now, so
  tokens published by `publishTurn` during the failed round trip survive
  (issue plan item 2). The captured `turn` from before the request is used
  only to carry the marked turn's identity into the guard.
- **Run-identity guard** (issue plan item 3): the flag is cleared only when
  the current turn still carries a pending stop *and* still belongs to the run
  the failed request targeted — `streaming.runId == expectedRunId` when the
  request carried an id. The `streaming.runId == null` fallback covers the
  marked turn not having seen `run_started` yet; the only way a *different*
  run can present as null-id-and-stopping is a fresh send whose Stop was
  tapped before its `run_started` arrived, whose own cancel is by then
  in flight — the stale restore removes a presentation the in-flight request
  will re-confirm or the response will correct, and can never leave the
  button stuck (which is the failure mode this issue is about). Acceptance
  criterion 5 is tested with announced ids, the realistic ordering.
- **Error always shown**, even when the guard rejects the restore: a cancel
  request the user made did fail, and F00-R4 forbids silent failures. This
  matches today's behaviour, which already sets `actionError`.
- **Success paths untouched.** With a streaming turn, `stopping = true`
  remains until the server resolves the run through the stream (criterion 4);
  the `turn == null` reload-on-success stays.

Per `AGENTS.md`, the change ships without comments — the run-identity guard
lives in its named method and in tests named for the behaviour (section 5);
this document carries the *why*.

## 4. Edge cases

| Case | Behaviour after the fix |
|---|---|
| Cancel POST returns 4xx/5xx while tokens keep arriving | Flag cleared on the latest turn, error shown, streamed text intact; Stop button enabled again. |
| Cancel POST fails at the network layer (offline, connection dropped) | Identical — `apiCall` surfaces an `IOException` failure; same restore path. |
| Run reaches its terminal (or any stream event) while the cancel request is in flight | `publishTurn`/`finishRun` run normally; the restore copies onto the latest turn. If the terminal already removed the turn (`streaming == null`), the guard is false and only the error shows — no turn is resurrected. |
| Cancel succeeds (200, `{"run": ...}` or `{"run": null}`) | Unchanged: pending presentation persists until the server resolves the run via the stream or the `turn == null` reload. |
| Late failure for run A while run B is now streaming and itself pending stop | `streaming.runId` (B) ≠ `expectedRunId` (A) → B's `stopping` untouched; only the error is shown. |
| Stop tapped with no streaming turn (conversation payload claimed an active run) | `turn == null`, no flag was ever set; failure shows the error, exactly as today. |
| Stop during an unconfirmed held-over turn | `stop()` ignores such turns already (`ThreadViewModel.kt:259`); unaffected. |
| Second tap after a failed stop | Same code path as any Stop: one POST, `expected_run_id` from the current turn (criterion 3). |
| Repeated failures | Idempotent: each failure restores `stopping = false` and replaces `actionError`; no accumulating state. |

## 5. Test plan

All logic criteria are JVM tests (the bar set by `android/CLAUDE.md`), in the
F04-R6 section of
`android/src/app/src/test/java/com/hpz/llmdockchat/feature/thread/ThreadViewModelTest.kt`,
whose harness (parked `FakeSseTransport` + real `MockWebServer`) is built for
exactly the "was a cancel request sent, and with what body" questions here.

1. **`a failed stop re-enables Stop and keeps the streamed partial`** —
   parked stream serving `RUN_STARTED` + `delta("Once upon")`; send; wait for
   the run id; enqueue `MockResponse.Builder().code(503).body("…cancel unavailable…")`
   (precedent: `data/HealthRepositoryTest.kt:108`); `stop()`;
   `awaitState { it.thread.streaming?.stopping == false && it.actionError != null }`.
   Assert `actionError == "cancel unavailable"`, `streaming.content == "Once upon"`,
   `runActive` still true. Covers acceptance criteria 1 and 2.
2. **`a stop retried after a failed stop sends exactly one new cancel`** —
   continues from test 1's state: checkpoint `server.requestCount`, enqueue a
   200 `{"run":{"id":"run-1","status":"cancelled"}}`, tap `stop()` again,
   `takeRequest()` and assert `POST …/cancel-active-run` with body
   `{"expected_run_id":"run-1"}`, assert `awaitState { stopping == true }`
   (retry re-arms the pending presentation) and
   `server.requestCount == checkpoint + 1` — one wire request for the retry,
   the issue plan's item 4. Covers criterion 3.
3. **`a late cancel failure for an earlier run leaves the newer run's pending stop alone`** —
   needs the run stream to move on while cancel #1 is still in flight, so it
   uses `ScriptedSseTransport` (its `endGate`/`tailPayloads` legs give
   deterministic ordering; the `MockResponse.bodyDelay` precedent is
   `ThreadTerminalPathTest.kt:211`): leg 1 emits `RUN_STARTED(run-1)` + a
   delta and holds on `endGate`; cancel #1 enqueued as 503 with
   `bodyDelay(1500, MILLISECONDS)`; `stop()`; release the gate with
   `[DONE, MESSAGE_SAVED]` tail payloads and a queued
   `conversation_completed.json` refetch; `send()` again against a leg 2
   emitting `RUN_STARTED(run-2)`; `stop()` again (cancel #2 = 200); after the
   delayed 503 lands, assert `streaming.stopping` is still true, the turn's
   `runId == "run-2"`, and exactly two cancel POSTs went out. Covers
   criterion 5. Lives in `ThreadReattachTest.kt`, which already owns the
   scripted-transport harness, next to the F09-R3 stop test at line 349.
4. **Criterion 4 (success retains the pending presentation)** is already pinned
   by the existing `stop cancels by conversation with the captured run id`
   (`ThreadViewModelTest.kt:471`) plus `after a cancel the partial answer is
   dropped and not presented as saved` (line 498) and the F09-R3 reattach stop
   test; these must stay green unchanged — the fix must not clear the flag
   eagerly on success.

Suite gates: `./gradlew assembleDebug` and `./gradlew testDebugUnitTest` from
`android/src` (Studio JBR via `scripts/dev.sh` env). Read the suite result, not
the count: `ThreadToolsTest` fails intermittently in full-suite runs
(`android/CLAUDE.md`, *The project*), so a red line there is re-run before
being read as a regression.

Device check for the failure mode (network-class, the one reproducible from
`dev.sh` without server cooperation): `./scripts/dev.sh run`, start a long
generation, `./scripts/dev.sh net off`, tap Stop →
`composer_stop` renders disabled while the request is in flight, then the
error surfaces and the button becomes enabled again with the partial answer
intact; `./scripts/dev.sh net on`, tap Stop → the run is cancelled.
`dev.sh shot` the before/after states. A 503-class cancel failure is not
triggerable against a live dashboard (it answers 200 with `{"run": null}`) and
stays JVM-covered.

## 6. Files touched

| File | Change |
|---|---|
| `android/src/app/src/main/java/com/hpz/llmdockchat/feature/thread/ThreadViewModel.kt` | `stop()` failure branch delegates to a new private `restoreStop` that clears the marked run's `stopping` flag under the identity guard and shows the error. |
| `android/src/app/src/test/java/com/hpz/llmdockchat/feature/thread/ThreadViewModelTest.kt` | Regression tests 1 and 2 (F04-R6 section). |
| `android/src/app/src/test/java/com/hpz/llmdockchat/feature/thread/ThreadReattachTest.kt` | Late-failure test 3 (F09-R3 section). |

Not touched: `ComposerRow.kt` (`enabled = !stopping` is the right contract once
the state is honest), `ChatRepository.kt` (the 200-`{"run": null}`-is-success
semantics F04-R6 depends on are already its), `ThreadState.kt`, and
`android/docs/F04-chat-turn-and-streaming.md` — no requirement changes; this
makes the implementation match F04-R6 and R-B, not redefine it.

Delivery: branch from a fresh `main`, one commit, PR against `main`.
Issue #263's five acceptance criteria map to tests 1–3 and the existing
F04-R6/F09-R3 pins named above.
