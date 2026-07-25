# F04 · Sending a turn and streaming the reply

**Mockup:** screens 04 (streaming) and 06a (composer) · **Depends on:** F01, F03 · **Blocks:** F05, F06, F09

The heart of the app. A user message goes up, an answer streams back
token by token, and the run survives whatever the phone does next.

---

## The wire format

Three endpoints produce the same stream: `POST …/messages`,
`PUT …/messages/<id>` (edit + re-run) and `GET /api/chat/runs/<id>/stream`
(reattach). One reader serves all three.

| Frame | Shape | Meaning |
|---|---|---|
| run started | `{"type":"run_started","run_id":"…"}` | Always the first frame, even while the run is still queued. Capture `run_id` — Stop needs it. |
| delta | a raw OpenAI-compatible chunk — **no `type` key** | Text. Read `choices[0].delta.content` and `.reasoning_content` (some models use `.reasoning`). |
| tool call pending | `{"type":"tool_call_pending","index":n,"name":"…"}` | The model has started emitting a tool call; the name is known, arguments are not. |
| tool call | `{"type":"tool_call","name","arguments","server_id"}` | The full call, about to execute. |
| tool result | `{"type":"tool_result","name","result","server_id"}` | What came back. |
| artifact | `{"type":"artifact","artifact_type","title","content"}` | `artifact_type` is `svg`, `image`, `html` or `code`. See F05. |
| parse warning | `{"type":"parse_warning", …}` | The model emitted a malformed tool call. |
| heartbeat | `{"type":"heartbeat","elapsed_s":n}` | Liveness during slow generation. Not content. |
| done | `data: [DONE]` | Model output is finished. **Does not end the stream.** |
| message saved | `{"type":"message_saved","message_id","seq"}` | The assistant turn is durable. Follows `[DONE]`. |
| conversation updated | `{"type":"conversation_updated","id","title"}` | Auto-title, after the first turn. Can arrive *after* `message_saved`. |
| error | `{"error":"…"}` — **no `type` key** | The run failed. |
| run status | `{"type":"run_status","status":"…"}` | Reattach to an already-finished run. |

A cancelled run emits **no terminal frame** — the stream simply ends.

---

## F04-R1 · Composer (Must)

A multi-line input that grows to roughly five lines and then scrolls.
Enter inserts a newline; the send button sends — the opposite of the
desktop, because thumbs.

**Acceptance criteria**

- [ ] Enter inserts a newline and never sends.
- [ ] The field grows with content up to its cap, then scrolls internally
      without pushing the thread off screen.
- [ ] Send is disabled when the message is empty and has no attachments.
- [ ] The draft survives rotation, backgrounding and a 401 round-trip
      (F00-R3).

## F04-R2 · Send a turn (Must)

`POST /api/chat/conversations/<id>/messages` with `{content, images}`.
The user's message appears immediately; the response body is the SSE
stream for the run it started.

The server enforces one active run per conversation: a second send while
one is running returns **409** and rolls the user message back.

**Acceptance criteria**

- [ ] The user's message renders before the first token arrives.
- [ ] Send is unavailable while a run is active in this thread.
- [ ] A 409 shows the server's message and does not leave a phantom user
      message in the thread.
- [ ] A request that fails to connect at all keeps the text in the
      composer rather than losing it.

## F04-R3 · Streaming text (Must)

Content deltas append to the assistant message as they arrive. The thread
follows the tail while the user is at the bottom, and stops following the
moment they scroll up.

**Acceptance criteria**

- [ ] Text appears progressively, not in one jump at the end.
- [ ] Scrolling up during generation stops auto-scroll; a control returns
      to the tail.
- [ ] The model name is visible while the answer streams, so it is always
      clear who is answering.
- [ ] A long answer (thousands of tokens) does not degrade scrolling.

## F04-R4 · Reasoning (Should)

Models that emit `reasoning_content` get a collapsed block above the
answer, expandable on tap. Collapsed by default.

**Acceptance criteria**

