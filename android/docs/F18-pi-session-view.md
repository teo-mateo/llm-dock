# F18 · Pi session view

**Mockup:** `../../docs/pi-remote/mockups/PhoneSession.dc.html` · **Depends on:** F05, F17 · **Data layer:** #358 · **Transcript:** #360 · **UI:** #362

The session view is the read-only detail screen for one pi-remote session. It renders the
session header and the event transcript; it does not send, steer, stop or change a run. Those
controls belong to later features. The one control it does own is F18-R4, a display preference that
changes how answers are drawn and touches no run state.

---

## F18-R1 · Header (Must)

The header shows the session name, a text status (`working`, `idle` or `ended`), the model, and
the context percentage when the server supplies it. Missing model or context values are omitted,
not rendered as zeros.

**Acceptance criteria**

- [ ] The header renders name, state text, model and context percentage from the `session` frame.
- [ ] A missing model or context value is omitted.
- [ ] The header updates when a later `session` frame arrives.

## F18-R2 · Transcript (Must)

The transcript renders the session's events through the F05 rendering pieces, with a user bubble,
assistant output, thinking, tool calls and run-end notices. It follows the stream live and never
shows an editable composer in this phase.

**Acceptance criteria**

- [ ] Events render in ascending `seq` order through the F05 rendering pieces.
- [ ] The transcript is read-only: no message input, steering, stop or send control.
- [ ] New events appear without user action.

## F18-R3 · Resume and unknown session (Must)

The stream connects with `?after=<last seq>` (0 at first), reconnects from the last held seq
without gaps or duplicates, reconnects immediately on `lagged`, and stops with a "no longer
known" state on `404 unknown_session`. Failures keep the last-known transcript visible while
retrying.

**Acceptance criteria**

- [ ] The first connect sends `after=0`; every reconnect sends `after=<last held seq>`.
- [ ] Duplicate and older seqs are dropped and events stay ascending.
- [ ] `lagged` reconnects without the normal delay.
- [ ] `404 unknown_session` sets `unknown` and stops; the UI shows "no longer known".
- [ ] A failure marks the state stale, keeps the last-known transcript, and recovers on retry.
- [ ] Cancellation is rethrown and not retried.

---

## F18-R4 · Response text size (Must)

The session screen header carries an `Aa` button that opens a settings sheet — the same interaction
as the chat thread's cog — offering pi answers only, from 70% to 140% in 10% steps, with the current
percentage shown and a `Reset` that returns it to 100%. The sheet has no dismiss button: it closes on
scrim tap, drag or back, like any modal bottom sheet. The choice is stored on the device, under the
DataStore key `pi_response_text_scale`, applied immediately to every answer on screen, and re-applied
after navigation or a restart. Chrome — header, chips, list rows, composer — keeps the system text
size.

**Acceptance criteria**

- [ ] `Aa` in the session header opens the sheet; it closes on scrim, drag or back with no dismiss
      button of its own, and sizes below 100% are offered.
- [ ] Stepping re-renders the answers on screen with no navigation, reload or restart.
- [ ] The bar reports the current size as a whole percentage and offers `Reset` only when it is not
      100%.
- [ ] The value survives navigating away and back, and a process restart.
- [ ] Header, composer and control bounds are identical at every size; answer text scrolls and clips
      normally instead of overflowing.

---

## Data layer (implemented in #358)

`PiSessionEventsRepository.stream(key)` reads `/api/pi/sessions/<session_id>/<instance_id>/stream`
through `SseTransport`, sending `after=<lastSeq>` on every connection. The optional named `after`
seed follows the existing positional reconnect-delay argument. It parses frames into
`PiSessionStreamEvent` and emits lossless fresh `appended` batches with `lastSeq`, summary and
status, without retaining raw history. Summary/stale emissions have empty batches. Incoming
seqs are sorted, deduplicated and filtered above the accepted cursor; seqs need not be contiguous.
`lagged` reconnects immediately without advancing beyond accepted events. Failures mark stale
and retry; `404 unknown_session` or a matching `session_removed` frame terminates as Unknown.

The transcript rules are shared with the web client: `dashboard/frontend/src/utils/piTranscript.js`
and Android `feature/pi/transcript/PiTranscript.kt` implement the same rules, item kinds and ids.
Android `PiTranscriptTest` ports the web suite's 14 cases one to one and adds malformed-payload
coverage. The same `TranscriptBuilder` now supports incremental application and checkpoint
continuation: items, working state and an explicit open assistant id, including when notices
trail that assistant. Restore rebuilds mappings for all tools, with the latest repeated call id
winning. Published snapshots are not mutated by later updates. The ViewModel owns one builder
on an injected worker dispatcher and reuses the transcript on metadata/stale updates. No disk
cache is enabled.

