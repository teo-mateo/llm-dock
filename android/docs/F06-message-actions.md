# F06 · Message actions

**Mockup:** screen 06b · Long-press · **Depends on:** F04

Fixing what you wrote, and getting text out of the app.

---

## F06-R1 · Long-press menu (Must)

Long-pressing a message opens a menu. The options depend on the role:

| Action | User message | Assistant message |
|---|---|---|
| Copy | yes | yes |
| Select text | yes | yes |
| Share | yes | yes |
| Delete | yes | yes |
| Edit and resend | yes | no — the server only edits user messages |

**Acceptance criteria**

- [ ] Long-press opens the menu on both roles, with Edit absent on
      assistant messages.
- [ ] The menu dismisses on outside tap with nothing changed.
- [ ] Copy and Share carry the message's text exactly.

## F06-R2 · Delete a message (Must)

`DELETE /api/chat/conversations/<id>/messages/<msg_id>`, behind a
confirm.

The server refuses with **409** while a run is active in that
conversation: the in-flight assistant turn is not yet persisted, and
deleting a prior message mid-run would leave the transcript inconsistent.

**Acceptance criteria**

- [ ] Deleting removes the message from the thread and it stays gone
      after a refetch.
- [ ] Attempting a delete while a run is active shows the server's
      message rather than optimistically removing the message.
- [ ] Delete is not offered at all while a run is active in that thread.
- [ ] Cancelling the confirm makes no request.

## F06-R3 · Edit and resend (Should)

`PUT /api/chat/conversations/<id>/messages/<msg_id>` with the new
`{content, images}`. This is destructive: the server **truncates the
thread from that message's position** and starts a new run from there.
Everything after it — including assistant answers — is gone.

It is easy to fat-finger on a phone, so it gets an explicit confirm that
says how many messages will be discarded, per F00-R9.

The response is an SSE stream, identical in shape to a send (F04). The
same reader handles it.

**Acceptance criteria**

- [ ] Editing a message mid-thread discards everything after it and
      begins a new answer from the edited text.
- [ ] The confirm states, in numbers, what is about to be discarded.
- [ ] Cancelling leaves the thread byte-identical — verified by refetch.
- [ ] Only user messages can be edited; the option is absent elsewhere.
- [ ] An edit rejected with 409 (a run became active in between) does not
      truncate anything — verified by refetch.

## F06-R4 · Text selection (Should)

Selecting a span within a message, for copying part of an answer without
taking the whole thing.

**Acceptance criteria**

- [ ] A span can be selected and copied from rendered prose and from a
      code block.
- [ ] Selection does not trigger the long-press menu.

## F06-R5 · Share (Must)

Hand the message text to any other Android app through the system share
sheet.

**Acceptance criteria**

- [ ] Sharing an assistant answer to a notes or messaging app delivers
      the full text.
- [ ] Sharing a message containing code preserves the fences.

---

## Endpoints used

| Method | Path |
|---|---|
| DELETE | `/api/chat/conversations/<id>/messages/<msg_id>` |
| PUT | `/api/chat/conversations/<id>/messages/<msg_id>` |

## Deviations from the mockup

None.

## Out of scope

- Editing assistant messages (the server rejects it — 400).
- Reordering or moving messages between threads.
- Retrying a failed turn as a distinct action — edit-and-resend covers it.
