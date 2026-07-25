# F09 · Run continuity and reattachment

**Mockup:** screens 08a (reattached) and 08b (offline) · **Depends on:** F04

The reason this is an app and not a bookmark. Runs live on the server:
lock the phone mid-answer, lose signal on the train, come back — the
reply finished without you.

---

## F09-R1 · Detect an in-flight run (Must)

Opening a conversation returns `active_run` when a run is queued or
running, and `last_run` for the most recent run whatever its status. The
conversation list carries `active_run` per row (F02-R3).

**Acceptance criteria**

- [ ] Opening a thread with a running turn shows it as generating
      immediately, before any stream data arrives.
- [ ] Opening a thread with no active run shows no generating state.

## F09-R2 · Reattach with replay (Must)

`GET /api/chat/runs/<run_id>/stream` subscribes to a live run and first
replays everything generated before the client subscribed, then continues
with the live tail. The frames are identical to a fresh send (F04), so
one reader handles both.

The replay buffer coalesces consecutive deltas, so a long answer arrives
as a few large chunks followed by live tokens — the app must handle that
without assuming one delta equals one token.

If the run has already reached a terminal status, the endpoint emits a
single `{"type":"run_status","status":"…"}` frame and closes. There is
nothing to replay; the saved content comes from refetching the
conversation.

**Acceptance criteria**

- [ ] Start a long turn, force-close the app, reopen the thread: the text
      generated while away is present, and generation continues live from
      where it is now.
- [ ] Reattaching to a finished run shows the complete saved answer
      (from the conversation payload), with no duplicated text.
- [ ] Reattaching twice in a row does not duplicate content.
- [ ] Reattaching to an unknown run id shows an error, not a hang.

## F09-R3 · Stop still works after reattaching (Must)

The reattached stream's first frame carries the run id, and Stop cancels
by conversation with `expected_run_id` (F04-R6), so a reattached client
can stop a run it did not start.

**Acceptance criteria**

- [ ] A turn started in the web UI can be stopped from the phone.
- [ ] A stale Stop — for a run that has already finished while a newer
      one started — does not kill the newer run.

## F09-R4 · Honest offline behaviour (Must)

When the network is gone the app says so. It retries with backoff, keeps
the draft, and never silently loses a message.

**Acceptance criteria**

- [ ] Airplane mode during a run shows a reconnecting state, then
      reattaches and catches up when the network returns.
- [ ] A send attempted with no network keeps the text in the composer and
      reports the failure.
- [ ] Backoff is bounded — the app does not hammer a dead server, and it
      does not give up permanently either.
- [ ] Nothing shows an answer as complete when the connection dropped
      mid-stream; the state is visibly "reconnecting", not "done".

## F09-R5 · Catch up on failure and completion missed while away (Must)

A run that completed, failed or was cancelled while the app was closed
must be reflected on reopening — including a failed run's error, carried
on `last_run`.

**Acceptance criteria**

- [ ] A turn that completed while the app was closed shows its answer on
      reopening.
- [ ] A turn that failed while the app was closed shows the error on
      reopening.
- [ ] A turn that was cancelled elsewhere shows the thread without a
      phantom generating state.

## F09-R6 · Notification when an answer lands (Dropped)

Screen 08b's central promise — a notification when a background run
finishes, or when a starting model becomes ready.

**This is dropped from v1.** There is no endpoint for it: nothing on the
dashboard notifies a client, and nothing lets a client register for
push. Delivering it would mean either new server code (a poll endpoint or
push registration) or a foreground service polling the conversation list —
which R-A excludes.

The mockup is explicit that this is "the killer feature and the biggest
single build item". It stays on the record in
[Dropped-Features.md](Dropped-Features.md) as the one thing worth
reopening once a server change is on the table.

**Acceptance criteria**

- [ ] The app posts no notifications and requests no notification
      permission in v1.
- [ ] The app runs no background or foreground service while closed.

---

## Endpoints used

| Method | Path |
|---|---|
| GET | `/api/chat/conversations/<id>` (`active_run`, `last_run`) |
| GET | `/api/chat/conversations` (`active_run` per row) |
| GET | `/api/chat/runs/<id>/stream` |
| GET | `/api/chat/runs/<id>` |
| POST | `/api/chat/conversations/<id>/cancel-active-run` |

## Deviations from the mockup

- **No notifications** — F09-R6 above.
- **No offline reading cache.** Screen 08b offers caching the last N
  threads for reading without a connection. Cut for v1; the web UI has no
  equivalent, and it introduces a second source of truth for message
  content.
- **Not "retrying every 5 s".** Screen 08b's offline banner promises a
  fixed interval. R4 asks for *bounded* backoff, which a fixed interval is
  not, so the delay doubles from 1 s to a ceiling of 8 s and stays there —
  see the second deviation below.

