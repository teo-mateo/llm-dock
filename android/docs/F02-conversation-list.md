# F02 · Conversation list

**Mockup:** screen 02 · Conversations · **Depends on:** F01 · **Blocks:** F03, F04

The app's home screen. The same threads the web UI shows, because it is
the same `chat.db`.

---

## F02-R1 · The list (Must)

Conversations, most-recently-updated first, from
`GET /api/chat/conversations`. Each row shows the title, the model, and
the relative update time.

The endpoint returns `updated_at DESC` and supports `limit`/`offset`.
Note that `limit=-1` returns the whole list as one consistent snapshot;
offset paging over a mutable ordering can skip or duplicate rows as
threads are touched. Pick one and be explicit about the trade-off.

**Acceptance criteria**

- [ ] A thread started in the web UI appears in the phone list after a
      refresh, and vice versa.
- [ ] Sending a message moves that thread to the top.
- [ ] With no conversations, an empty state explains how to start one.
- [ ] The list refreshes on returning to it from a thread, without a
      full-screen spinner over already-loaded content.

## F02-R2 · Model chip per row (Must)

Each row carries a chip naming the thread's `main_service`, colour-coded
by engine the way the dashboard badges them: vLLM, llama.cpp, ds4,
OpenRouter. Engine is derivable from the service name prefix
(`vllm-`, `llamacpp-`, `ds4-`) and from the `openrouter:` prefix for
remote models.

**Acceptance criteria**

- [ ] Threads on each engine show a visually distinct chip.
- [ ] A thread whose `main_service` is `openrouter:<model-id>` shows the
      model id, not the raw prefixed string.
- [ ] A thread pointing at a service that no longer exists still renders
      — with the name, unstyled — rather than crashing the row.

## F02-R3 · Live "generating" indicator (Must)

The list payload carries `active_run` (`{id, status, active_step,
started_at}`) or `null` for each conversation. Any thread with a non-null
`active_run` shows a live indicator; opening it reattaches to the stream
(F09).

This is the one thing a phone client does that a browser tab cannot:
walk away, come back, the answer is there.

**Acceptance criteria**

- [ ] Start a turn in the web UI, then open the phone list: that thread
      shows the indicator.
- [ ] The indicator clears once the run reaches a terminal status.
- [ ] Tapping such a row opens the thread already streaming, mid-answer.

## F02-R4 · Delete a conversation (Must)

Swipe on a row to delete, behind a confirm (F00-R9), via
`DELETE /api/chat/conversations/<id>`.

**Acceptance criteria**

- [ ] The confirm names the thread's title.
- [ ] After confirming, the row is gone and stays gone after a refetch.
- [ ] Deleting a thread with an active run does not leave a ghost row.
- [ ] Cancelling the swipe restores the row with no request made.

## F02-R5 · Batch delete (Should)

Long-press enters a selection mode; `POST /api/chat/conversations/delete`
takes `{ids: [...]}` in one call.

**Acceptance criteria**

- [ ] Selecting several threads and confirming removes exactly those.
- [ ] The confirm states how many will be deleted.
- [ ] Exiting selection mode without acting changes nothing.

## F02-R6 · Project grouping — **Withdrawn**

Decision 3: the phone has no project concept. The list is flat.

Threads that belong to a project — created on the desktop — still appear
in the list and open normally; they are simply not grouped, and nothing
in the app names their project. `GET /api/chat/projects` is never called.

**Acceptance criteria**

- [ ] A thread belonging to a project appears in the flat list alongside
      every other thread, in `updated_at` order.
- [ ] Opening and using such a thread works exactly like any other,
      including its model's project file tools (F08-R5).
- [ ] The app never calls `/api/chat/projects`.

## F02-R7 · Navigation to Models (Must)

A bottom bar with two destinations, Chats and Models (F10) — decision 1.
It appears on the two list screens only; opening a thread gives the full
screen to the conversation.

**Acceptance criteria**

- [ ] The bar is present on the conversation list and the models list.
- [ ] The bar is absent inside a thread and inside model detail/logs.
- [ ] Switching tabs preserves each tab's scroll position.

## F02-R8 · Start a new conversation (Must)

A primary action opens the new-chat sheet (F03).

**Acceptance criteria**

- [ ] The action is reachable one tap from the list, including when the
      list is empty.

---

## Endpoints used

| Method | Path |
|---|---|
| GET | `/api/chat/conversations?limit&offset` |
| DELETE | `/api/chat/conversations/<id>` |
| POST | `/api/chat/conversations/delete` |

## Deviations from the mockup

- **No last-line preview.** Screen 02 draws a preview line under each
  title. The list endpoint returns conversation rows only — no messages —
  so a preview would cost one `GET /api/chat/conversations/<id>` per
  visible row. Rows show title, model chip and time.
- **No search.** Drawn as "your call" on screen 02 and cut in the
  decision table. There is no search endpoint, and the web UI has no
  conversation search either. See Dropped-Features.
- **No project groups.** Screen 02 draws collapsible project headers.
  Decision 3 removed projects from the phone entirely — the list is flat.

## Out of scope

- Projects in any form: no grouping, no headers, no assignment, no
  project names anywhere in the UI.
- Spin-off threads as a distinct concept — they render as ordinary
  threads if one was created on the desktop.