### Preparatory checkpoint storage

`PiSessionSnapshot` / `PiSnapshotCodec` serialize those existing render models and the summary,
with a required codec/reducer version, canonical server identity, session/instance key,
`firstSeen`, accepted cursor and save timestamp. Payload identity and summary identity must
agree; invalid versions, continuations or content are misses. The summary is display data,
not current command authorization or liveness.

`PiSessionSnapshotStore` is not wired into the application yet. Its eventual owner must pass
`cacheDir/pi-sessions/`, one store instance per directory and an app-lived coroutine scope.
There is no separate encryption claim. SHA-256 filenames hash the serialized identity tuple,
not user-authored path segments. Gzip input is bounded by the 64 MiB compressed-file/committed
budget and 8 MiB decompressed JSON limit; output encoding is also bounded. Atomic same-directory
replacement preserves the old target until commit; startup removes only owned orphan temps.

The store keeps at most eight committed entries. Successful reads and commits update file
modification time using the injected clock; that persisted access time drives LRU, with hash
filename as a deterministic tie-breaker. Save timestamps remain diagnostic payload fields.
Entry count and compressed-byte quotas are enforced before replacement.

One IO worker retains at most eight latest pending checkpoints (one per key), plus its single
in-flight write. A full queue rejects a new key but still accepts replacement for an existing
pending key. `enqueue` returns a deferred outcome: stored, skipped, superseded, invalidated,
queue-full or an explicit IO failure. Callers capture a generation before scheduling work;
`delete` and `clear` invalidate it before disk removal, including queued/in-flight writes.
`invalidate` rejects unfinished work without deleting committed files, supporting the approved
retention policy when lifecycle wiring is added. No sign-out, restore, throttling or UI wiring
is enabled by this storage-only change.

**Acceptance criteria**

- [x] `PiSessionStreamEventTest` covers events order, session, lagged after, unknown type and
      malformed JSON.
- [x] `PiSessionEventsRepositoryTest` covers first `after=0`, reconnect from last seq, duplicate
      and older seq dropping, summary updates, immediate `lagged` reconnect, 404 stop, stale
      recovery, and cancellation not retried.
- [x] New Kotlin files have no comments; no dependency added.

## Endpoints used

| Method | Path |
|---|---|
| GET | `/api/pi/sessions/<session_id>/<instance_id>/stream?after=<seq>` |

## Verification notes

Data layer and transcript: JVM tests `PiSessionStreamEventTest`, `PiSessionEventsRepositoryTest` and
`PiTranscriptTest` cover the original stream/reducer contracts. `PiTranscriptContinuationTest`
checks every fixture split, trailing notices, tool restoration, invalid continuations and prior
snapshot stability. `PiSessionEventBatchesTest` covers seeded replay, slow collectors, accepted
cursors, terminal removal/404 and cancellation. `PiSessionIncrementalTest` checks queued worker
execution, exact incremental output, metadata/stale snapshot reuse, cancellation and removal.
`PiSnapshotCodecTest`, `PiSessionSnapshotStoreTest`, `PiSnapshotEvictionTest` and
`PiSnapshotWriterTest` cover roundtrips, exact byte boundaries, malformed/oversized files,
interrupted replacement, access eviction, bounded coalescing and deterministic generation races
using temporary directories and injected IO/time. The issues' Android JVM/build gates are
recorded in their PRs.

UI (#362): `PiSessionViewModelTest` covers loading, first transcript, Unknown, stale and idempotent
start; `PiFormattingTest` covers `shouldFollow`; `PiSessionDestinationTest` covers encoded route
segments. The screen is read-only: no composer, Stop or steering control; `MarkdownBody` and the
now-`internal` thread `ReasoningBlock` are reused.

Emulator check: the dashboard still answers `/api/pi/...` with 404 (no `llm-dock.service`
restart), so no live session or session-screen screenshot was possible. The Pi tab screenshot
`../../docs/pi-remote/screenshots/f18-pi-tab.png` shows the tab and empty/reconnecting state; the
PO performs the live session check with the owner. No UI criteria are claimed as device-verified.
