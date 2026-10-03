# Thread edit mode survives reload and process restoration (issue 271)

**Issue:** #271 `[Android][P2] Reloading a thread drops edit mode and turns the edited message into a new-message draft`
**Baseline:** issue reports `main` at `415c0cc`; this plan was written against `main` at `c404ca6` — the code paths it cites are unchanged between the two.
**Owner surfaces:** Android app only (`android/`). No dashboard change; no new endpoint (Plan_TOC rule R-A holds).

Every file:line below was read in the working tree at the stated revision. No builds or
test runs were performed for this plan — §6 lists what must be run.

---

## 1. Problem statement

Edit-and-resend (F06-R3) is a destructive, confirm-gated action: Send while
`editingMessage != null` opens a discard-count dialog instead of posting
(`android/src/app/src/main/java/com/hpz/llmdockchat/feature/thread/ThreadScreen.kt:277-281`).
A thread reload — which happens on every rotation, every return to the destination,
and every error retry — rebuilds the UI state from a fresh server load, and the rebuild
drops the edit identity while keeping the edited text in the composer:

```text
REVIEW_EDIT_RELOAD: editingMessage=null, composer=What is a transistor?
```

The user is now, without any signal, holding the old message's text as a plain
new-message draft. One tap sends it as a brand-new turn — the exact outcome the
F06-R3 confirmation exists to prevent — and Cancel can't rescue them because the
pre-edit draft it would restore is no longer reachable.

**Acceptance criteria from the issue** (all six are addressed; mapping in §6):

- Rotation while editing retains Edit mode and the edited text.
- Send still opens the edit/discard confirmation and updates the original message.
- Cancel restores the pre-edit text and attachments.
- Reloading cannot silently turn an edit into a new send.
- A deleted edit target produces clear feedback and preserves user-entered text.
- Process restoration has an explicit, tested recovery behavior.

**Decision — restore, don't discard.** The issue offers "preserve across reload" or
"cleanly discard with a notice". Criteria 1–3 require preservation for reload and
recreation, so restoration is the design; the discard-with-notice shape is reserved
for the one case where restoration is impossible — the edit target no longer exists
server-side (§4.3). For process death (criterion 6) the plan implements the issue's
first alternative, "store sufficient saved state", with a minimal text-only record;
the fallback when restoration is impossible is the same explicit notice.

## 2. Root cause

### 2.1 The clobber: `loadedFrom` whitelists fields instead of preserving overlay state

Rotation recreates the Activity and the NavHost, and `ThreadScreen` re-enters:

- `ThreadScreen.kt:105` — `LaunchedEffect(Unit) { viewModel.load() }` fires on every
  fresh composition of the destination.
