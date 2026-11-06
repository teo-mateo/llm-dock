# F17 · Pi sessions list

**Mockup:** `../../docs/pi-remote/mockups/Main.dc.html` · **Depends on:** F01 · **Data layer:** #354

The Pi tab is a read-only view of pi-remote sessions living on the dashboard. It lists sessions
without sending, steering, stopping or opening a transcript; those controls belong to later
features.

---

## F17-R1 · Pi tab and live session list (Must)

The app has a Pi tab whose list is fed by `GET /api/pi/sessions/stream`: a `snapshot` on connect,
then `session` deltas, and `lagged` when the dashboard drops the reader. Live sessions appear
first; ended sessions are shown below them.

**Acceptance criteria**

- [x] The Pi tab is reachable from the app's bottom navigation.
- [ ] The list matches the dashboard's pi sessions and updates without user action.
- [ ] Live sessions are ordered above ended sessions.

## F17-R2 · Row content and state (Must)

Each row shows a status chip and a text label — `working`, `idle` or `ended` — so state is never
colour-only. It shows the session name (falling back to the last path segment of `cwd`), `cwd`,
`model`, and `context_percent` when known.

**Acceptance criteria**

- [ ] A working session shows `working` and a warning-coloured chip.
- [ ] An idle live session shows `idle` and a success-coloured chip.
- [ ] An ended session shows `ended` and a muted chip.
- [ ] Name, `cwd`, model and context percentage are visible; an unnamed session falls back to its
      `cwd` basename.
- [ ] A missing model or context value is omitted, not rendered as a fake zero.

## F17-R3 · Ended sessions below (Must)

Ended sessions remain visible as history, below all live sessions, with the end reason when the
server supplies one. They are not mixed into the live list.

**Acceptance criteria**

- [ ] Ending a session moves it below the live rows without removing it.
- [ ] The row shows `ended · <end_reason>` when `end_reason` is present.

## F17-R4 · Reconnecting state (Must)

While the stream is down and the repository is retrying, the screen shows `reconnecting` rather
than going blank or freezing the last list. A successful reconnect replaces the list with the
new snapshot.

**Acceptance criteria**

- [x] Dropping the connection shows `reconnecting`.
- [ ] The last-known sessions stay on screen while reconnecting.
- [ ] The indicator clears when the reconnect succeeds.

---

## Data layer (implemented in #354)

`PiSessionsRepository.streamWithStatus()` reads the stream through `SseTransport`, maps each
session once at the wire/domain seam, and keeps the list sorted live-first then `lastSeen` desc.
`snapshot` replaces the list, `session` upserts by `PiSessionKey`, and `lagged` ends the current
connection and reconnects without the normal delay. Failures surface `stale = true` and retry
after the configured delay.

**Acceptance criteria**

- [x] Snapshot and session frames parse; malformed or unknown frames become `Unknown` without
      throwing.
- [x] Ended sessions map to `PiState.ENDED`; a live unknown/missing state maps to `IDLE`.
- [x] Snapshot replaces, session upserts, sort is live-first then `lastSeen` descending.
- [x] A failed connection marks the state stale and recovers on reconnect.
- [x] `lagged` reconnects without delay; cancellation is rethrown and not retried.

## Endpoints used

| Method | Path |
|---|---|
| GET | `/api/pi/sessions/stream` |

## Verification notes

Data layer: JVM tests `PiSessionsStreamEventTest`, `PiSessionMapperTest`, and
`PiSessionsRepositoryTest` pass; `assembleDebug` builds.

UI (#356): `PiSessionsViewModelTest` and `PiFormattingTest` pass; `assembleDebug` builds. Emulator
screenshot `../../docs/pi-remote/screenshots/f17-pi-tab.png` shows the Pi tab in the bottom bar,
title `pi sessions`, `0 live · 0 ended`, the `Reconnecting…` banner, and the empty state. The
dashboard endpoint was still 404 without a restart, so no live rows were available to verify;
the row content, split sections and ended-section criteria remain unchecked.
