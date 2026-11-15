# `/model` slash command in the chat composer

Add a pi-style `/model` slash command to the llm-dock React v2 chat composer: typing
`/model <ref>` as the whole composer message switches the conversation's `main_service`
instead of sending a chat message. Frontend-only — the backend `PUT` already accepts
`main_service`.

Reference UX: pi 1.5.0 already ships `/model` (`/github/earendil-works/pi`:
`packages/coding-agent/src/core/slash-commands.ts:21`,
`src/modes/interactive/interactive-mode.ts:3331` and `:5377` with argument completion at
`:755`). This plan borrows the syntax, not the selector-UI (llm-dock's model picker is a
native `<select>` in the header, which cannot be opened programmatically).

## 1. Goal and scope

Requirements:

- **R1** — `/model <ref>` as the entire (single-line, attachment-free) composer message
  switches the open conversation's `main_service` through the existing
  `PUT /api/chat/conversations/<id>`, reloads the conversation, shows a transient
  confirmation notice, and is **not** sent as a chat message.
- **R2** — bare `/model` lists the available models in a transient notice; not sent.
- **R3** — an unknown ref shows an error notice; nothing is sent, nothing is changed.
- **R4** — in the empty-state (new-conversation) composer, `/model <ref>` sets the
  pre-selected model via the existing `onModelChange` path (which also clears the
  pre-selected reasoning level) and does not create a conversation or send.
- **R5** — any other input (non-command text, multi-line text, commands with images)
  passes through to the normal send path unchanged.

Constraints and non-goals:

- React v2 frontend only (`dashboard/frontend/src`). No backend change: `PUT
  /api/chat/conversations/<id>` already stores `main_service` (`chat/db.py:510`
  allowlist); `conversation_policy.resolve_conversation_update` validates
  `reasoning_level`/`sampling_params`/`project_id`/`prompt_id` but not `main_service`
  existence — the selector has the same property today, so client-side validation in
  the command is the enforcement point, consistent with the existing UI.
- Out of scope: switching the sidekick/critic service, composer autocomplete (ChatInput
  has no completion infrastructure), the Ghost chat page, the Pi page (pi handles
  `/model` itself there — its composer sends raw text to the pi session), and the
  Android client.
- No persistence of the model choice beyond the conversation row (that is what
  `main_service` already is).

## 2. Verified current behavior

Read-only inspection at `origin/main` (`7ebf490`), the base of the implementation
branch `feat/chat-model-slash-command`:

- No slash-command handling exists in the chat composer (grep for `startsWith('/')`
  in `components/chat` / `hooks` finds only an unrelated path-normalize comment in
  `ProjectPage.jsx`).
- Two composer send entry points in `components/chat/ChatArea.jsx`: empty state
  `onSend={(msg, images) => onCreateAndSend?.(msg, images)}` (~line 158) and the
  open-conversation `handleSend` (~line 236) → `onSend` = `useChat.sendMessage`.
- Model switching today: header `ModelSelector` → `ChatArea.handleModelChange`
  (~line 208): `updateConversation(conversation.id, { main_service: value })` then
  `onReloadConversation?.(id)`. Empty-state pre-selection: `ChatPage.jsx`
  `handleComposerModelChange` (`setSelectedModel` + clears reasoning level) and
  `handleCreateAndSend` (line 275) which creates with `main_service: selectedModel`.
- The model list the selectors offer (`ModelSelector.jsx` / `ModelOptions.jsx`):
  `useRunningServices()` = running chat-kind services (`hooks/useRunningServices.js`,
  `isChatService` drops e.g. `kind: "embedding"`), `useOpenRouterModels()` curated list
  (only when configured), `useProviderModels()` provider groups. Service-string
  conventions: `utils/openrouter.js` (`serviceNameForModel`, `isOpenRouterService`,
  prefix `openrouter:`), `utils/providers.js` (`providerServiceName`,
  `parseProviderService`, `<providerId>:<modelId>`).
