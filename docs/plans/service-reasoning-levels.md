# Per-service reasoning levels: declared at config time, selectable at runtime

**Implemented** (P1-P8). Deviations from this plan, both deliberate:
`parse_levels`/`validate_levels` trim spaces **around** comma-separated entries
(so `"off, low"` is accepted) while still rejecting case differences and
internal whitespace — trimming a separator cannot change which token is sent,
normalising case can, so §5's `"medium "` case is accepted rather than
rejected. And §5's live gate is **not yet run**: it needs a GPU slot, so no
ladder is declared on a production service by this change.

Original plan follows, as written before implementation.

Plan only — no code written. Baseline: branch
`feat/chat-reasoning-level-selector-qwen38-fn-skilled` @ `57846fa`, clean working
tree. Only this ref was inspected; no other branch was read.

## 1. Goal and scope

A service entry gains an optional declaration of the reasoning levels it offers
(one comma-separated string). The chat UI then offers exactly those levels for
that service, and the chosen one is applied to the actual model request.

| ID | Requirement |
|----|-------------|
| R1 | Any service can declare its available reasoning levels in `services.json` / the config panel as a comma-separated string. |
| R2 | The declaration is validated on every write path (`POST /api/services`, `PUT /api/services/<name>`); malformed or unsupported input is rejected, never stored. |
| R3 | Declared levels reach the chat client through the existing service payloads (`GET /api/services` and the `/api/services/stream` snapshot). |
| R4 | The user selects one level per conversation; the choice persists and is visible on reload. |
| R5 | The selection is applied to the outgoing request for engines where the mechanism is verified (llama.cpp, vLLM). |
| R6 | No level selected ⇒ the outgoing request is byte-identical to today's (no new fields, no behavior change). |
| R7 | A level that the current service does not offer can never reach the wire, whatever the client sends. |
| R8 | Editing the declaration needs no container restart: it takes effect on the next run. |

Non-goals (explicit, see §6 for how old behavior is preserved): **OpenRouter gets
no levels in this release**; **levels are plain names — no token budgets**;
critique/sidekick runs, auto-title generation and ephemeral spin-off runs keep
today's behavior; TabbyAPI, ds4 and ik_llamacpp get no mapping; no global default
level; no per-message override; the legacy `dashboard/static` UI is untouched.

Decisions locked by the requester (not assumptions): plain names only, selection
stored per conversation, OpenRouter deferred.

## 2. Verified current behavior

| Path | Entry point | State / validation owner | Final consumer | Change or exclusion |
|---|---|---|---|---|
| Config write (create) | `routes/services.py:219 create_service` | `flag_metadata.py:1671 validate_service_config` | `ComposeManager.add_service_to_db` + `rebuild_compose_file` | accept + validate new field |
| Config write (edit) | `routes/services.py:300 update_service` (merges `existing.update(data)`, so un-sent keys survive) | same | `update_service_in_db` + rebuild | accept, validate, `""` clears |
| Config write (CLI) | AGENTS workflow: `add_service_to_db` + `rebuild_compose_file` | none (raw dict) | same file | works unchanged; validation is added in the shared normalizer, so CLI-written junk is reported at read time (see §3) |
| Config read → payload | `docker_utils.py:117 get_docker_services` (two dict branches: container-exists `:166-183`, not-created `:193-211`) | `services.json` | `GET /api/services` (`routes/services.py:74`) **and** SSE snapshot (`services/event_manager.py:141 get_services_snapshot`) | add one field in both branches |
| Config → compose | `service_templates.py` / `templates/*.j2` | — | `docker-compose.yml` | no change: unknown config keys are inert in rendering |
| Rename | `routes/services.py:443` → `compose_manager.py:467 rename_service` (relocates the whole entry) | — | — | field survives, no change |
| Chat selection (client) | `ChatArea.jsx:141/209 ModelSelector`, `:185 handleModelChange → updateConversation` | `chat/db.py:414 update_conversation` allowlist | `conversations` row | add `reasoning_level` |
| Run start | `chat/routes.py:661 send_message` → `_start_run_response` → `manager.start` | `ChatTurnRequest` (`chat/runtime.py:104`) | `ChatRunner._build_stream` (`chat/runtime.py:131-159`) | snapshot level at run creation |
| Request build | `chat/tool_loop.py:13 stream_with_tools:34` / `chat/llm_proxy.py:289 stream_chat_completion` | `llm_proxy.py:309-329` payload dict | `requests.post` (`llm_proxy.py:339`) | inject reasoning fields |
| Auto-title | `chat/runtime.py:62` (own `stream_chat_completion` call) | — | — | excluded: passes no level |
| Critique | `chat/critique.py` / `routes.py:~860` | — | — | excluded |
| Ephemeral spin-off | `chat/routes.py:908 spinoff` (own payload) | — | — | excluded |
| OpenRouter runs | `chat/openrouter.py:70 resolve` → same `stream_chat_completion` | curated list in `chat_settings.json` | OpenRouter | **excluded**: `resolve()` supplies no levels, so the mapping receives no level and sends nothing |

