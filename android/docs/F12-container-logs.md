# F12 · Container logs

**Mockup:** screen 10c · Logs · **Depends on:** F10, F11

The best reason to reach for the phone when something will not come up.

---

## F12-R1 · Streaming logs (Must)

`GET /api/services/<name>/logs/stream?tail=N` (tail clamped 1–1000,
default 200). The stream emits typed frames:

| Frame | Meaning |
|---|---|
| `{"type":"snapshot_start"}` | The historical tail begins |
| `{"type":"log","line":"…"}` | One log line |
| `{"type":"snapshot_end"}` | The tail is done; what follows is live |
| `{"type":"stream_end"}` | The container's log stream ended |
| `{"type":"error","message":"…"}` | Something broke |
| `: keepalive` | Comment frame during quiet periods — not a line |

A service with no container yet returns **404** ("Service has not been
created yet").

**Acceptance criteria**

- [ ] Opening logs shows the recent tail immediately, then new lines as
      they are written.
- [ ] The boundary between historical and live output is visible.
- [ ] A quiet container keeps the view connected through keepalives.
- [ ] `stream_end` (container stopped) is shown as an end state, not as a
      connection failure.
- [ ] Logs for a `not-created` service show the 404 as a clear message,
      not an empty black screen.
- [ ] Leaving the screen closes the stream — verified in the dashboard
      log.

## F12-R2 · Follow tail (Must)

The view follows new output while the user is at the bottom, and stops
the moment they scroll up. A control returns to the tail.

**Acceptance criteria**

- [ ] Scrolling up during heavy output holds position.
- [ ] The return-to-tail control appears only when not following, and
      resumes following.

## F12-R3 · One-shot fetch as fallback (Should)

`GET /api/services/<name>/logs?tail=N` returns the tail as a single JSON
blob with timestamps. Use it when the stream cannot be established.

**Acceptance criteria**

- [ ] With streaming unavailable, the view still shows a tail and says it
      is not live.

## F12-R4 · Level colouring (Should)

Colour by level where the line makes it derivable (`ERROR`, `WARN`,
`INFO`). This is client-side pattern matching over unstructured container
output — it must degrade to plain text, never mangle a line.

**Acceptance criteria**

- [ ] Error lines from a real vLLM startup failure are visually distinct.
- [ ] A line that matches nothing renders plainly and completely.
- [ ] Colouring never truncates or reorders output.

## F12-R5 · Share the buffer (Must)

Hand what is on screen to any other app — the whole point when you want
to paste a startup failure somewhere.

**Acceptance criteria**

- [ ] Share delivers the visible buffer as text, in order.
- [ ] A large buffer is truncated with an explicit marker rather than
      failing silently.

## F12-R6 · Search within the buffer (Later)

Filtering the loaded buffer client-side. Not in v1.

---

## Endpoints used

| Method | Path |
|---|---|
| GET | `/api/services/<name>/logs/stream?tail=N` |
| GET | `/api/services/<name>/logs?tail=N` |

## Deviations from the mockup

None.

## Out of scope

- Log retention or export to a file.
- Logs for anything but a compose-managed service (the endpoint refuses
  names outside the project).

## Verification notes

Both Must requirements verified live against the rig; the review
reproduced the findings independently rather than trusting them.

**`stream_end` is an end state, not a failure — verified by breaking it
first.** The reviewer patched the `StreamEnd` branch to route to `Failed`
and watched `LogsViewModelTest` fail at line 112, then reverted. Then
proved it live: opened logs on a running container and stopped it mid-
stream. The status flipped from green "Live" to grey "Stream ended —
container stopped", with the container's own `cleaning up before exit…`
as the final line. Not an error screen.

This is the criterion that mattered most: a stopped container ends its
log stream normally, so getting it wrong would make the feature look
broken every single time the owner stops a model.

**Teardown, independently confirmed.** `ss -tnp` filtered on
`qemu-system-x86` (where the emulator's host-side sockets live) showed
the exact stream socket `127.0.0.1:57060 → 127.0.0.1:3399`; it was gone
within ~1 s of pressing back. This requirement has now been got wrong
twice on this project — F07, and a real bug in F10 where
`viewModelScope`-launched streams survived a tab switch — so it is
verified by socket, never by inspection.

**No reconnect loop, deliberately.** Unlike the GPU and services stream
repositories, `LogsStreamRepository` does not retry. A `stream_end` is a
normal outcome, and auto-reconnecting into a genuinely dead stream is
worse than not. A real network drop instead surfaces as `Failed` with a
manual Retry, so the user is never stuck — one tap reconnects. Reviewed
and agreed rather than assumed.

**Follow-tail did not inherit F04's sharp edge.** `ThreadScreen`'s
pattern misbehaves in a list too short to scroll, where `canScrollForward`
stays false and following flips back on. Here that is the correct
behaviour: if the whole buffer fits on screen there is nothing to scroll
away from, so there is no disagreement to honour.

**Not verified:** keepalive behaviour on a quiet container (accepted on
code read — SSE comments are already dropped by `SseFrameParser` and
covered by its tests), and R4's level colouring on screen, since no
container produced a real ERROR line during review. R4 is Should and its
classification logic is unit-tested.

**F11-R7 (readiness) was not picked up here**, and the review agreed with
that call. Wiring "up but not ready" into the picker touches
`NewChatViewModel`'s selection logic and its own state machine — a
different screen's concern, not a small addition just because a log
client now exists. It stays a documented skip.