- Backend run path reads `conversation.main_service` at run creation
  (`hooks/useChat.js:520`, server: `chat/llm_proxy.resolve_service`); an unknown
  service string fails there, at run time, not at update time.

## 3. Proposed design and contracts

**New pure module** `dashboard/frontend/src/utils/modelSlashCommand.js` (single owner of
syntax + resolution, unit-testable without React):

- `parseModelCommand(text)` → `{ arg: string | null }` iff `text.trim()` starts with
  `/model` at position 0, followed by end-of-string or whitespace, **and** the text
  contains no `\n` (single-line only). `/model` → `{arg: null}`; `/model  foo ` →
  `{arg: "foo"}`; `/modelx` → `null`; anything with a newline → `null`.
- `resolveModelRef(arg, models)` → `{ service } | { ambiguous: [...] } | null`,
  where `models` is `{ services, openRouterModels, providerGroups, currentService }`
  (shapes as the hooks return; `services` pre-filtered by `isChatService`).
  Resolution order:
  1. exact match of `arg` against chat-capable local service names;
  2. if `arg` contains a `:`, it resolves only when it **is offered** (the curated
     list / the provider's model list) or equals `currentService` (a no-op re-select
     of what the conversation already uses, e.g. a model that left the curated list).
     The server stores `main_service` unvalidated, so a typo'd exact string would
     only fail at run time — rejected instead (PR review, MEDIUM);
  3. if `arg` contains no `:`, match curated OpenRouter and provider models by id
     (exact) or label (case-insensitive); more than one distinct match returns
     `{ ambiguous: [...] }` so the notice can name the candidates.
  - Local services are matched from the **unfiltered** SSE list filtered by
    `isChatService` (all statuses), not only running ones — a conversation may
    legitimately sit on a stopped service (the reasoning-level control already reads
    the unfiltered list for that reason), and the bare-`/model` listing marks which
    are running.
- `formatModelList(models)` → lines for the bare-`/model` notice (local, then
  OpenRouter, then providers; running marked).

**Interception point** — one wrapper in `ChatArea.jsx` used for *both* composer `onSend`
wiring points (replaces the inline arrow at ~158 and `handleSend` at ~236):

```js
function handleComposerSend(msg, images) {
  if (images.length > 0) return passthrough(msg, images)
  const cmd = parseModelCommand(msg)
  if (!cmd) return passthrough(msg, images)
  ... handle command ...
}
```

Command handling:

- `cmd.arg === null` → set `slashNotice` to `formatModelList(models)`; never send.
- resolved = `resolveModelRef(cmd.arg, models)`; if `null` → `slashNotice` = unknown-model
  error (naming the arg); no PUT, no send.
- open conversation → `await updateConversation(conversation.id, { main_service: resolved })`,
  `onReloadConversation?.(conversation.id)`, notice `Switched main model to <resolved>`.
  The `await` is wrapped: a failed PUT shows `Couldn't switch to <ref>: <message>` and
  does not reload (PR review, MEDIUM — `ChatInput` has already cleared the composer, so
  the notice is the only recovery surface). Mirrors `handleModelChange` exactly (no
  `reasoning_level` clearing — a level the new model lacks is dropped at run start and
  named on `run_started`, the existing behavior).
- empty state (`!conversation`) → `onModelChange(resolved)` (existing prop; clears the
  pre-selected level), notice; no create, no send.

`models` is gathered inside ChatArea via `useServicesSSE()` + `useEngineCatalogue()`
(`isChatService`) + the existing `openRouterModels` prop + `useProviderModels()`.

**Notice surface** — new local state `slashNotice` in ChatArea, rendered above the
composer next to the existing `runNotice` banner with a close button. Action notices
(switched / unknown / ambiguous / failed) auto-clear after ~6 s (timeout ref); the
bare-`/model` list is sticky (a list unread within 6 s is useless) and stays until the
next send, a conversation change, or the close button. Deliberately *not* `useChat`'s
`runNotice`, which is owned by run lifecycle frames.

