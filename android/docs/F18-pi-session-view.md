# F18 · Pi session view

**Mockup:** `../../docs/pi-remote/mockups/PhoneSession.dc.html` · **Depends on:** F05, F17 · **Data layer:** #358

The session view is the read-only detail screen for one pi-remote session. It renders the
session header and the event transcript; it does not send, steer, stop or change a run. Those
controls belong to later features.

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

## Data layer (implemented in #358)

`PiSessionEventsRepository.stream(key)` reads `/api/pi/sessions/<session_id>/<instance_id>/stream`
through `SseTransport`, sending `after=<lastSeq>` on every connection. It parses total frames into
`PiSessionStreamEvent`, keeps a `PiSession` summary and ordered `PiEvent` list, merges only seqs
greater than the last held seq, reconnects immediately on `lagged`, marks failures stale and
retries, and stops with `unknown = true` on `404 unknown_session`.

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

JVM tests `PiSessionStreamEventTest` and `PiSessionEventsRepositoryTest` pass; `assembleDebug`
builds. No UI is implemented in #358, so F18-R1–R3 UI criteria remain unchecked.
