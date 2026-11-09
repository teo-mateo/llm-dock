# Android Pi transcript — tool-call rendering today vs. stored event shapes

Read-only investigation for the "purpose-built viewers per tool kind" task
(requested by llmdock-po in #llmdock, 2026-11-09 ~12:47Z). No code changes.
Evidence: Android sources under `feature/pi/`, and the live capture store
`dashboard/pi_remote.db` (26 sessions, 46 session/instance pairs, ~210k events,
2026-11-07 10:41Z → 2026-11-09 12:48Z; counts below are as-of query time and
drift upward while pi is active).

## 1. How the transcript renders tool calls/results today

Data flow: `GET /api/pi/sessions/<sid>/<iid>/events` (`dashboard/routes/pi_remote.py:127`)
→ `PiEventDto` → `PiEvent(seq, type, ts, payload: JsonObject)`
(`data/model/PiEvent.kt`) → `buildPiTranscript()` → Compose list.

- `transcript/PiTranscript.kt:17` — `PiItem.Tool(callId, name, args: String?,
  output: String?, status, durationMs, truncated, ts)`. **`args` and `output` are
  the raw JSON strings from the wire, never parsed.** `applyToolStart` (:143)
  stores `args`; `applyToolEnd` (:161) overwrites `output` with `result`
  (or `partial` on `tool_update`).
- `transcript/PiToolRuns.kt` — `groupToolRuns` (:20) packs consecutive tool items
  into a collapsible `ToolGroup`; a group shows only the first
  `VISIBLE_TOOL_ROWS = 3` rows plus a "N more…" expander (:62). The row summary is
  `argsSummary` (:46): the args JSON flattened to `key=value · key=value…`,
  whitespace-collapsed, hard-cut at `MAX_SUMMARY_CHARS = 160`.
- `PiToolGroupView.kt` — the group card (:45) renders one row per tool (:83):
  status dot + tool name (monospace, 1 line) + the 160-char args summary
  (1 line, ellipsis) + "Details". Tapping the row expands `PiToolDetails` (:124):
  status text, then **`item.args` printed verbatim as raw JSON**, then
  **`item.output` printed verbatim as raw JSON**, clipped to `MAX_OUTPUT_LINES = 20`
  lines with a "Show all" toggle (:138–144), plus "output truncated by pi-remote"
  when `truncated` is set.
- `PiItemViews.kt:20` — a lone tool item is wrapped in a single-tool group, so the
  same raw rendering applies everywhere; `PiSessionTranscript.kt:67` feeds the
  grouped list to the `LazyColumn`.

Net: args and results are walls of raw JSON text. The only structure today is the
160-char flattened summary on the collapsed row. The same wire data also feeds the
web UI (`dashboard/frontend/src/utils/piTranscript.js`), which is out of scope here
but shares the payload shapes below.

Wire contract (dashboard side): `pi_remote/events.py:93–107` — `tool_start` carries
`{call_id, name, args: string|null, truncated}`, `tool_update` `{call_id, name,
partial: string|null, truncated}`, `tool_end` adds `{result: string|null, is_error,
duration_ms}`. The extension (`pi-extension/src/mirror.ts:143–164`) forwards pi's
own `args.text`/`result.text` + `truncated` flags; result strings cap at 64 KiB
pi-side (observed max = 65536).

## 2. What the tools actually are (stored `pi_events`)

`tool_start` = `tool_end` ≈ 6,889 calls each, 9,356 `tool_update`. Counts:

| tool | calls | share |
|---|---|---|
| bash | 5,168 | 75.0% |
| edit | 532 | 7.7% |
| process | 356 | 5.2% |
| read | 344 | 5.0% |
| chatterbox_send | 174 | 2.5% |
| write | 165 | 2.4% |
| codemode | 47 | 0.7% |
| contact_supervisor | 31 | |
| subagent | 27 | |
| chatterbox_look | 22 | |
| chatterbox_join / subagent_supervisor | 9 / 7 | |
| grep / ask_user / chatterbox_leave / find | 4 / 3 / 2 / 1 | |
| `bash=` (anomalous name) | 1 | |

Outcomes: 278 `tool_end` with `is_error=true` (~4%); 109 with `truncated=true`
(~1.6%, mostly `read` hitting the 64 KiB cap).

### Arg shapes (top-level keys of the `args` JSON, by frequency)

- **bash** — `{command, timeout?}` (3,523 with timeout, 1,649 without). Command
  length p50 ≈ 272 chars, p95 ≈ 1,955, max 14,258.
- **edit** — always `{path, edits}`; `edits` is a list of `{oldText, newText, …}`
  blocks. Args p50 ≈ 1.2k chars, max ≈ 17.6k — the old/new text dominates.
- **process** — `{action, …}`: `start` 180, `stop` 129, `output` 37, `list` 8.
  start: `{action, command, name, cwd?, notify?, stream?, watches?}`; stop/output:
  `{action, id, tailLines?}`.
- **read** — `{path, offset?, limit?}` (215 with all three, 124 path-only).
- **write** — always `{path, content}`; content dominates (args p50 ≈ 4.6k, max 30.7k).
- **chatterbox_send** — `{audience, text, to?, ignore_unseen?, important?}`; text
  p50 ≈ 2k chars (args p50 ≈ 2.1k, max 8.2k).
- **codemode** — `{code}` only (p50 ≈ 2.5k, max 7.7k).
- **chatterbox_look** — `{what, count?}`; **chatterbox_join** — `{channel?, nick?}`;
  **chatterbox_leave** — `{}`.
- **grep / find** — `{pattern, path, limit?}`.
- **ask_user** — `{question, message?, kind?, options?, allow_free_text?}`.
- **subagent** — `{action, …}` with high variance (`id`, `message`, `lines`,
  `view`, `topic`, `capabilities`, or a full spawn spec `workflow/cwd/isolation/…`).
- **contact_supervisor** — `{message, reason}`; **subagent_supervisor** —
  `{action, message, replyTo?}`.

### Result shapes (`tool_end.result` JSON string)

Almost all results are MCP-style objects, not plain text:

- **bash / read** — `{content: [{type:"text", text}], structuredContent: {output: "…"}}`
  (the actual stdout/file text lives in `structuredContent.output` and duplicated in
  `content[0].text`). A minority are plain strings (bash 18, read 91). Sizes: read
  p50 ≈ 13k chars, p95/max = 65,536 (the cap); bash p50 ≈ 0.9k, p95 ≈ 10.5k, max 64k.
- **edit** — `{content: [{type:"text", text: "Successfully replaced N block(s) in <path>."}], details: {diff: "…unified diff…"}}`. p50 ≈ 2.8k, max ≈ 29k — the diff in `details.diff` is the bulk.
- **process** — `{content: […], details: {action, result: {ok, info: {id, name, pid, command, cwd, status, exitCode, stdoutFile, stderrFile, …}}}}`.
- **chatterbox_send** — `{content: [{text: "Sent to X in #chan; confirmed…"}], details: {outcome}}` — tiny (~140 chars).
- **write** — `{content: [{text: "Successfully wrote to <path>"}]}` — tiny (~130 chars).
- **codemode** — `{content: […script output…], details: {calls: [{name, args, status, durationMs}]}}`; result p95 ≈ 43k.
- **chatterbox_look** — `{content: […], details?}`; p50 ≈ 184, max 12k.
- **subagent** — `{content: […], details}`; p50 ≈ 2.3k, p95 ≈ 46k.
- **grep / find / chatterbox_join / leave / ask_user / supervisors** — same
  `{content, details?}` envelope, small.
- **tool_update partials** (bash 3,994, codemode 6): same `{content: […], details: {}}`
  envelope streamed in chunks.

## 3. What this means for purpose-built viewers

- The 80/20 split is stark: **bash (75%), edit, process, read, chatterbox_send,
  write ≈ 97%** of calls. Five viewers (bash, edit, read/write, process,
  chatterbox_*) cover nearly everything; the long tail can keep the raw fallback.
- Every result is a JSON *string* inside `PiItem.Tool.output`; viewers must parse
  it at render time (MCP `content[]` envelope → join `text` parts; `details` /
  `structuredContent` are tool-specific). Keep the raw string as the fallback for
  unknown tools and for malformed JSON (observed: plain-string results, and at
  least one corrupted name/action value in the store).
- Viewer-relevant extracts per tool: bash → `command` arg + `structuredContent.output`
  (or `content[0].text`); edit → `path` + `details.diff` (real diff view), count from
  `content[0].text`; read → `path, offset, limit` + file text; write → `path` +
  `content` arg; process → `action` + `details.result.info` (pid/status/exitCode);
  chatterbox_send → `audience/to` + `text` + `details.outcome`; codemode → `code`
  arg + `details.calls`.
- Constraints to respect: `PiItem.Tool` is serialized into the on-disk checkpoint
  (`PiSnapshotCodec`) — parse-at-render, don't change the stored shape, or migrate
  the codec; `truncated` and the 20-line / 160-char caps (`PiToolGroupView.kt:42`,
  `PiToolRuns.kt:7`) are the existing readability guards a per-tool viewer replaces;
  grouping (`groupToolRuns`) and per-row expand state are keyed by `callId`/`id` and
  stay valid.
