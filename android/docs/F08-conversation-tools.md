# F08 · Per-conversation tools

**Mockup:** screen 07b · Tools · **Depends on:** F03, F04

Which MCP servers a thread may call. Per conversation, exactly as on the
desktop.

---

## F08-R1 · List the available servers (Must)

`GET /api/chat/mcp-servers` returns `{servers: [...]}` — the enabled
entries from the server's registry, each with an id, name, description
and icon.

The registry mixes built-ins (sympy-math, schemdraw-circuits,
render-html, project-files) with machine-local external servers declared
in `mcp_servers.json`. The phone shows whatever the server reports and
hardcodes nothing.

**Acceptance criteria**

- [ ] The list matches the dashboard's Tools list.
- [ ] Adding a server to `mcp_servers.json` and reloading the registry
      makes it appear on the phone without an app update.
- [ ] With no servers enabled, the sheet shows an empty state rather than
      an error.

## F08-R2 · Toggle per conversation (Must)

Selection is stored on the conversation. Reading it uses the
`mcp_servers` array in the conversation payload; **writing it uses
`mcp_servers_json`** — a JSON string — on
`PUT /api/chat/conversations/<id>`. The array field is read-only; writing
it has no effect.

The web UI does exactly this: build the next array, `JSON.stringify` it,
PUT `mcp_servers_json`, refetch.

**Acceptance criteria**

- [ ] Enabling a server, then reopening the thread, shows it still
      enabled.
- [ ] The same thread opened in the web UI shows the same set.
- [ ] Toggling several servers before closing the sheet persists all of
      them.
- [ ] A failed write reverts the toggle in the UI rather than showing a
      state the server does not have.

## F08-R3 · Tools are per thread, not global (Must)

The set applies to the conversation it was set on. The new-chat sheet
(F03-R3) may remember the last selection as a *default* for new threads,
but changing one thread's tools never changes another's.

**Acceptance criteria**

- [ ] Changing tools in thread A leaves thread B untouched.

## F08-R4 · Effect during a run (Must)

The enabled set is read when a turn starts. Changing it mid-run does not
affect the run in flight.

**Acceptance criteria**

- [ ] The sheet is unavailable, or clearly marked as taking effect next
      turn, while a run is active.

## F08-R5 · Project file tools (Should)

The phone has no project concept (decision 3) — but a thread created on
the desktop inside a project still opens here, and the server still
scopes the project-files MCP server to that project's directory when it
runs. The model can therefore read and write project files from a phone
turn even though the phone shows no project UI.

Those calls must render as ordinary tool cards (F04-R5). Nothing special
is needed for them, and nothing must break on them.

**Acceptance criteria**

- [ ] A desktop-created project thread, continued from the phone, shows
      project file tool calls and results like any other tool.
- [ ] The app offers no file browser, upload, download or editor.
- [ ] The absence of project UI never blocks or hides such a tool call.

---

## Endpoints used

| Method | Path |
|---|---|
| GET | `/api/chat/mcp-servers` |
| PUT | `/api/chat/conversations/<id>` (`mcp_servers_json`) |

## Deviations from the mockup

None.

## Verification notes

**A stale-write race was found in review and fixed.** Toggling three
tools at ordinary tapping speed left the server holding an *earlier*
selection than the sheet showed, and a tool the user never chose
(`browser-fetch`) appeared enabled on reopening. Reproduced through
normal use, not a stress case.

Cause: `toggleTool` PUT the **whole** id array optimistically and
cancelled the previous write. But `ApiClient.request` uses a blocking
`client.newCall(...).execute()` that is not cancellation-aware, so
cancelling the coroutine did not recall a request already on the wire —
it landed whenever it landed, in any order, and `apiCall` rethrows
`CancellationException`, so the outcome was discarded silently.

Fixed by **serialising the writes** behind a `Mutex` in `ThreadViewModel`
with a monotonic toggle counter. Ordering alone suffices because each PUT
carries the absolute list, not a delta: the last one queued is the last
one sent and is authoritative. The counter preserves the old `cancel()`'s
intent — only the newest toggle's own failure reverts the sheet, so a
stale failure cannot fight a newer write that is about to set the right
value anyway.

The mutex is per-ViewModel, deliberately. `ConversationsRepository` is an
app-wide singleton, so locking there would serialise unrelated
conversations.

**Cancellation-awareness in `ApiClient` was considered and rejected**, and
would not have fixed this anyway — cancellation always races delivery.
It is also not free: `stop()` fires `cancelActiveRun` in `viewModelScope`,
so an abortable one-shot client would mean tapping Stop and immediately
navigating back kills the cancel POST in flight, leaving the run alive
server-side — a regression in already-verified F04-R6. The streaming path
is already cancellation-aware where it needed to be
(`OkHttpSseTransport` holds and cancels its own `Call`). If F09 wants
this, it should be opt-in per call site, since each needs its own answer
to F04-R10's "navigation is not cancellation".

**Outstanding**

| Item | Why |
|---|---|
| R4 during a real run | Verified by JVM test (the guard blocks both open and toggle; the server is never contacted) and by inspection (`enabled = canOpenTools`, not merely relabelled). Not caught on screen: turns on this rig finish in under a second, too fast to screenshot a stable generating state. |
| R1 · dynamic registry reload | Requires editing `mcp_servers.json` and reloading the registry — a dashboard configuration action, out of scope for the app and for its agents. |
| R5 · project file tools (Should) | No project-scoped conversation on hand. F04's `ToolCallCard` special-cases no server id, so a project-files call renders like any other; confirmed by inspection only. |

**MockWebServer cannot express the write race.** It replies in the order
responses were queued and both requests arrive in send order, so the
reordering never occurs. The regression test uses a repository subclass
whose writes park on per-call gates, plus a main-executor drain so
"has the next write been sent yet?" is a settled question rather than a
timing accident. An earlier gate-only version of that test passed even
against the broken code.

## Out of scope

- Editing the MCP registry (`/api/chat/mcp-registry/*`). Dashboard only.
- Testing a server's connectivity from the phone.
- A global "always use these tools" setting instead of per-thread
  toggles. Recorded as a possible simplification in the mockup; not
  chosen, because it would diverge from the web UI's model (R-B).
