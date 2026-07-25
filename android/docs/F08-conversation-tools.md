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

## Out of scope

- Editing the MCP registry (`/api/chat/mcp-registry/*`). Dashboard only.
- Testing a server's connectivity from the phone.
- A global "always use these tools" setting instead of per-thread
  toggles. Recorded as a possible simplification in the mockup; not
  chosen, because it would diverge from the web UI's model (R-B).
