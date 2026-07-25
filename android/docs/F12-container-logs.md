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