Decisive evidence for the wire mechanism:

- **llama.cpp** (source inside `llm-dock-llamacpp:latest`, image built
  2026-09-05; `tools/server/server-common.cpp`): `:1308-1311` request
  `chat_template_kwargs` merge **over** the CLI defaults set by
  `--chat-template-kwargs`; `:1315-1322` `enable_thinking` kwarg is parsed to a
  bool; `:1325-1331` top-level `reasoning_effort` is honored, `"none"` disables
  thinking; `:1367` `reasoning_budget_tokens` **or** `thinking_budget_tokens`
  overrides the server `--reasoning-budget`, applied only when the template
  declares thinking tags (`:1371-1375`). `tools/server/server-chat.cpp:284-290`
  also folds a Responses-style `reasoning.effort` into `reasoning_effort`.
- **vLLM** (running `vllm-qwen3-8-flash-next-mixed-nvfp4-fp8`, served with
  `--reasoning-parser qwen3`; `/openapi.json` read live): `ChatCompletionRequest`
  exposes `reasoning_effort` with enum
  `none|minimal|low|medium|high|xhigh|max`, plus `thinking_token_budget` (int),
  `include_reasoning` and `chat_template_kwargs`. `entrypoints/openai/chat_completion/protocol.py:574-592`
  passes `reasoning_effort` into the template kwargs **and** derives
  `enable_thinking = reasoning_effort != "none"`.
- **A declared ladder is genuinely necessary.** `docs/reasoning-level-sweep-qwen3.8-27b.md`
  shows the Qwen3.8 chat template accepts only `low|medium|xhigh` (plus the
  Unsloth `high` alias) and answers anything else with **HTTP 500**, that the
  named knob is not a token budget, and that `off` is the one reliable state.
  So llm-dock must never invent level tokens — it can only offer what the
  operator declares. The same doc argues a numeric token budget is the only
  predictable cap; budgets are deliberately **out of this release** (§3.1).
- **OpenRouter** (public catalog read live, recorded only because it is where a
  later phase would start): `supported_parameters` contains `reasoning`
  (306 models), `reasoning_effort` (167), `include_reasoning` (306), and
  `chat/openrouter_catalog.py:235` already derives a `reasoning` boolean from
  them. **Out of scope here**, and still unverified for the exact request shape —
  which is precisely why it was dropped rather than guessed.

Precedent that a chat-only metadata key lives happily in `services.json`:
`favorite` (`docker_utils.py:139` reads it, `:182/:210` exposes it, no template
uses it).

## 3. Proposed design

### 3.1 Representation (config time)

New optional key on any service entry:

```json
"reasoning_levels": "off,low,medium,xhigh"
```

Grammar (parsed, never guessed): `LEVEL = NAME`, joined by `,` with optional
spaces. `NAME = [a-z][a-z0-9_-]{0,15}` — **plain names only**, at most 8 levels,
whole value ≤ 120 chars. `off` is a reserved id meaning "thinking disabled".
Missing key or `""` ⇒ no levels (feature inert for that service). Duplicate ids
are errors. Anything containing `:` is rejected with a message naming the
budget-free grammar, so a future budget feature fails loudly rather than being
silently truncated to `low`. Levels keep declaration order — that is the UI order.

Rationale for a CSV of free-form names over the alternatives: (a) server flags
(`--reasoning-budget`, vLLM `--default-chat-template-kwargs`) are static per
container and cannot switch per turn, so they cannot satisfy R4/R5; (b) a JSON
array of objects is richer than requested and duplicates what the parser already
produces internally; (c) a fixed enum would be wrong, because the accepted
tokens are a property of each model's chat template, not of llm-dock. Normalized
shape is `{"id": "low", "effort": "low"}` (id and effort are equal for plain
names) — so adding a `budget_tokens` key, or promoting the config value to a real
array, is additive rather than a rewrite.