- [ ] A thinking model shows a reasoning block that expands and collapses.
- [ ] Reasoning is never mixed into the answer body.
- [ ] A model that emits no reasoning shows no empty block.
- [ ] Reasoning persisted with a message (`reasoning_content` on load) is
      shown the same way as reasoning received live.

## F04-R5 · Tool calls (Should)

Each tool call renders as a one-line card — server and tool name —
expandable to arguments and result. `tool_call_pending` shows the name
before the arguments finish arriving.

**Acceptance criteria**

- [ ] A tool call shows as a single line while running and updates in
      place when its result arrives.
- [ ] Expanding shows arguments and result.
- [ ] Several calls in one turn render in order without collapsing into
      each other.
- [ ] A `parse_warning` frame is surfaced as a visible warning on that
      turn — quietly, not as a modal.

## F04-R6 · Stop (Must)

A Stop control while a run is active, calling
`POST /api/chat/conversations/<id>/cancel-active-run` with
`{"expected_run_id": "<id from run_started>"}`.

Cancel by conversation, not by run id: the server always knows the
conversation's active run, so Stop works even if the client never
captured the run id. `expected_run_id` prevents a stale Stop from killing
a newer run.

**Important:** a cancelled run does **not** persist its partial answer.
The text on screen is client-side only; on the next load of that thread
it is gone. This matches the web UI. The app must not imply the partial
was saved.

**Acceptance criteria**

- [ ] Stop halts generation within a second or two (cancellation is
      cooperative — polled between stream events, not forced).
- [ ] Stopping a run that already finished is a harmless no-op, not an
      error.
- [ ] After Stop, the thread shows the user's message; the partial answer
      is not presented as a saved assistant turn.
- [ ] Reopening the thread after a Stop shows the server's state and does
      not resurrect the partial.

## F04-R7 · Completion and title (Must)

On `message_saved`, the streamed text becomes the persisted assistant
message. The app keeps the stream open afterwards for a possible
`conversation_updated` frame carrying the auto-generated title.

**Acceptance criteria**

- [ ] The first turn in a new thread updates its title without a manual
      refresh.
- [ ] Closing the stream at `[DONE]` is not what the app does — verified
      by a new thread that receives its title.
- [ ] After completion, the assistant message survives a refetch
      unchanged.

## F04-R8 · Failure (Must)

`{"error": "..."}` means the run failed. Unlike a cancel, a failed run
**does** persist whatever text had accumulated, plus the error, so the
partial answer is real and will be there on reload.

**Acceptance criteria**

- [ ] A model container dying mid-answer shows the error attached to that
      turn, with the partial text kept.
- [ ] The thread stays usable — the next message can be sent once the run
      is terminal.
- [ ] A run that failed while the app was elsewhere surfaces its error on
      reopening the thread (the conversation payload carries `last_run`
      with the error).

## F04-R9 · Image attachments (Should)

Photos from the camera or gallery, sent as `images` on the send payload —
the same encoding the web UI uses. On a phone this is the most natural
input there is: a photo of a screen, a whiteboard, an error message.

**Acceptance criteria**

- [ ] An image can be attached from the gallery and from the camera.
- [ ] Attachments are visible in the composer and individually removable
      before sending.
- [ ] A message can be sent with images and no text.
- [ ] A sent image renders in the user's message in the thread and
      survives a refetch.
- [ ] A large photo is downscaled before upload rather than failing.

## F04-R10 · Leaving does not stop the run (Must)

Navigating away, backgrounding the app or locking the phone must not
cancel the run. The app unsubscribes; the server keeps generating and
persists the reply. Reattachment is F09.

**Acceptance criteria**

- [ ] Send a long turn, immediately leave the thread, wait, return: the
      complete answer is there.
- [ ] Backgrounding the app during a run issues no cancel request —
      verified in the dashboard log.

---

## Endpoints used

| Method | Path |
|---|---|
| POST | `/api/chat/conversations/<id>/messages` |
| PUT | `/api/chat/conversations/<id>/messages/<msg_id>` (F06) |
| POST | `/api/chat/conversations/<id>/cancel-active-run` |
| POST | `/api/chat/runs/<id>/cancel` (fallback) |
| GET | `/api/chat/conversations/<id>` |

