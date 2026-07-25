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

## Deviations found while implementing

- **Text selection is invoked through the menu, not by long-pressing text
  directly.** F05 shipped `MarkdownBody` always wrapped in a
  `SelectionContainer`, so a long-press on the text itself started a
  selection. That gesture and F06-R1's long-press-for-menu compete for the
  same touch: `SelectionContainer`'s own long-press-to-select handler and an
  outer long-press-to-open-menu handler both sit on the same pointer stream
  over the same glyphs, and there is no reliable way to referee between them
  from outside Compose's text-selection internals.

  Resolved by making selection opt-in per message: `MarkdownBody` (and the
  equivalent in `UserBubble`) only mounts a `SelectionContainer` when that
  specific message is in "selection mode", entered via the long-press menu's
  "Select text" row and left via a "Done" pill. While a message is not in
  that mode it has no selection gesture at all, so the long-press-to-menu
  detector is the only thing listening and always wins; while it is in that
  mode the long-press detector is removed entirely (not merely overridden),
  so the selection drag is the only thing listening. Verified live on device:
  long-press opens the menu everywhere text is *not* already in selection
  mode, and once "Select text" is tapped, long-pressing the same text starts
  a native selection (word highlight, drag handles, the system Copy/Select
  all toolbar) with no menu popping up over it.

  This changes *how* F05-R3's selection is invoked, not whether it works —
  selecting a span in rendered prose and in a code block is unchanged once
  selection mode is on. See `feature/thread/MarkdownRender.kt`'s
  `MarkdownBody` doc comment and `feature/thread/ThreadMessages.kt`'s
  `LongPressableMessage`.

## Out of scope

- Editing assistant messages (the server rejects it — 400).
- Reordering or moving messages between threads.
- Retrying a failed turn as a distinct action — edit-and-resend covers it.

## Verification notes

**Deleting a user message does not cascade to its assistant reply.**
`chat/routes.py:delete_message` is a single-row delete and the spec never
asked for cascading, so the reply is left with no preceding question.
Verified live. Recorded so a future reader does not file it as a bug.

**The discard count is exact.** `create_run_with_user_message`
(`chat/db.py:903`) does `DELETE … WHERE seq >= msg.seq` and then inserts
a fresh row for the edit, so the edited message is destroyed and
replaced. The client's strictly-after count is therefore what the user
actually loses. Verified against the live backend at the first message of
a thread (discards 3) and at the last user turn before its reply
(discards 1).

**For the owner, needing a real thumb:** drag-selecting inside a
horizontally-scrolling code block, and long-press timing generally.
Synthetic `input swipe` does not reproduce Compose's
long-press-then-extend gesture — one attempt was eaten by the edge-back
gesture.

**Not caught live:** cancelling an edit-and-resend run mid-stream. The
local model finishes faster than a Stop tap lands on this rig, so only
the already-finished no-op case was exercised. `confirmEdit` routes
through the same `collectRun`/`finishRun` as `send()`, which F04 covers
for cancellation, and nothing edit-specific touches that path.