- The ViewModel survives the recreation (it is keyed `"thread_$conversationId"` on the
  navigation entry's store, `navigation/AppNavHost.kt:267-295`), so the edit state
  exists in memory right up to the moment `load()` replaces it.
- `feature/thread/ThreadViewModel.kt:88` — a successful load sets the whole state with
  `loadedFrom(conversation, draft, staged)`.

`loadedFrom` (`ThreadViewModel.kt:121-139`) constructs a **brand-new**
`ThreadUiState.Loaded` and carries across an explicit list: `composer`, `attachments`,
`sending`, `actionError`, the streaming turn, ladders. Everything not named reverts to
the data-class defaults (`feature/thread/ThreadState.kt:81-83`): `editingMessage`,
`pendingEdit`, `pendingDelete` all become `null`. That is the drop.

The symptom is precisely the shape of the whitelist: `composer` **is** carried
(`ThreadViewModel.kt:133`), `editingMessage` **is not** — so the edited text survives
its own edit mode and outlives it as a new-message draft, and the Send action's branch
on `it.editingMessage != null` (`ThreadScreen.kt:280`) now takes the `onSend()` arm.

### 2.2 The orphaned snapshot: why Cancel can't recover

`beginEdit` (`ThreadViewModel.kt:450-463`) snapshots the pre-edit composer and
attachments into private ViewModel fields (`ThreadViewModel.kt:77-78`). Those fields
outlive the reload — but their only reader is `cancelEdit`, which bails when
`editingMessage == null` (`ThreadViewModel.kt:467`). After §2.1 the snapshot is alive
and unreachable: the pre-edit draft is gone from the UI with no way back except
retyping.

### 2.3 The second instance: process death has no edit state at all

The `ThreadViewModel` factory (`AppNavHost.kt:273-289`) takes no `SavedStateHandle`, so
a cold restore builds a virgin ViewModel and loads from disk. The edit text is on disk:
`onComposerChange` persists every keystroke through `DraftStore`
(`ThreadViewModel.kt:225-229`), so after process death the thread reopens with the
edited text sitting in the composer as an ordinary draft and no edit banner — the same
silent edit→new-send conversion, from the persistence layer this time. This is also the
state a failed-reauth Connect round trip restores into, since that teardown destroys
the destination and its ViewModel outright (the rationale in
`core/prefs/DraftStore.kt:12-22`). Criterion 6 makes this path in scope, not a
theoretical one.

### 2.4 The near-miss: `reloadConversation` preserves but never reconciles

The incremental refresh path `reloadConversation()` (`ThreadViewModel.kt:275-285`)
uses `current.copy(...)` and so *keeps* the edit fields — but it never checks the fresh
message list against the target. A message deleted elsewhere (the web UI shares
`chat.db`; Plan_TOC R-B makes divergence expected) leaves `editingMessage` /
`pendingEdit` pointing at a row that no longer exists, and `confirmEdit` would PUT to
a dead message id (`ThreadViewModel.kt:516`). The fix in §4.2 closes both this and the
issue's "deleted edit target" criterion with one reconcile function.

## 3. Design

Preserve the edit session — its target, its text, its pre-edit context — across every
reload and restoration path, reconciled against the fresh server state by message id.
Three pieces:

| # | Piece | Where |
|---|---|---|
| 3.1 | An `EditStateStore` persistence seam (sibling of `DraftStore`) | new `core/prefs/EditStateStore.kt`, `AppContainer`, `AppNavHost` |
| 3.2 | One id-reconcile of edit state, applied by both reload paths | `ThreadViewModel.loadedFrom`, `reloadConversation` |
| 3.3 | Record written on `beginEdit`, cleared on `cancelEdit`/`confirmEdit`; replayed by `load()` | `ThreadViewModel` |

No new screen, no wire-format change, no endpoint change.

### 3.1 The persisted edit record

```kotlin
// core/prefs/EditStateStore.kt
interface EditStateStore {
    suspend fun record(conversationId: String): EditSession?
    fun save(conversationId: String, session: EditSession)
    fun clear(conversationId: String)
}

@Serializable
data class EditSession(val messageId: String, val composerBeforeEdit: String)
```

`DataStoreEditStateStore` implements it exactly as `DataStoreDraftStore` does
(`core/prefs/DraftStore.kt:31-66`): one preferences key (`"edit_drafts"`) holding a
JSON map `{conversationId -> EditSession}`, via the existing `ValuePreference`, capped
like drafts. The record is two strings per conversation — the target id and the
pre-edit draft — deliberately excluding attachments: image data URLs are
multi-megabyte, DataStore preferences is the wrong home for them, and picked draft
attachments do not survive process death anywhere in this app today (`addAttachment`,
`ThreadViewModel.kt:287-290`, is memory-only; only the F14 share flow persists
attachments, to cache files — `SharedDraftStore`). A restored edit therefore re-derives
attachments from the fresh message row, exactly as `beginEdit` does
(`ThreadViewModel.kt:459`). This is a documented, tested limitation, not an oversight.

Two fields, and why each is required and not derivable:

- `messageId` — the identity the whole design reconciles on. In memory this is
  `editingMessage.id`; in the record it is the only piece not recoverable from disk.
- `composerBeforeEdit` — the Cancel target. In memory it is the private var at
  `ThreadViewModel.kt:77`, which the record must mirror for the process-death path.

The edit text itself needs no separate field because §3.3 keeps `DraftStore` equal to
the live composer while editing — the draft half of a share already works this way
(`SharedDraftStore.reassign`).

### 3.2 One reconcile, used by every server reload

New private function on `ThreadViewModel`, called by `loadedFrom` and by
`reloadConversation`:

```kotlin
private fun reconcileEdit(
    current: ThreadUiState.Loaded?,
    conversation: ConversationDetail,
): ReconciledEdit
```

Behavior:

1. **Not editing** (`current?.editingMessage == null`) → pass through `null/null`.
   Nothing is added that wasn't there before; the F06 happy paths are untouched.
2. **Target present** — `conversation.messages.firstOrNull { it.id == editing.id }`
   finds the row and its role is `USER`:
   - `editingMessage` := the **fresh** row (the server copy — so a message edited from
     the web changes content but keeps its id, and the resend still targets the same
     original, criterion 4 / issue step 4).
   - `pendingEdit` (confirmation open across the reload) := preserved, rebound to the
     fresh row with `discardCount` recomputed from the fresh message list — the dialog
     must never state a stale number next to a destructive action.
   - composer and attachments are left alone: the user's in-progress text wins.
   - The persisted record stays (still the same target).
3. **Target gone or turned into a non-user row** → explicit discard:
   - `editingMessage = null`, `pendingEdit = null`, record cleared.
   - **Text preservation, the rule:** if `composerBeforeEdit` is non-blank it is
     restored to the composer and to `DraftStore` (mirroring `cancelEdit`'s
     `ThreadViewModel.kt:471-474`); if blank, the edit text stays in the composer as a
     plainly-labelled new-message draft. Either way, text the user typed is never
     dropped — this is what "preserves user-entered text" means operationally, and the
     difference between the two arms is which one is still recoverable through the
     normal draft machinery.
   - Visible feedback through the existing snackbar channel (`actionError` →
     `ThreadScreen.kt:209-214`), phrased so the state is unmistakable:
     *"The message you were editing is no longer in this conversation. Edit cancelled —
     your text is kept."* This is the issue's own discard-with-notice shape, scoped to
     the one case where keeping the edit is impossible.

`pendingDelete` gets the same presence check (keep the confirm dialog if the row is
still there, drop it silently otherwise — a vanished delete target is self-cancelling
and the dialog itself is the feedback). Model picker, settings sheet and reasoning
picker are **not** preserved: they are transient sheets that reload-on-open anyway,
`load()` only fires when no sheet can be open, and widening the whitelist has no
criterion behind it. Deliberate exclusion, stated so it isn't "fixed" later.

### 3.3 The edit session lifecycle in `ThreadViewModel`

- `beginEdit` — after the existing guards: write the record
  `{messageId = message.id, composerBeforeEdit = current.composer}` and
  `drafts.save(conversationId, message.content)`. The second line is what keeps the
  §3.1 invariant true — while an edit is open, `DraftStore` always mirrors the live
  composer — so every restoration path reads the same text the user was looking at.
- `onComposerChange` — unchanged. Its existing `drafts.save` is the mirror.
- `cancelEdit` / `confirmEdit` — `editStates.clear(conversationId)` alongside the
  existing state clear (`confirmEdit` clears at entry, like its `drafts.clear` at
  `ThreadViewModel.kt:513`; a later 409 rollback needs no re-write, because the edit
  it rolls back is already finished — criterion: *cancel makes no request* stays true,
  the store is local).
- `load()` — after `loadedFrom` has run the in-memory reconcile (§3.2), if there is
  still no `editingMessage` but a record exists for this conversation, attempt
  restoration: target present in the fresh list and `USER` → re-enter edit
  (`editingMessage` = fresh row, `composer` = draft mirror, `attachments` = fresh row's
  images, `composerBeforeEdit`/`attachmentsBeforeEdit` vars repopulated from
  record — attachments only from the fresh row). Target absent → run the discard arm
  of §3.2 (notice + the text rule). The 401-destroys-destination case and process
  death both land on exactly this line, which is what makes criterion 6 one behavior,
  not two.
- `fireAutoSend` (`ThreadViewModel.kt:112-119`) — F14-R7's owed turn wins: before
  sending, clear any restored edit state and the record. A claim spends the composer;
  leaving an edit banner over a now-empty composer would be a new inconsistency, and
  "exactly one turn" outranks an interrupted edit. Tested so the priority is pinned.

Constructor gains `editStates: EditStateStore? = null`, optional in the style of
`attachmentStore` (`ThreadViewModel.kt:44`) so existing callers, previews and every
other test compile untouched. `AppContainer` builds it next to `draftStore`
(`core/AppContainer.kt:131`) from the same `DataStore<Preferences>` and `appScope`;
`AppNavHost` passes it in the thread factory.

### 3.4 What `loadedFrom` becomes

The whitelist gains the reconciled trio — the root cause is a missing field set, so
the shape fix is small and mechanical:

```kotlin
val edit = reconcileEdit(current, conversation)
return ThreadUiState.Loaded(
    conversation = conversation,
    thread = ThreadState(
        messages = conversation.messages,
        streaming = current?.thread?.streaming?.takeUnless { it.unconfirmed },
    ),
    composer = edit.composer,
    attachments = edit.attachments + staged distinct,
    sending = current?.sending ?: false,
    actionError = current?.actionError ?: edit.cancelNotice,
    pendingDelete = current?.pendingDelete?.takeIf { id still in conversation.messages },
    editingMessage = edit.message,
    pendingEdit = edit.pendingEdit,
    laddersByService = mergedLadders,
)
```

(`reloadConversation` applies the same `ReconciledEdit` to its `copy`.) No Compose
change: the "Editing message" banner (`ThreadScreen.kt:878-898`) and the confirm dialog
(`ThreadScreen.kt:326-347`) are pure functions of the preserved state fields.

## 4. Edge cases

| Case | Behavior | Why |
|---|---|---|
| Target's **content** changed on the web between reloads | Edit continues against the fresh row (id stable); confirm shows recomputed discard count; PUT targets the same id | The server truncates from the row's position and keys by id; the original message is still the original |
| Target deleted (web UI, other phone) | Explicit cancel, visible notice, text rule (§3.2) | The one genuinely unrecoverable case — and the acceptance criterion that demands feedback, not silence |
| Pre-edit draft blank, target deleted | Edit text remains in composer as a labeled draft + notice | Never silently; never loses typed text |
| Confirmation dialog open during reload/recreation | `pendingEdit` preserved, count recomputed; Confirm updates the same original | Criterion 4; F00-R9 confirm discipline |
| Reload while a run became active server-side | `runActive` gates composer and Send (existing `canSend`/menu guards); edit state itself preserved, the stale-confirm path keeps relying on the server's 409 rollback (`ThreadMessageActionsTest`, pre-existing design) | Pre-existing gap untouched — out of scope, recorded so the next reader doesn't mistake it for this fix's |
| Process death mid-edit | §3.3 `load()` restoration (edit re-enters), or discard-notice if the target vanished | Criterion 6 |
| Force-stop before typing during an edit | `beginEdit`'s draft save means the mirror holds the message text; restore re-enters edit with it | The invariant, not a special case |
| Process death mid-edit, target then deleted + pre-edit draft existed | Record restores `composerBeforeEdit` (the draft it clobbered at begin time), notice shown | The record is the only place the pre-edit draft survives — §3.1's second field |
| Restored edit + F14-R7 auto-send claim both pending | Auto-send wins, edit + record cleared before the claim is taken | F14-R7's exactly-one-turn contract |
| Two overlapping `load()`s (retry + return) | Idempotent: second reconcile preserves the first's preserved state | All paths are pure over `_state.value` |
| Draft text blank on restore | `DraftStore.save`/`DataStoreDraftStore` blank-clear (`DraftStore.kt:57`); `beginEdit`'s mirror re-saves on Cancel | Pre-edit blank stays blank |
| Stale record for a message that was never a user row | Reconcile rejects non-`USER` targets (mirrors `beginEdit`'s guard, `ThreadViewModel.kt:451`) → discard arm | Defense in depth for records written by an older build |
| Record cleared but process dies inside `confirmEdit`'s optimistic window | No edit state, no banner; the run either lands or the existing 409/refetch rollback repaints the thread | The edit had already been sent; nothing left to preserve |

## 5. Files to touch

| File | Change |
|---|---|
| `android/src/app/src/main/java/com/hpz/llmdockchat/feature/thread/ThreadViewModel.kt` | `reconcileEdit` + `ReconciledEdit`; preserve trio in `loadedFrom`; reconcile in `reloadConversation`; `editStates` param; record write in `beginEdit`; clear in `cancelEdit`/`confirmEdit`; restore in `load()`; auto-send precedence |
| `android/src/app/src/main/java/com/hpz/llmdockchat/core/prefs/EditStateStore.kt` (new) | `EditSession`, `EditStateStore`, `DataStoreEditStateStore` (mirrors `DataStoreDraftStore`) |
| `android/src/app/src/main/java/com/hpz/llmdockchat/core/AppContainer.kt` | build `editStateStore` beside `draftStore` (`:131`) |
| `android/src/app/src/main/java/com/hpz/llmdockchat/navigation/AppNavHost.kt` | pass `editStates` in the thread factory (`:267-295`) |
| `android/src/app/src/test/java/com/hpz/llmdockchat/testing/Fakes.kt` | `FakeEditStateStore` (next to `FakeDraftStore`, `:114`) |
| `android/src/app/src/test/java/com/hpz/llmdockchat/feature/thread/ThreadEditReloadTest.kt` (new) | §6 tests, reusing the `ThreadMessageActionsTest` harness |
| `android/src/app/src/test/resources/fixtures/conversation_multi_turn_no_m1.json` (new) | the multi-turn fixture minus the edited first user turn |
| `android/docs/F06-message-actions.md` | one F06-R3 acceptance line: edit mode survives rotation/reload; vanished target cancels with a visible notice (Plan_TOC §3 — the plan must describe what the app does) |

Per root-AGENTS *Scope of Changes*: bug-fix commit only — no reformat, re-quote or
restyle of untouched lines. New branch from a fresh `main`.

## 6. Test plan

JVM suite — new `ThreadEditReloadTest` on the `ThreadMessageActionsTest` harness
(MockWebServer for JSON, `FakeSseTransport`, `FakeDraftStore`, `FakeEditStateStore`,
`coalesceWindowMs = 0`), one test per criterion plus the guards:

1. **`rotation reload keeps edit mode and the edited text`** — load, `onComposerChange("a half-written question")`, `beginEdit(m1)`, `onComposerChange("What is a diode?")`, enqueue the fixture again, `load()`. Assert `editingMessage.id == "m1"` and `composer == "What is a diode?"`. This is the issue's probe (`REVIEW_EDIT_RELOAD`) inverted: it pins the exact observed regression. → criteria 1, 4.
2. **`send after reload still opens the discard confirmation on the same message`** — continue test 1 with `requestEditConfirm()`; assert `pendingEdit.message.id == "m1"`, `discardCount == 3` (the four-message fixture, edited first turn), and Confirm issues `PUT .../messages/m1` on the transport. → criteria 2, 4.
3. **`cancel after reload restores the pre-edit draft`** — continue test 1 with `cancelEdit()`; assert composer `"a half-written question"` and `drafts.saved` agrees. → criterion 3.
4. **`confirmation open across a reload survives, with the count recomputed`** — open confirm (count 3), reload with `conversation_multi_turn_after_delete.json` (three messages), assert `pendingEdit` non-null and `discardCount == 2`. → criterion 2; F00-R9.
5. **`a reload that drops the target cancels the edit with a notice and restores the prior draft`** — second load serves `conversation_multi_turn_no_m1.json`; assert `editingMessage == null`, `pendingEdit == null`, composer is the pre-edit draft, `actionError` carries the notice, and `drafts` was rewritten (not left holding the edit text). → criterion 5.
6. **`a dropped target with no prior draft keeps the typed edit text`** — same, no pre-edit draft; assert the edited text remains in the composer and the notice fires. → criterion 5.
7. **`a message edited on the web keeps the same original target`** — second load serves a variant where m1's content differs; assert `editingMessage.content` is the fresh copy, id unchanged. → issue step 4.
8. **`process restore re-enters the edit`** — a fresh `ViewModelStore` + second `ThreadViewModel` over the same fakes (mirrors cold restore), record `{m1, pre-edit draft}` and draft `"What is a diode?"` in place; `load()` → `editingMessage.id == "m1"`, composer is the edit text; `cancelEdit()` → the record's `composerBeforeEdit` returns. → criterion 6.
9. **`process restore with a deleted target discards with the notice and keeps text`** — same, served `conversation_multi_turn_no_m1.json`; assert the notice, null edit state, and the text rule. → criteria 5, 6.
10. **`beginEdit records, cancelEdit and confirmEdit clear`** — assert `FakeEditStateStore` contents at each transition, and that cancel still issues **no** HTTP request (F06-R3's "sends no request" criterion, now including the local write).
11. **`the delete confirmation survives a reload while its message exists`** — and is dropped, silently, when it does not. Secondary, same family.
12. **`an auto-send claim overrides a restored edit`** — F14-R7: staged claim + restored record → `load()` sends the claim, no edit banner, record cleared.

Regression: the whole existing suite stays green — `./gradlew testDebugUnitTest`
(reported as 599 passing at the issue baseline), read rather than counted
(`android/CLAUDE.md`: `ThreadToolsTest` is a known intermittent), plus
`assembleDebug` and lint clean.

Device pass (the Android bar: device criteria need a screenshot or instrumented
evidence): on `emulator-5554`, open a multi-turn thread, start an edit, type; rotate
(`user_rotation`) → screenshot shows the "Editing message" banner and the typed text;
tap Send → discard-count dialog; rotate again with the dialog open → dialog still
open; Cancel → banner gone, pre-edit draft back; `dev.sh shot` captures at each stop.
Then force-stop the app mid-edit and relaunch → the same banner is back.

## 7. Risks and open items

- **The whitelist stays fragile.** This bug is `loadedFrom` naming a field list; the
  fix grows the list. A durable guard would build the next state from
  `current.copy(...)` instead, but a refresh must be able to *reset* transient
  overlays (sheets) and a full `Loaded(…)` literal is the honest place to say which
  ones survive — hence the explicit trio + a test per preserved field. Recorded as
  the deliberate shape, not an unfinished refactor.
- **Attachments on the restore path** re-derive from the fresh row, so a multi-image
  message restored after process death shows the message's images, not any draft
  images picked before the edit began. Consistent with today's non-persistence of
  picked draft attachments; revisit only if `DraftStore` gains an attachment half.
- **`requestEditConfirm`/`confirmEdit` have no `runActive` guard** (`ThreadViewModel.kt:477-520`);
  the server's 409 + refetch rollback is the existing answer, and this change neither
  strengthens nor weakens it.
- If any behavior above needs a server change to hold, it is a spec bug per
  `android/CLAUDE.md` ("stop rather than grind") — none is expected: everything is
  client-state work over the existing `GET /api/chat/conversations/<id>` payload.
