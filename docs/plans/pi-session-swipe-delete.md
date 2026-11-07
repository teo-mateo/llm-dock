# Swipe-to-delete a pi session

Adds the delete path the pi-remote surface never had: swiping a session row right in the
Android Pi tab removes it, with an undo window, the same shape the chat list uses
(`android/docs/F02-conversation-list.md`).

## The contract

| | |
|---|---|
| `DELETE /api/pi/sessions/<session_id>/<instance_id>` | `200 {"deleted": true}` · `409 pi_session_live` · `404 unknown_session` |
| SSE, both pi streams | new frame `session_removed` with `{"session_id": …, "instance_id": …}` |

`PiRemoteClient.delete_session` is the whole rule: refuse a session the extension is
heartbeating for, otherwise drop the `pi_sessions` row together with its `pi_events`,
`pi_prompts` and `pi_commands` rows, and publish `removed` on the bus. The route adds
nothing to that decision, and the stream layer only turns `removed` into a frame.

## Decisions

**Deleting erases llm-dock's capture, everywhere.** The session row, its transcript events,
its prompts and its command audit disappear from `pi_remote.db`, so the row vanishes from the
phone and the web page at once. pi's own session file is untouched — `pi --resume` still works.
A local-only "hide on this phone" alternative was rejected: two devices showing different
lists for one dashboard, plus a dismissed-id store to keep in sync forever.

**A live session refuses.** While the extension heartbeats, its next `hello` re-inserts the
row through `UPSERT_SQL` (`ended_at = NULL` included). Deleting then would hide a session that
is about to reappear, so the client gets `409 pi_session_live` and the phone says so. Ended
sessions — what the list actually accumulates — delete freely. Ending a live session is
`POST …/abort`, already a separate control (F19); combining abort and delete in one gesture was
rejected as a destructive surprise behind a swipe.

**The undo window precedes the request, not the other way round.** Exactly the chat list's
reasoning, held here so the second copy is not read as an accident: the row leaves the list
immediately, the DELETE is held for 3 s, and only when that expires is anything sent. Undo
therefore costs nothing and needs no second call to put the row back, and there is no
optimistic-delete-plus-recreate dance the server would have to support. `PendingUndo` lives in
the UI state rather than in the list itself so a stream update landing inside the window cannot
resurrect the row; `visibleLive`/`visibleEnded` are what the screen draws.

**The pending row is dropped, not re-added on failure.** If the DELETE fails the row returns —
it still exists on the dashboard, and leaving it hidden would be the UI lying. The failure is
named once in a snackbar, not swallowed.

**409 gets its own sentence.** The dashboard's error bodies are machine codes
(`pi_session_live`), and `AppError.displayMessage` shows a server body verbatim. The phone maps
`409` on this call to "A running session can't be deleted." rather than printing the code.

**`session_removed` is additive.** The pi sessions stream already ignores unknown frame types
(`PiSessionsStreamEvent.Unknown` → list unchanged), so an older app is unaffected by the new
frame and needs no protocol version bump. The list stream keeps running after one; the
single-session transcript stream ends after it, because the session it was reading is gone.

## Files

| | |
|---|---|
| `dashboard/pi_remote/session_store.py` | `delete()` — the session row plus its four captured tables |
| `dashboard/pi_remote/client.py` | `delete_session()` — the refuse-live rule, the queue drop, the `removed` publish |
| `dashboard/pi_remote/stream.py` | `session_removed` on both streams |
| `dashboard/routes/pi_remote.py` | the DELETE route and its status map |
| `android/…/data/PiSessionDeleteRepository.kt` | the one REST call |
| `android/…/feature/pi/PiSessionsViewModel.kt` | undo window, action error |
| `android/…/feature/pi/PiSessionsScreen.kt` | swipe row, snackbar with Undo |
| `android/…/core/net/PiSessionsStreamEvent.kt` | parse `session_removed` |
| `android/…/data/PiSessionsRepository.kt` | merge removes the key |

## Tests

Dashboard: `test_pi_remote_client.py` (deletes all four tables, refuses while heartbeating,
unknown key, publishes `removed`), `test_pi_remote_routes.py` (200 / 409 / 404 / 401),
`test_pi_remote_stream.py` (frame on the list stream which then continues; frame then end on the
transcript stream).

Android: `PiSessionsViewModelTest` (hidden before anything is sent, sent when the window closes,
undo sends nothing, second swipe commits the first, failure restores and names itself, 409 has
its own message), `PiSessionsRepositoryTest` (merge drops the key, ignores another instance, a
later frame does not resurrect it), `PiSessionsStreamEventTest`, `PiSessionDeleteRepositoryTest`
(method, path, escaping, the 409 body).

## Not done

- No delete control in the `/v2/pi` web page; the frame reaches it, the button does not exist yet.
- llm-dock never touches pi's own session storage.
- The undo job runs in `viewModelScope`: swiping and leaving the tab within 3 s abandons the
  delete rather than sending it, so the row reappears on return. Same gap as the chat list.

## Noticed while testing

`BaseUrl.resolve` percent-encodes the path it is handed, and `Endpoints.encodePathSegment` has
already encoded it, so a session id containing `/` or a space would travel as `%252F`. Harmless
while ids are UUIDs — which pi's session ids and instance ids are — and the same today for the
existing `messages`/`abort`/`stream` paths, so it is recorded rather than fixed here.
