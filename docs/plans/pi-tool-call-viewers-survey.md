# Pi tool-call viewers — device survey

Observed on emulator-5554, build `f07e15a`, 2026-11-09, against real sessions
(an ended `heapzilla-mail-checker` session on mistral-large-4 and a live
`llm-dock` session on deepseek-v4-1-flash). Code-side shapes and counts are in the
architect's companion notes.

## What a tool call looks like today

Collapsed row: status dot, tool name, then `key=value` of the first argument,
ellipsised, and a `Details` link. Expanded:

1. `done · 0.0 s`
2. the **raw JSON arguments**, e.g. `{"command":"cd … && sed -n '640,680p' …","timeout":30}`
3. the **raw JSON result envelope**, e.g. `{"content":[{"type":"text","text":"…"}]}`,
   with `\n` and `\"` printed literally — multi-line output collapses into one
   wrapped paragraph.

## Problems, by tool

| Tool | Collapsed row | Expanded |
|---|---|---|
| `bash` | `command=cd /forgejo/wt-hzm-74 && sed…` — the `cd` prefix eats the visible width, the actual command is cut off | JSON-escaped command; output escaped into one paragraph, no line breaks |
| `edit` | `path=/forgejo/wt-hzm-74/frontend/src…` — the file name, the only useful part, is cut off | `oldText` and `newText` concatenated as one escaped JSON string; impossible to see what changed |
| `write` | same path truncation | whole file content as an escaped string |
| `read` | (not screenshotted; same path truncation expected) | file content escaped |
| `chatterbox_look` / chatterbox sends | readable (`what=recent · count=30`) | the text appears **twice**: once in `content[].text`, again in `details.items[]`, plus internal fields (`msgid`, `replayed`, `addressed`) |

Cross-cutting:

- `done · 0.0 s` on every call in an ended session (duration not known after replay) — noise.
- Consecutive runs of `bash` calls with identical `cd <worktree> &&` prefixes; the prefix carries no information after the first.
- Absolute worktree paths (`/forgejo/wt-hzm-74/frontend/src/...`) repeated on every row.

## Proposal (survey + architect's shapes, `android-pi-tool-call-viewers.md`)

Parse `args`/`output` at render time; `PiItem.Tool` and the snapshot codec stay
unchanged, and the raw JSON stays reachable as a fallback ("Raw" toggle) for
unknown tools and malformed JSON.

| Priority | Tool (share) | Collapsed row | Expanded |
|---|---|---|---|
| 1 | generic, all tools | name + short arg summary | args as key/value list; result = joined `content[].text` with real line breaks |
| 2 | bash (75%) | `$ <command>` with leading `cd <dir> &&` stripped, dir as a dim chip; red dot + exit code on error | command block, then output terminal block (`structuredContent.output`), first ~12 lines + "show all N lines" |
| 3 | edit (8%) | **basename** + dim dir, `+a −b` | red/green unified diff from `details.diff` (already computed by pi) |
| 4 | read (5%) / write (2%) | basename + `L<offset>–<offset+limit>` / line count | content with line numbers, collapsed after ~20 lines |
| 5 | process (5%) | `start <name>` / `stop <id>` / `output <id>` | status, pid, exit code from `details.result.info`; command; tail lines |
| 6 | chatterbox_* (3%) | `→ #llmdock` / `→ architect: <first line>`; look: `what=recent` | send: message bubble + outcome; look: `details.items` as chat lines (`time · from: text`) — no duplicate |
| later | codemode, subagent, grep/find, ask_user | generic | `code` as mono block + `details.calls` list, etc. |

Cross-cutting: hide `0.0 s` when no duration is known; keep the 3-row group
collapse; shorten paths relative to the session `cwd`.
