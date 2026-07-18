# Chat redesign — decisions log

Running record of what we keep / drop from the "Drydock" mock
(`mock.html`). Becomes a GitHub issue at the end.

## Decided

### D1 — Vocabulary: DROP the nautical metaphor
Use conventional, conversation-based terms everywhere. No harbor jargon.

| Mock term | Use instead |
|---|---|
| Berth | Conversation |
| Tender | Spin-off |
| Dock tray | (minimized) spin-off taskbar |
| Inspector | Critique panel |
| Command console | Composer / message input |
| Operator | You / user |

Naming/labels only — this decision does not by itself accept or reject
any visual treatment.

### D2 — Collapse the global app nav (`components/Sidebar.jsx`) — RESOLVED
Reclaim horizontal space for chat. Currently 224px with logo + text
labels (Services / Chat / Tools) + user block. **Resolved:** collapsible
with a pin/chevron toggle; collapsed = icons only (hover tooltips),
expanded = icons + labels; state persisted in localStorage; applied on
**all routes**; **default collapsed**.

### D3 — Keep the active-conversation vertical-bar highlight
The colored left vertical bar marking the active conversation row in the
list stays. (Independent of palette choice — bar can be any accent.)

> **Issue B filed:** https://github.com/teo-mateo/llm-dock/issues/28
> (Projects + Conversation Artifacts) — covers D4, D5, D6.

### D4 — Conversation Artifacts (NEW feature — separate issue)
Full spec in `SPEC-conversation-artifacts.md`. Resolved: UNIFY into one
conversation-scoped artifact store (existing per-message render outputs
become `source='render'`); DB blob in a separate table (10 MB cap, MIME
allowlist); tree nested under the conversation in the left sidebar grouped
Uploaded / Generated; spin-offs get read-only access to the root's
artifacts. Open: sign-off on the render-output migration + the proposed
defaults (soft-delete user-only, the 3 model tools, referencing UX).

### D5 — Introduce a Project entity (now)
`projects(id, name, created_at, archived_at, default_main_service,
default_sidekick_service, default_system_prompt, default_mcp_servers)`.
`conversations.project_id` **nullable** (projects are opt-in grouping;
spin-offs inherit parent's project, enforced equal). Artifacts (D4) are
**project-scoped** when a conversation is in a project. Migration: wrap
each existing root conversation (+ spin-offs) in an auto-named project.
Open crux: artifact ownership for project-less conversations (see Open).

## Open (to discuss)

- D2 sub-decision: collapse mode (toggle+remembered / always icon rail /
  hover-to-expand) and scope (all routes / chat only)
- Visual styling of sidebar conversation rows: status LED + mono meta line
  + spin-off tree connector — keep? (the active vertical bar is already
  kept per D3)
- Typography (Archivo / IBM Plex Mono / Newsreader serif for assistant)
- Color palette (deep ink + amber/cyan vs. current gray/blue)
- Instrument header strip (telemetry cluster, toggle switches, signal sweep)
- Transcript-as-log (timeline spine, hairline blocks vs. bubbles)
- Reasoning "tape" / tool instrument cards / drift chip styling
- Composer treatment
- Critique panel treatment
- Spin-off window + taskbar treatment
- Background atmosphere (grid, blooms, grain)
- Streaming signal-sweep motion