## Deviations from the mockup

- **No tok/s readout.** Screen 04 draws a live tokens-per-second figure
  in the stop bar. The web chat has no such readout — the throughput
  numbers on the dashboard come from a separate service-metrics panel, not
  from the chat stream — so R-B (web parity) excludes it. See
  Dropped-Features.
- **"Partial text is kept" on Stop is wrong.** Screen 04's note says
  cancelling keeps the partial answer. It does not: the server marks the
  run cancelled and saves no assistant message. Corrected in F04-R6.
- **No critique overlay.** No sidekick, as requested.

## Deviations found while implementing

- **`conversation_updated` is frequently never delivered, so the app polls
  for the title as a backstop.** `auto_generate_title` runs *after* the run
  has already been marked complete (`run_manager._execute`), and
  `observe()`'s idle backstop closes the stream the moment a 3 s silence
  finds the run in a terminal state. Titling with a local model takes
  longer than that as often as not: measured 4 s on
  `llamacpp-gemma-4-26b-a4b-it-q8`, in which case the client gets
  `{"type":"run_status","status":"completed"}` and the stream closes with
  the title frame published to a bus nobody is subscribed to. The frame is
  still handled when it does arrive (and it did on one of the two turns
  measured); when it does not, the app refetches the conversation a few
  times over the next six seconds, but only for a thread still titled
  exactly `New Conversation` — the same guard the server itself uses — so
  no other thread is ever polled. This is a dashboard-side bug the app
  works around rather than something F04 changes; without the workaround
  F04-R7's first criterion fails on this rig.
- **`run_status` is not reattach-only.** The wire table lists it under
  "reattach to an already-finished run". The idle backstop above emits it
  on the *send* path too, so one reader has to accept it from any of the
  three endpoints.
- **`run_status` also carries `error`.** The table shows
  `{"type":"run_status","status":"…"}`; `chat/routes.py:stream_run` sends
  `{"type":"run_status","status":…,"error":…}`, which is how a reattach to
  a run that failed while the app was away learns why.
- **`message_saved`'s `message_id` is a UUID string,** not the integer the
  shape suggests.
- **A terminal drops the streamed turn only if the refetch succeeds.** D3
  says every terminal replaces `streaming` with what the server has. When
  the refetch itself fails there is nothing to replace it with, and
  dropping it anyway takes the answer, the error and the user's own
  message off screen with nothing said — the worst outcome of the three.
  So the turn is held over, marked unconfirmed: it stops counting as a
  live run (the composer comes back), it carries the run's error inline
  since `last_run` could not be fetched, and the next successful load
  discards it in favour of the saved message.
- **Stop works with no locally streamed turn.** The requirement assumes
  Stop belongs to a run this client started. A thread can be opened while a
  run started elsewhere is still going (F09 has not landed, so there is no
  reattach yet), and cancel-by-conversation handles that case unchanged —
  the app passes `active_run.id` as the guard.

## Out of scope

- Regenerating an answer (no endpoint; the web does it by editing and
  re-sending — that is F06).
- Streaming to more than one thread at a time in the UI. Multiple runs can
  exist server-side; the app renders the one that is open.

## Known gap — attachments are not persisted (F04-R9)

Composer **text** is persisted to DataStore via `DraftStore`, so it
survives process death and the 401 round-trip F00-R3 describes.
**Attachments are not** — they live only in `ThreadViewModel._state`
(`addAttachment`). Anything that destroys the ViewModel, most commonly
process death while the system photo picker is in the foreground, brings
the text back and drops the images with no indication. Observed once on a
real device: a one-character draft returned and its image did not, and
the turn was sent without it.

Not fixed in the real-device fix pass, deliberately. Once the ViewModel
is gone nothing knows an attachment existed, so it cannot even be
reported — the fix is to persist attachments, and at ~140 KB per base64
data URL that is wrong for DataStore (which rewrites the whole file) and
risks `TransactionTooLarge` in `SavedStateHandle`. The right shape is
files in `cacheDir` keyed by conversation, with the draft record pointing
at them. That is a small feature, not a fix — schedule it rather than
bolting it on.