One pure module owns all of it, because validation, payload exposure and request
mapping must agree: **`dashboard/reasoning_levels.py`** (proposed) with
`parse_levels(raw) -> list[dict]`, `format_levels(list) -> str`,
`level_id(raw_or_list, level_id) -> dict | None`, and
`request_fields(level, engine) -> dict`. Disk I/O stays with its current owners
(`ComposeManager`, `settings_store`); this module is pure and unit-testable.

### 3.2 Exposure to the client

`docker_utils.py get_docker_services` gains `reasoning_levels` (the parsed list,
`[]` when unset) in **both** dict branches. That single change feeds
`GET /api/services`, the SSE snapshot, and therefore `useServicesSSE`/
`useRunningServices`, whose reducer keeps whole snapshot objects
(`useServicesSSE.js:13-25`) and merges deltas onto them — no frontend plumbing
needed. Unparsed/invalid stored strings degrade to `[]` plus one `logger.warning`
(a hand-edited `services.json` must not break the Services page).

Staleness is bounded by the existing `refresh()` (reconnect → new snapshot,
`useServicesSSE.js:390`), which the config panel calls after a successful save;
chat re-reads a snapshot on mount anyway. A config edit while a chat page stays
open is picked up on the next snapshot — acceptable and stated in the UI tooltip.

### 3.3 Selection and its lifecycle

Per-conversation column `conversations.reasoning_level TEXT NULL`, following
`main_service`:

- `NULL` = "say nothing to the model" (today's behavior, R6). Not `"off"`:
  `off` is an active instruction to disable thinking.
- Storage is the **level id** string only; nothing derived from the service entry
  is copied into the conversation row, so editing the declaration never needs a
  conversation migration.
- Migration: one entry in `chat/db.py:186 _migrate`; add to
  `update_conversation`'s `allowed` set (`chat/db.py:415-417`), to
  `models.Conversation` and its `to_dict`, and to `create_conversation`
  (`chat/routes.py:433`). `PUT` with `null` clears.
- Two-point enforcement (R7): on **write** (`POST/PUT /api/chat/conversations*`)
  a non-null level must be offered by `main_service` → else 400. At **run
  creation** (`_start_run_response`) it is re-checked against the service's
  current list and dropped to `None` for that run if the service lost the level
  or the model changed; the effective value is reported on `run_started` so the
  UI can show "level not available for this model" instead of lying.
- The level is snapshotted into `ChatTurnRequest` at run creation, matching the
  `effective_project_id` discipline (`chat/runtime.py:104-115`): a mid-run edit
  affects the next run, never the in-flight one.

### 3.4 Wire mapping

`request_fields(level, engine)` returns exactly one of these shapes, and the
caller merges it into the payload at `llm_proxy.py:309-329`:

| Engine (`template_type`) | `off` | named level | Evidence |
|---|---|---|---|
| `llamacpp` | `reasoning_effort: "none"` + `chat_template_kwargs: {"enable_thinking": false}` | `reasoning_effort: "<id>"` | server-common.cpp:1315-1331 |
| `vllm` | `reasoning_effort: "none"` (server derives `enable_thinking: false`) | `reasoning_effort: "<id>"` | protocol.py:574-592; openapi enum |
| `ik_llamacpp`, `tabbyapi`, `ds4`, `openrouter:*`, unknown | `{}` | `{}` | deliberate: unverified → nothing is sent |

No numeric field is ever sent: llama.cpp's `thinking_budget_tokens` and vLLM's
`thinking_token_budget` are the correct hooks and are recorded here for the later
phase, but this release maps names only.

`off` sends both fields on llama.cpp because templates differ: the llama.cpp
server reads `enable_thinking` itself (`server-common.cpp:1315`) while some
templates only honor the kwarg; `reasoning_effort: "none"` also *erases* the
effort kwarg (`:1329`), which is the state the sweep measured as perfect.
Sending `enable_thinking` to a template that does not declare it is inert.
Request-level kwargs override the service's own `--chat-template-kwargs`
server default (`server-common.cpp:1308-1311`), which is what makes R8 true —
no container restart.

`stream_chat_completion` and `stream_with_tools` gain a keyword-only
`reasoning_level=None` (plus the engine string resolved once inside
`resolve_service`), threaded from `ChatRunner._build_stream`. Unknown/None
level ⇒ the dict is empty ⇒ R6 holds at the boundary, asserted by test.

`resolve_service` (`llm_proxy.py:81-99`) returns only `{host_port, api_key}`
today; it gains `template_type` and `reasoning_levels`, sourced from the same
`get_docker_services()` call it already makes (which is why §3.2 puts both in
that payload rather than re-reading `services.json`).

### 3.5 UI

- **Config panel** (`ServiceConfigPanel.jsx`): one text input
  "Reasoning levels (comma separated)" beside Port/API Key, initialized from
  `config.reasoning_levels`, added to `isDirty`/`handleDiscard` and to the PUT
  body built at `:88-96` (send the string, and `""` to clear; the backend merge
  keeps it if omitted). Save calls `refresh()` from `useServicesSSE`. Server-side
  validation errors surface through the existing `onError`.
- **Chat**: a small `ReasoningLevelSelect` rendered next to `ModelSelector` in
  `ChatArea.jsx` (both the header `:141` and the new-chat variant `:209`), fed by
  the levels of the currently selected service, value = `conversation.reasoning_level`,
  onChange → existing `updateConversation` + reload path (`:185`). Hidden entirely
  when the service declares no levels — never a disabled-but-mysterious control.
  New-chat pre-selection flows through `create({ main_service, reasoning_level })`
  (`ChatPage.jsx:240`). Panel: the body is built at `ServiceConfigPanel.jsx:87-96`.

### 3.6 OpenRouter: excluded by decision

`openrouter.resolve()` (`chat/openrouter.py:70-84`) returns no `template_type`
and no levels, so `request_fields` is never reached with a level for an
`openrouter:` service — the payload stays exactly as today, with no code needed
to keep it that way. If it is ever picked up, the entry point is a
`reasoning_levels` string on curated `openrouter_models` entries
(`chat_settings.json`, Settings page), and it must start by probing which field
OpenRouter actually honors (`reasoning_effort` vs `reasoning: {effort}`) and how
`off` reads, with a 1-token completion per candidate shape before anything ships.

## 4. Implementation sequence

| Step / req | Files and symbols | Behavior and responsibility | Depends on | Acceptance |
|---|---|---|---|---|
| P1 pure layer | `dashboard/reasoning_levels.py` (new) | parse/format/lookup/`request_fields`; no I/O, engine table | — | `tests/test_reasoning_levels.py` |
| P2 config write | `flag_metadata.py:1671 validate_service_config` (+ new `OPTIONAL_STRING_FIELDS` check) | reject malformed `reasoning_levels` on create+update with a field-named message; `""` accepted as clear | P1 | `tests/test_service_reasoning_levels.py` via `POST/PUT /api/services` |
| P3 exposure | `docker_utils.py:117-211` both branches | parsed `reasoning_levels` on every service payload; bad string ⇒ `[]` + warning | P1 | `tests/test_services_sse.py` snapshot assertion |
| P4 conversation | `chat/db.py` `_migrate`, `update_conversation`, `chat/models.py Conversation`, `chat/routes.py create_conversation/update_conversation` | column, allowlist, `to_dict`, write-time validation | P1 | `tests/test_chat_db_*` + `test_chat_run_routes.py` pattern |
| P5 runtime mapping | `chat/routes.py _start_run_response`, `chat/runtime.py ChatTurnRequest/_build_stream`, `chat/tool_loop.py stream_with_tools`, `chat/llm_proxy.py resolve_service/stream_chat_completion` | run-time re-check, snapshot, merge into payload | P1-P4 | payload-shape test in `tests/test_llm_proxy_stream.py` style (asserted both present and absent fields) |
| P6 UI config | `ServiceConfigPanel.jsx` | input + dirty/discard/PUT body + SSE refresh | P2 | `npm run lint`, `npm run test` (vitest panel test), manual save on one llama.cpp service |
| P7 UI chat | new `ReasoningLevelSelect.jsx`, `ChatArea.jsx`, `ChatPage.jsx` | per-conversation select, hidden without levels | P3-P5 | vitest component test + manual run |
| P8 docs | `AGENTS.md` (services.json schema row, gotcha about never synthesizing level tokens) | keep the single reference accurate | P1-P7 | review |

P1-P5 are the backend vertical slice: after P5 the API is usable by a direct
client even before the UI lands. P6 and P7 are independently shippable.

## 5. Verification

Proposed tests (none run yet; only read-only probes were run during planning):

- **Parsing/validation (R1, R2)** — `tests/test_reasoning_levels.py`: empty /
  missing/whitespace-only, `"off"`, `"off,low,medium,xhigh"`, spaces around
  commas, duplicate ids, a colon-bearing value (`"low:512"`) rejected with the
  grammar named in the message, uppercase and surrounding-space handling
  (`"Low"`, `"medium "`) rejected rather than silently normalized, 9 levels, 121
  chars, non-string value. `tests/test_service_reasoning_levels.py`:
  `validate_service_config` for `llamacpp`/`vllm`/`tabbyapi`, then create-then-
  read round trip through `ComposeManager` and `PUT` with `""` clearing while an
  unrelated key (`favorite`) survives the merge.
- **Exposure (R3)** — extend `tests/test_services_sse.py`: snapshot entries carry
  the parsed list; a garbage string yields `[]` and does not raise.
- **Persistence (R4)** — create with a level → reload → `to_dict`; `PUT` to a
  different level; `PUT null` clears; a rejected level leaves the stored value
  untouched; migration on a pre-existing DB file (create DB without the column,
  open, expect the column and `NULL` for old rows).
- **Boundary payload (R5, R6, R7)** — in the `_FakeResp`/monkeypatched-post style
  of `tests/test_llm_proxy_stream.py`: for engine `llamacpp` assert
  `reasoning_effort` plus `chat_template_kwargs.enable_thinking` for `off`, and
  assert `payload` carries **no** reasoning keys at all when the level is `None`;
  same for `vllm` with `reasoning_effort` only; assert no numeric budget field
  (`thinking_budget_tokens`/`thinking_token_budget`) ever appears; assert
  `ik_llamacpp`/`tabbyapi`/`openrouter:*` payloads are byte-identical to today's;
  assert a stale level (service lost it between write and run) produces the
  no-level payload and a `run_started` note.
- **Live gate (one, bounded, after P5)** — against a running llama.cpp Qwen3.8
  service: `POST /apply-template` with the two `off` shapes to confirm the empty
  think block renders without any GPU work (the command from
  `docs/reasoning-level-sweep-qwen3.8-27b.md` §Reproduction), then one 8-token
  chat completion per level through the chat API comparing reasoning length.
  The vLLM counterpart uses `--reasoning-parser qwen3`, already enabled on the
  running service. Both probes hit a GPU in use — run them when it is idle.

## 6. Rollout, risks, exclusions

- Additive: no migration rewrites anything, `services.json` gains an optional
  key, `chat.db` gains a nullable column via the existing `ALTER TABLE` list.
  Rollback = ignore the field; dropping the column is unnecessary (SQLite leaves
  it, and old builds simply do not select it).
- Behavior-preserving by default: services without the key render no UI control
  and send no new field, so the 21 existing services are untouched (verified by
  the R6 payload assertion test).
- Config edits are metadata-only for the runtime path even though
  `update_service` still rebuilds `docker-compose.yml` (`routes/services.py:350`);
  no container is recreated by that route, so R8 holds. Do not use
  `ComposeManager.add_service()` for scripted adds — the AGENTS-documented YAML
  round-trip breaks `restart: no`.
- Risk: a declared token the template rejects → HTTP 500 from llama.cpp (the
  documented Qwen3.8 behavior). Mitigation: llm-dock sends only declared tokens,
  the UI list is exactly what was declared, and the live gate in §5 is run per
  new ladder before a level is declared on a production service.
- Risk of over-claiming: a level name is an instruction to a chat template, not a
  token cap — the sweep showed the ladder is not a budget and is sometimes
  inverted. The UI therefore labels the control "reasoning level" and shows no
  token counts, and `AGENTS.md` records that budgets would need
  `thinking_budget_tokens` (llama.cpp) / `thinking_token_budget` (vLLM).
- Excluded paths keep sending no reasoning field: `auto_generate_title`
  (`chat/runtime.py:62`), critique, `POST /api/chat/spinoff` (`chat/routes.py:908`).
  A crafted request cannot activate the feature there, because activation happens
  only via `request_fields` with a level the runner was given, and those call
  sites pass none.

## 7. Readiness

**Ready for implementation.** All three design questions were answered by the
requester and are now baked in rather than assumed: levels are **plain names**
(no `:budget` in the grammar, no numeric field in any payload), the selection
lives in a **per-conversation `reasoning_level` column**, and **OpenRouter is
excluded** (§3.6 explains why that exclusion needs no code). Remaining work is
P1-P8 as sequenced; the only thing gating a *new* ladder going live on a real
service is the bounded `/apply-template` + 8-token probe in §5, which is an
acceptance gate, not an open design question.
