# F03 · Starting a conversation

**Mockup:** screen 03 · New chat sheet · **Depends on:** F02, F07 · **Blocks:** F04

A sheet, not a screen. Everything prefills from the last chat, so the
fast path is: tap New chat, tap Start, type.

---

## F03-R1 · Create with a model (Must)

`POST /api/chat/conversations` with `main_service`. It is the only
required field. The response is the new conversation; the app opens it.

`main_service` is either a local service name (`vllm-…`, `llamacpp-…`,
`ds4-…`) or `openrouter:<model-id>`. The picker is F07.

**Acceptance criteria**

- [ ] Creating with only a model selected produces a usable thread.
- [ ] The new thread appears at the top of the list.
- [ ] The model defaults to the one used for the previous chat, and that
      default survives an app restart.
- [ ] If the remembered model is no longer running, the sheet says so and
      requires an explicit choice rather than creating a dead thread.
- [ ] Creation failure shows the server's message and keeps the sheet
      open with the user's selections intact.

## F03-R2 · System prompt picker (Should)

Managed prompts come from `GET /api/chat/prompts` (`{prompts: [{id, name,
content, sort_order}]}`). Selecting one sends `prompt_id` on create; the
server copies that prompt's content into the conversation.

Sending no prompt at all is not the same as sending an empty one: with
neither `main_system_prompt` nor `prompt_id`, the server applies the
configured global default. The sheet's "Default" option must therefore
send **neither field**.

**Acceptance criteria**

- [ ] The list matches the prompts shown on the dashboard, in the same
      order.
- [ ] Choosing a named prompt produces a thread whose system prompt is
      that prompt's content.
- [ ] Choosing "Default" produces a thread carrying the server's
      configured default prompt.
- [ ] With no managed prompts defined, the row shows only Default and
      does not appear broken.

## F03-R3 · Tools for the new thread (Should)

Which MCP servers this thread may call, from
`GET /api/chat/mcp-servers`. Selection is written as `mcp_servers_json`
(a JSON *string* of an array of server ids) — see F08 for the full
behaviour and for changing it later.

**Acceptance criteria**

- [ ] Enabled servers on the new thread match what was selected.
- [ ] The selection is remembered as the default for the next new chat.
- [ ] With no servers available, the row is hidden rather than empty.

## F03-R4 · Project assignment — **Withdrawn**

Decision 3: the phone has no project concept. The sheet has no project
row, and `project_id` is never sent on create. Threads created on the
phone are always unfiled; assigning one to a project is desktop work.

**Acceptance criteria**

- [ ] The create payload never contains `project_id`.
- [ ] The sheet shows no project row.

## F03-R5 · Title (Should)

Threads are created with the server's default title and auto-titled after
the first turn — the run emits a `conversation_updated` frame carrying
the generated title (see F04-R7). The sheet does not ask for a title.

**Acceptance criteria**

- [ ] A new thread shows a placeholder title until the first answer
      completes, then shows the generated one without a manual refresh.

## F03-R6 · The minimal sheet (Must)

With F03-R4 withdrawn, the sheet is at most three rows: Model, system
prompt, tools. If F03-R2 and R3 are also cut, it is one row — Model — and
a Start button. That must remain a coherent screen, not a sheet with
empty slots.

**Acceptance criteria**

- [ ] With optional rows disabled, the sheet renders as a single choice
      plus Start.

---

## Endpoints used

| Method | Path |
|---|---|
| POST | `/api/chat/conversations` |
| GET | `/api/chat/prompts` |
| GET | `/api/chat/mcp-servers` |

## Deviations from the mockup

- **No critic / sidekick row.** Cut as requested. Threads created on the
  phone send no `sidekick_service`, so it stays null.
- **No project row.** Screen 03 draws one. Decision 3 removed projects
  from the phone — F03-R4 is withdrawn.
- **Tools on a new thread are always two calls, not one.** `POST
  /api/chat/conversations` (`dashboard/chat/routes.py:330-379`,
  `create_conversation`) builds its `Conversation` row from a fixed field
  set — `title, main_service, sidekick_service, main_system_prompt,
  sidekick_system_prompt, parent_conversation_id, selected_text,
  project_id` — and never reads `mcp_servers_json` from the request body.
  Only `PUT /api/chat/conversations/<id>` (`update_conversation`) accepts
  it. So enabling tools on a brand-new thread is always create-then-PUT;
  the app issues the PUT immediately after a successful create. If that
  PUT fails, the conversation still exists — the sheet stays open and
  offers Retry (re-issue only the PUT) or Open anyway, never a second
  create. F08 (which owns changing tools on an existing thread) should
  assume the same two-call shape, not a single endpoint.
- **The model picker is F03's own minimal build, not F07's.** F07 (model
  selection) doesn't exist yet, and F03-R1 can't work without choosing a
  model, so this feature builds a flat picker: local services from `GET
  /api/services` (filtered to a recognised engine prefix and `kind ==
  "chat"`) plus the curated OpenRouter list from `GET
  /api/chat/settings/openrouter-models` when configured. It lives entirely
  in `NewChatScreen`'s `ModelPickerSheet` composable. F07 enriches that one
  composable (search, favorites, richer grouping) without touching
  `ModelOption`, the repositories it reads from, or
  `ConversationsRepository.create`'s signature.

## Out of scope

- Creating or editing managed prompts or MCP registry entries. Both are
  read-only here.
- Projects in any form.
- Setting a custom `main_system_prompt` free-text on the phone. Pick a
  managed prompt or take the default.

## Carried forward

| Criterion | Verify in |
|---|---|
| R5 · "…then shows the generated one without a manual refresh" | **F04.** The auto-title arrives on a `conversation_updated` frame during the first turn (F04-R7). F03 verified only the placeholder-title half. |

Unit-tested rather than device-verified, deliberately: the
remembered-model-not-running branch (would need a container stopped), and
the no-managed-prompts / no-MCP-servers empty cases (would need shared
server config mutated). Everything else in F03 was driven on device
against the live dashboard, including creation failure — reachable with
`dev.sh net off`, which is app-scoped and reversible.