**Contracts**

| Input | Result |
|---|---|
| `/model` | notice listing models; nothing sent |
| `/model vllm-qwen` (exact local name) | PUT main_service; notice; not sent |
| `/model anthropic/claude-sonnet-5` (curated OR id) | `openrouter:<id>`; PUT; not sent |
| `/model mistral:mistral-large-latest` (offered provider model) | PUT as-is; not sent |
| `/model openrouter:unoffered/model` | error notice unless it is the current `main_service` |
| `/model Nope` (label, any case) | PUT; not sent — labels are case-insensitive |
| `/model Nope` (label colliding across sources) | ambiguity notice naming the candidates; no PUT |
| `/model nope` | error notice; no PUT; not sent |
| `/modelx`, `hello /model x`, multi-line, or with images | normal send |
| `/model x` in empty-state composer | `onModelChange(x)`; not sent |

Alternatives considered and rejected: intercepting inside `ChatInput` (it owns
attachments/inserts but not conversation context; two parents); server-side
`main_service` validation (changes the API for Android/other clients — out of scope);
composer argument autocomplete (no infrastructure in ChatInput — deferred, non-goal).

## 4. Implementation sequence

| Step | Files / symbols | Behavior | Depends on | Acceptance test |
|---|---|---|---|---|
| 1 | `src/utils/modelSlashCommand.js` (new) + `src/utils/modelSlashCommand.test.js` | pure `parseModelCommand` / `resolveModelRef` / `formatModelList` | — | vitest: table in §3 plus edge cases (`/modelx`, newline, empty arg, embedding service excluded, unoffered exact `openrouter:` string rejected unless it is the current model, ambiguous label) |
| 2 | `src/components/chat/ChatArea.jsx`: hooks for model list, `slashNotice` state, `handleComposerSend` wrapper at both `onSend` sites, notice render | command interception per §3 | step 1 | `ChatArea.test.jsx`: with conversation — `/model other` calls `updateConversation(id, {main_service:'other'})` and not `sendMessage`, shows notice; unknown → no PUT, no send; bare → list notice; empty state → `onModelChange` called, `onCreateAndSend` not called; passthrough cases unchanged |
| 3 | `dashboard/frontend/AGENTS.md` component map (ChatArea row) mentions the slash command | docs only | step 2 | — |

Each step is a reviewable vertical slice; no step depends on a later step's helper.
Implementation branches from fresh `origin/main` per the repo branching rule.

## 5. Verification

- Ran: `npm test -- src/utils/modelSlashCommand.test.js src/components/chat/ChatArea.test.jsx` (68/68),
  full `npm test` in `dashboard/frontend` (964/964), `npm run lint` (clean), production build.
- Backend untouched by the feature and the review fixes — no backend tests applicable.

## 6. Rollout and risks

- Frontend-only, no migration, no server restart; rollback is reverting one branch.
- Risk: server stores any `main_service` string unvalidated until run time — same
  exposure the header selector has today; the slash command validates client-side
  against the offered models, so it never makes this worse.
- Risk: SSE model list still loading when the command runs — resolve yields `null` →
  error notice, nothing sent; acceptable (no silent wrong switch).
- Unknowns: none blocking.

## 7. Status

Implemented on `feat/chat-model-slash-command` (PR #502, base `main`). All §3 decisions
taken as written: stopped chat services included in the match set. PR review findings
addressed in a follow-up commit: failed PUT is named in a notice (MEDIUM 1), exact
`openrouter:`/`<provider>:` strings resolve only when offered or current (MEDIUM 2),
the bare-`/model` list is sticky with a close button (LOW 3), labels match
case-insensitively with an ambiguity notice (LOW 5). Deferred: sharing the `useServicesSSE`
stream between ChatArea and ModelSelector (LOW 4, pre-existing pattern), and letting the
no-default-model empty-state composer send (LOW 6, a product decision about what a plain
send does with no model at all).