## Deviations found while implementing

- **The send path reconnects by reattaching too.** R4 reads as though
  offline recovery belongs to the reattach path, but a connection can
  equally drop half a second into a `POST …/messages` whose run is already
  executing. The retry is therefore *always*
  `GET /api/chat/runs/<id>/stream`, on every path, and the POST is never
  re-issued: the server would create a second run and persist a second
  copy of the user's message. Regression-tested (`a drop on the send path
  retries by reattaching, never by posting again`).
- **A stream that ends cleanly is never retried, and that is forced by the
  wire format.** `run_manager._sse_frames_for` maps `run_cancelled` to no
  frame at all, so a cancelled run and a completed one both close the
  stream in silence. There is nothing to tell them apart at the frame
  level, which means "the server closed it" has to be treated as "the run
  is over" — only a *thrown* connection error is retryable. What actually
  happened then comes from the refetch, exactly as Architecture D3 says.
- **Backoff is not F07's flat 2 s.** `ServicesStreamRepository` retries the
  services stream on a fixed 2 s delay; the chat reconnect doubles 1→2→4→8 s
  and holds at 8 s. The two cases differ in duration, not in kind: the
  services stream is scoped to a sheet that is open for seconds, whereas a
  thread can sit reconnecting for as long as the screen is, which is the
  case a flat delay handles badly. Schedule asserted in
  `ReconnectBackoffTest`.
- **Reattaching replays the run from its first token, every time.**
  Measured against the dashboard on 2026-07-25: two consecutive reattaches
  to one live run returned 8,168 and 12,304 characters, the second
  containing the first in full. So the accumulated turn is rebuilt per
  connection rather than appended to — the fixtures
  `sse/reattach-replay-first.sse` and `-second.sse` are those two
  captures, and the test that pins it fails with 20,472 characters against
  a client that accumulates across attempts.
- **R6's negative criteria hold and were checked, not assumed.** The
  manifest requests only `INTERNET` and `ACCESS_NETWORK_STATE`;
  `dumpsys activity services com.hpz.llmdockchat` reports "(nothing)" and
  `cmd notification list` shows no record owned by the package.

## Out of scope

- Any background execution. The app does nothing while it is closed.

## Verification notes

Every Must criterion was verified, most of them live against the
dashboard. The review could not refute one.

**The no-duplication rule is a single line.** `TurnAccumulator` is built
inside `collectAttempt`, per attempt. Every reattach replays the run from
its first token, so an accumulator shared across attempts appends the
replay to text it already has. Confirmed by hoisting it in review:
20,472 characters for a 12,304-character answer — the replayed prefix
appended to what was already on screen. The construction site carries a
comment naming the test that catches it, because the obvious
"optimisation" is to hoist it.

**A clean close is never retried.** `_sse_frames_for` maps
`run_cancelled` to nothing, so a cancelled run and a completed one close
*identically* and no frame distinguishes them. Only a thrown connection
error is retryable. This matters more than it looks: a spurious reattach
after Stop would resurrect a partial the server never saved (F04-R6 —
cancelled runs persist nothing). Confirmed in the dashboard log: one
`/stream` GET for a cancelled run and nothing after the cancel.

**Reconnecting while the run has already finished is honest, and
self-correcting.** Observed live — the run completed server-side while
the emulator was offline and the phone still said *Reconnecting*, because
it cannot know. On the network returning it recovered on its own in about
12 s: reattach → `run_status` → clean close → refetch → saved answer.
Honest *and* not stuck.

**Backoff** is 1→2→4→8 s capped, resetting only after an attempt that
delivered frames, deliberately diverging from F07's flat 2 s: F07's
stream lives for a sheet open for seconds, a thread can sit reconnecting
for as long as the screen is. Bounded, no stop sentinel, no attempt
limit. The overflow clamp and the zero-delay guard are both pinned by
tests seen to fail without them (`but was 0` — a hot loop, not a naming
accident).

**Outstanding**

| Item | Why |
|---|---|
| R5 · failed while away, live | Needs a container to die, which no agent here may cause. Covered by a JVM test over `conversation_failed_run.json`, whose error string is byte-identical to the f-string at `dashboard/chat/llm_proxy.py:89`. |
| R2 · unknown run id, live | Would mean inventing a run id, which is what the test does. Server shape confirmed by hand: `404 {"error":"Run not found"}`. |

**Owner line items — feel, not correctness**

- The amber "Reconnecting…" line can sit half-clipped behind the
  composer: it is trailing content on the streaming bubble, and no new
  content arrives to trigger the auto-scroll. It is the thing R4's fourth
  criterion is *seen* through, so it is worth a glance.
- Screen 08a's "Picked up where you left off" banner renders correctly
  but sits above the answer, so it is off-screen whenever the thread is
  following the tail. Whether it earns its place there is a judgement
  call.
