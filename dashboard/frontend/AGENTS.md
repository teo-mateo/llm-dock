# LLM-Dock — React v2 Frontend Guide

Single reference for working in the React v2 web application at
`dashboard/frontend/`. It is the newer UI served under `/v2`; the legacy
vanilla-JS + Jinja2 dashboard (`dashboard/static/`) is "v1" and lives
elsewhere. This file is scoped to the frontend — for the backend, Docker
Compose orchestration, chat runtime, Android client, and operational
playbook read the repo-root `AGENTS.md` (`CLAUDE.md`).

## Overview

A React 19 SPA that manages local LLM inference services and provides a
full chat experience. It talks to the Flask dashboard API on port 3399
(bearer-token auth) and renders:

- **Dashboard** (`/`) — live GPU stats + a services table with start/stop/
  restart/delete, favorites, and a "Rotate default key" action.
- **Service details** (`/services/:name`) — config editor, live logs, and
  metrics tabs.
- **Chat** (`/chat/:conversationId?`, `/chat/project/:projectId`) — the
  largest subsystem: conversations, streaming responses, tool (MCP) calls,
  critiques, spinoffs, and per-project file workspaces.
- **Tools** (`/tools`) — MCP registry editor and default system prompt.
- **Settings** (`/settings`) — theme, chat prompts, OpenRouter model picker,
  TOTP setup.

## Tech Stack & Dependencies

| Layer | Technology |
|-------|-----------|
| Framework | React 19, React DOM 19 |
| Build | Vite 7 (`@vitejs/plugin-react`) |
| Styling | Tailwind CSS 4 (`@tailwindcss/vite`, `@tailwindcss/typography`) |
| Routing | `react-router-dom` 7 (BrowserRouter, `basename="/v2"`) |
| Markdown | `react-markdown` 10 + `remark-gfm`, `remark-math`, `rehype-katex`, `rehype-raw`, `katex` |
| Icons | Font Awesome 6 (loaded from CDN in `index.html`) |
| Fonts | Google Fonts: Archivo (UI), Newsreader (prose), IBM Plex Mono (code) |
| Testing | Vitest 4 + Testing Library (`@testing-library/react`, `jest-dom`), `jsdom`, `vitest-canvas-mock` |
| Lint | ESLint 9, flat config in `eslint.config.js` (`js.configs.recommended` + `eslint-plugin-react-hooks` 7 + `eslint-plugin-react-refresh`), `dist` ignored |

### Key `package.json` scripts

```bash
npm run dev          # `vite` — no server.port is set, so :5173
npm run build        # `vite build` → dist/
npm run lint         # `eslint .`
npm run test         # `vitest run`
npm run test:watch   # `vitest`
npm run preview      # `vite preview` — serves the built dist/
```

## How to Work

### Dev mode

```bash
cd dashboard/frontend
npm install
npm run dev
```

`vite.config.js` sets `base: '/v2/'` and no `server.port`, so the dev server
listens on :5173. Requests do **not** use its `/api` proxy: every client builds
an absolute URL from `API_BASE` (`src/api.js`), which is
`<scheme>://<host>:3399/api` when the page runs on `localhost`/`127.0.0.1`. So
dev needs the Flask dashboard actually up on 3399 and depends on its
`CORS(app)`. In production Flask serves `frontend/dist` under `/v2`
(`dashboard/app.py`), so page and API share an origin.

### Build & lint

```bash
npm run build        # outputs to dist/ (gitignored)
npm run lint         # ESLint over the whole project (`eslint .`)
npm run test         # Vitest (jsdom environment)
```

### Conventions

- **JavaScript (no TypeScript)** — `.jsx` for components, `.js` for
  hooks/services/utils.
- **Functional components + hooks** everywhere. No class components.
- **Tailwind utility classes** for styling; semantic theme tokens via
  `--color-*` CSS variables (see `index.css`).
- **No comments unless they carry real intent** — but this codebase is
  unusually rich in explanatory comments around concurrency/race
  reasoning. Preserve them; they document hard-won fixes.
- **Optimistic updates + revert-on-failure** is the standard pattern for
  mutations (see `useChatPrompts`, `useServicesSSE` favorites).
- **SSE over fetch + ReadableStream** for all streaming (EventSource can't
  send auth headers).
- **Stable identity discipline**: hooks that receive inline callbacks from
  parents hold them behind refs and expose stable wrappers so effects /
  stream callbacks don't re-run every render (see `useChat`'s
  `onConversationUpdatedRef`, `ProjectChatSplit`'s `onDirtyRef`).

### Testing

Tests live next to source (`*.test.jsx` / `*.test.js`). Vitest config
(`vitest.config.js`, separate from `vite.config.js`) uses jsdom and
`src/test/setup.js`, which installs `vitest-canvas-mock` (so `GpuGraph`'s
canvas calls work under jsdom) and `@testing-library/jest-dom/vitest`
matchers. Run a single file:

```bash
npm test -- src/components/chat/ChatArea.test.jsx
```

## Authentication

The React v2 app has **no login screen of its own**. It assumes a valid
session token already exists in `localStorage` under `dashboard_token`
(`TOKEN_KEY` in `api.js`) and sends it as `Authorization: Bearer <token>`
on every request. Getting that token happens in the **legacy v1 dashboard**
(vanilla JS served by Flask): the login page's "password" field is the
`DASHBOARD_TOKEN` from `dashboard/.env`, posted to `POST /api/auth/session`
(or a TOTP code via `POST /api/auth/login`); the response token is stored
under the same `dashboard_token` key.

Key mechanics:

- **Token source & storage** — `localStorage['dashboard_token']` (`TOKEN_KEY`);
  the frontend never mints a token, only reads, refreshes and clears it.
- **Sliding refresh** — `fetchAPI` (`api.js`) reads the `X-TOTP-Token`
  response header on every reply and writes it back to localStorage, so the
  token's 8-hour window keeps sliding while the app is used.
- **401 → `handleAuthFailure()`** — clear the token and full-page-navigate to
  the v1 login page (`?redirect=<current path>`, built by the pure-exported
  `buildLoginRedirectUrl`). A module-level `redirecting` flag makes the bounce
  happen once per page life, since many hooks authenticate on mount and a
  single 401 would otherwise start a redirect storm. `fetchAPI` takes the same
  path when no token exists at all (then throws `Not authenticated`); on 401 it
  throws `Authentication failed`.
- **Every unauthenticated path converges on `handleAuthFailure()`**, not just
  `fetchAPI`: `services/sse.js`, `services/chat.js` (upload/download),
  `services/mcpRegistry.js`, and all three SSE hooks call it on a 401 response.
- **Explicit sign-out is `logout()`** (`api.js`), wired to the sign-out button
  in `Sidebar.jsx`. Unlike `handleAuthFailure` it always navigates.
- **SSE hooks read the token directly** — `useServicesSSE`, `useGpuSSE`,
  `useServiceLogsSSE`, and `services/sse.js` call `getToken()` themselves
  (they use raw `fetch`, not `fetchAPI`). `useServicesSSE` listens for the
  `storage` event on `TOKEN_KEY` and reconnects, but that event fires only for
  a token written by *another* same-origin tab: an in-tab `X-TOTP-Token`
  refresh never restarts a live stream, which is harmless because the header is
  read only at connect time.
- **No backoff anywhere** — all three SSE hooks retry on a fixed
  `RECONNECT_DELAY` of 3 s.
- **Stable error codes** — auth failures surface as `err.message`
  ("Not authenticated" / "Authentication failed"); the UI does not branch on
  these strings except in `ServicesTable`'s connection-dot logic.
- **TOTP in Settings is enrollment, not login.** `components/TOTPSetup.jsx`
  calls `/totp/setup`, `/totp/verify`, `/totp/disable` to configure a
  second factor for the *v1 login flow*. It requires an already-valid token
  and does not sign you in.

## Architecture & Code Map

### Entry & routing

| File | Purpose |
|------|---------|
| `index.html` | HTML shell; anti-FOUC theme script; CDN Font Awesome + Google Fonts; mounts `#root` |
| `src/main.jsx` | Entry: `createRoot`, `StrictMode`, `ThemeProvider`, `BrowserRouter basename="/v2"`, `App` |
| `src/App.jsx` | Root layout: `Sidebar` + `MobileNav` + `Header` + `<Routes>` |
| `src/index.css` | Tailwind entry + full semantic theme token system (`@theme static`), dark/light overrides |
| `vite.config.js` | Vite config: `base: '/v2/'`, sourcemaps, and an `/api` → `:5000` proxy that no request uses (see [Dev mode](#dev-mode)) |
| `vitest.config.js` | Test config: jsdom, setup file |

### Routes (`App.jsx`)

| Path | Component | Purpose |
|------|-----------|---------|
| `/` | `GpuMonitor` + `ServicesTable` | Dashboard |
| `/chat/:conversationId?` | `ChatPage` | Chat (with optional conversation) |
| `/chat/project/:projectId` | `ChatPage` | Project file explorer |
| `/tools` | `ToolsPage` | MCP registry, default prompt |
| `/services/:serviceName/*` | `ServiceDetailsPage` | Config / logs / metrics |
| `/settings` | `SettingsPage` | Theme, prompts, OpenRouter models, TOTP |

### Navigation & layout

| File | Purpose |
|------|---------|
| `components/Sidebar.jsx` | Desktop collapsible sidebar (nav + logo + user); collapsed state persisted |
| `components/MobileNav.jsx` | `md:hidden` drawer nav |
| `components/navItems.js` | Shared nav item list (Services/Chat/Tools/Settings) consumed by both Sidebar and MobileNav so they never drift |
| `components/Header.jsx` | Top bar shell (`hidden md:flex`); renders nothing today — there is no "Back to v1" link |

### API client layer

| File | Purpose |
|------|---------|
| `src/api.js` | `fetchAPI` wrapper: bearer token from localStorage (`dashboard_token`), `X-TOTP-Token` refresh, `handleAuthFailure`/`logout` → v1 login redirect, stable `err.code` for UI branching. `API_BASE` is `<scheme>://<host>:3399/api` on `localhost`/`127.0.0.1` and same-origin `/api` on any other host, so a non-local deployment needs a reverse proxy mapping `/api` to the dashboard |
| `src/utils.js` | `getValue`/`totalValue` (metric access) |
| `src/utils/fence.js` | Fence helpers for markdown/code fences |
| `src/utils/openrouter.js` | Pure helpers for the `openrouter:<model-id>` service-string convention (`isOpenRouterService`, `openRouterModelId`, `serviceNameForModel`, `formatModelLabel`) |
| `src/utils/openrouterModels.js` | Curated-list helpers shared by the picker and its JSON panel: `validateModelsJson`/`validateModels` (mirror of the server rules), `modelsToJson`, `deriveLabel`, `formatPricePerMtok`, `formatContext`, `CONTEXT_PRESETS` |

### Services (per-domain API clients under `src/services/`)

| File | Purpose |
|------|---------|
| `lifecycle.js` | `startService` / `stopService` / `restartService` |
| `sse.js` | `streamChat` — the one SSE stream primitive (fetch + ReadableStream) for send (POST), edit (PUT) and reattach (GET, no body); dispatches typed events `run_started`, `message_saved`, `tool_call`, `tool_call_pending`, `tool_result`, `tool_progress`, `artifact`, `heartbeat`, `run_status`, `parse_warning`, `conversation_updated`, plus `[DONE]` and `error` |
| `chat.js` | Conversations CRUD, projects CRUD, project files (tree/upload/download/read/write/mkdir/move/copy/delete), critique, runs + `cancelActiveRun` |
| `chatPrompts.js` | Saved prompt CRUD + reorder (`/chat/prompts`) |
| `chatSettings.js` | Default system prompt get/put/reset (`/chat/settings/main-system-prompt`) |
| `openrouterModels.js` | Curated OpenRouter model list get/put/reset + `refreshOpenRouterLadders(ids)` (POST `…/openrouter-models/refresh`) — the ladder is server-derived, so the client asks for it rather than editing it |
| `openrouterCatalog.js` | Live OpenRouter catalog get (`/chat/settings/openrouter-catalog`), with `refresh`/`detail` flags |
| `openrouterProviders.js` | Per-provider detail for a batch of model ids (`…/openrouter-catalog/endpoints`, POST); `MAX_PROVIDER_BATCH` mirrors the server cap |
| `mcpRegistry.js` | Registry get/json/put/reload/test; surfaces structured `err.body` validation errors |

### Hooks (`src/hooks/`)

| File | Purpose |
|------|---------|
| `useServicesSSE.js` | **Core services state**: snapshot+delta reducer over `/services/stream` SSE; reconnect on a fixed 3 s delay, token-change handling, optimistic favorite toggle; `sortServices` (open-webui first, favorites, alpha). On mount it also fires a plain `GET /services` so the table paints when the SSE snapshot is slow, skipped once a snapshot arrived (`sseSnapshotReceivedRef`), and reconnects on `visibilitychange` without ever disconnecting on hide |
| `useGpuSSE.js` | GPU stats via `/gpu/stream` SSE |
| `useServiceLogsSSE.js` | Live container logs via `/services/:name/logs/stream`; `snapshot_start/log/stream_end` frames; 2000-line cap; reconnect only on unexpected drops |
| `useServiceDetails.js` | Per-service config fetch + lifecycle actions (start/stop/restart/rename/delete, `setPublicPort`, YAML preview, Open WebUI register/unregister); runtime from shared SSE; `setPublicPort` re-fetches config + refreshes SSE |
| `useServiceMetrics.js` | Polled metrics (`/services/:name/metrics` + `/slots` for llama.cpp); normalizes llama.cpp→vLLM metric names; computes token rates, KV cache, prefix-hit and spec-decode ratios; 60-point history |
| `useChat.js` | **The chat engine hook** — see Chat subsystem below |
| `useConversations.js` | Conversation list (fetches entire list, `limit=-1`), create/remove/rename, `patchConversation` for SSE auto-title |
| `useProjects.js` | Project list CRUD |
| `useChatPrompts.js` | Saved prompts with optimistic create/update/remove/reorder |
| `useCritique.js` | Request/store per-message critiques |
| `useRunningServices.js` | Filters running chat-capable services by name prefix (`llamacpp-`, `ik-`, `vllm-`, `ds4-`, `exl3-`, `PAIR_`), excludes embedding-pooling ones via `kind` |
| `useOpenRouterModels.js` | OpenRouter model list load/save/reset + `refreshLadders(ids)`, which re-derives ladders server-side and replaces `data` wholesale so what a row shows is what the server stored |
| `useOpenRouterCatalog.js` | Live OpenRouter catalog, loaded once on mount; `refresh(true)` is the explicit Refresh |
| `useModelProviders.js` | Provider detail for the catalog rows the picker reports as in view; fetched once per id per session, `retry()` forces a refetch of the ids in view |
| `useMainSystemPrompt.js` | Default system prompt load/save/reset |
| `useRegistry.js` | MCP registry load/save/reload |
| `useResizableWidth.js` | Drag-resize panel width with localStorage persistence + ResizeObserver clamp |
| `useProseClass.js` | Prose/markdown class helper for message rendering |

### Dashboard components (`src/components/`)

| File | Purpose |
|------|---------|
| `GpuMonitor.jsx` | GPU cards: `GpuStats` + `GpuGraph`; keeps 20-point history |
| `GpuStats.jsx` / `GpuGraph.jsx` | Per-GPU stats + canvas history graph |
| `ServicesTable.jsx` | Services table (desktop) + stacked cards (mobile); start/stop/restart/delete/edit/logs, favorites, search, rotate-key modal; engine badges |
| `RotateDefaultKeyModal.jsx` | Rotate-default-API-key flow |
| `GaugesRow.jsx` / `MetricsPanel.jsx` / `TokenSparkline.jsx` / `SpecDecodeBar.jsx` / `RequestStrip.jsx` | Metrics visualizations (GPU gauges, token sparklines, speculative-decoding bar) |
| `ServiceDetailsPage.jsx` | Tabs (config/logs/metrics) + skeleton loading + not-found state |
| `ServiceDetailsHeader.jsx` | Header with rename + lifecycle actions |
| `ServiceConfigPanel.jsx` | Service config form (params editor) |
| `ServiceLogsPanel.jsx` | Live logs viewer |
| `ParameterReference.jsx` | Flag metadata reference + add-flag |
| `SettingsPage.jsx` / `settings/PromptsEditor.jsx` / `TOTPSetup.jsx` | Settings: theme, chat prompts editor, TOTP enrollment |
| `settings/OpenRouterModelsPicker.jsx` | Curated OpenRouter list: live-catalog pane (search, vendor/facet filters, sort, counted "show N non-chat" reveal) + short-list pane (reorder, inline labels, stale/deprecated badges, read-only ladder chips with a per-row re-read) + collapsed JSON panel. Rows carry a provider line (count, names, quantizations, price spread, expandable per-provider uptime/status) once it lands; which rows want one comes from an `IntersectionObserver` on the pane, not from list position |
| `tools/ToolsPage.jsx` | MCP registry UI: server list (built-in/external), details, test panel |
| `tools/RegistryEditor.jsx` | JSON editor for `mcp_servers.json` |
| `tools/DefaultPromptEditor.jsx` | Default system prompt editor |
| `tools/ServerTestPanel.jsx` | Discover tools + run a tool against a server |
| `ThemeSwitcher.jsx` | Theme toggle — cycles below 3 themes, renders a `<select>` at 3+, so adding a theme needs no JSX edit |
| `../contexts/ThemeContext.jsx` | Theme provider + `useTheme` + `AVAILABLE_THEMES`: OS-following first-load-only, persisted override, no-transition swap |

## Chat Subsystem (the big one)

### `hooks/useChat.js` — the engine

Owns all conversation state for one open chat: `conversation`, `messages`,
`critiques`, streaming buffers (`streamingContent`, `streamingReasoning`,
`streamingArtifacts`), `toolEvents`, `pendingToolCalls`, `heartbeat`,
`artifacts`, `streamingParseWarning`, `runNotice`, `error`, and the run-control
flags (`runReady`, `cancelling`).

Exposes `loadConversation`, `sendMessage`, `editMessage`, `deleteMessage`,
`stopStreaming`, `setConversation`, plus `setCritiques`/`setArtifacts` for the
critique panel and delete handling. It is heavily engineered around races:

- **Request sequencing** — `observedConvIdRef` (the *intended* id, claimed
  synchronously before the fetch) plus a monotonic `loadGenRef` ensure a
  late-resolving fetch or a superseded same-id load (StrictMode double-mount,
  A→B→A navigation) never clobbers the intended conversation. `refetchMessages`
  takes an optional `isFresh` predicate re-checked **after** the fetch, because
  the id guard alone cannot order two same-id fetches whose responses arrive
  oldest-last.
- **Optimistic user rows** — `id: 'temp-user'` / `'temp-edit'` replaced on
  `message_saved`. On error, send drops the temp row while edit re-loads the
  conversation, since it had truncated the transcript client-side.
- **Drain phase** — after `message_saved`, the stream stays alive for the
  trailing `conversation_updated` (auto-title). `loadConversation` won't
  abort a draining stream; `liveControllersRef` sweeps detached controllers
  on unmount.
- **Guarded cancellation** — `stopStreaming` cancels the *server* run by
  conversation id via `cancelActiveRun` (so it works before `run_started`
  lands), passing `expectedRunId` = the id captured from `run_started`, falling
  back to `conversation.active_run.id` for a run we returned to. `ChatArea`
  renders Stop only when `runReady` or a returned-to `active_run` exists, so
  there is no unguarded Stop. `cancellingRef`/`cancelling` stay set across both
  the cancel POST **and** its reconcile refetch, which is what makes the early
  no-id stop safe: no new run can be created while an unguarded cancel is in
  flight. The reconcile is required because the user message persisted at run
  creation while the optimistic row is still local — the next send's
  temp-row strip would otherwise erase the stopped prompt.
- **Cancel vs fail rendering** — a cancelled run emits no terminal frame and
  persists no assistant message, so reattach reconciles a silent close in its
  `finally` when no terminal signal was seen; a failed run surfaces either as an
  `error` frame or, if it died while unobserved, via `last_run.status ===
  'failed'` on refetch. The two must not be treated alike.
- **Background-run reattach** — returning to a conversation whose
  `active_run` is still running reattaches via `GET /chat/runs/:id/stream`
  (replay + live tail) through the same handlers as a live send, so no
  optimistic user row is added. `onRunStatus` handles already-terminal runs.
- **Run notice** — `run_started.reasoning_level_note` becomes `runNotice`, and
  a note-less frame clears it so a later run can't inherit the previous
  one's. `ChatArea` renders it above the composer: a level the server dropped is
  otherwise indistinguishable from a model that chose not to think.
- **Stable callbacks** — `onConversationUpdatedRef` wrapper keeps stream
  callbacks identity-stable so `loadConversation` doesn't loop.

### `components/chat/` — chat UI

| File | Purpose |
|------|---------|
| `ChatArea.jsx` | Orchestrates the transcript, composer, model/prompt selectors, critique panel, spinoff window, MCP toggle, the Stop control and the `runNotice` banner |
| `ChatInput.jsx` | Composer card: textarea, image paste/drop and text-file attachments, send, and a `trailing` slot for the control rail. No stop button and no edit UI — Stop is `ChatArea`'s, editing is `MessageBubble`'s |
| `MessageList.jsx` / `MessageBubble.jsx` | Rendered transcript; markdown + KaTeX via `react-markdown`; role styling; inline edit of a user message → `useChat.editMessage` |
| `ArtifactRenderer.jsx` | Artifact card for `svg`/`image`/`code`/`html`: inline render, download, and HTML pop-out wrapped in a script-free shell hosting a sandboxed iframe, so model-authored HTML never runs at the dashboard origin where the bearer token sits in localStorage |
| `ThinkingBlock.jsx` | Collapsible reasoning trace |
| `ToolCallBubble.jsx` / `ToolResultBlock.jsx` | MCP tool call + result display |
| `CopyablePre.jsx` | Copy-to-clipboard code blocks |
| `CritiquePanel.jsx` / `CritiqueButton.jsx` / `CritiqueOverlay.jsx` | Response critique UI |
| `DebugOverlay.jsx` | Conversation viewer behind the header bug icon: raw message objects (content, reasoning, tool args + results, parse warnings, errors) read off the live `messages` state |
| `ModelSelector.jsx` | Choose main/sidekick/model service (local + OpenRouter) |
| `ModelOptions.jsx` | The option list for one of those `<select>`s: local services and curated OpenRouter models as `<optgroup>`s, plus a fallback option when the selected OpenRouter model left the curated list, so a native select never renders blank and the stored value survives an unrelated save |
| `PromptSelector.jsx` | Choose a saved prompt |
| `McpToggle.jsx` | Enable/disable MCP servers for a conversation |
| `ReasoningLevelSelect.jsx` | Per-conversation reasoning-level listbox in the composer rail. Reads the **unfiltered** service list from `useServicesSSE()` (a local ladder rides on the service payload) and `openRouterModels[].reasoning_levels` for a remote one — a status filter would hide the control on exactly the conversations that have a level, and the remote half is empty while `OPENROUTER_API_KEY` is unset. Renders nothing with no ladder and nothing stored; a level the model stopped offering stays visible and clearable, flagged "not offered by this model" and never sent |
| `levelRejection.js` | `isReasoningLevelRejection(err)` — pure test behind ChatPage's create-and-send retry, keyed on `err.code === 'invalid_reasoning_level'`; only a level rejection is worth creating a second conversation for, because any other failure can arrive after the first create succeeded |
| `SpinoffWindow.jsx` / `SpinoffTaskbar.jsx` | Spinoff conversation UI |
| `ChatSidebar.jsx` | Conversation tree grouped by project; rename/delete/select-all, shift-click range selection, bulk move/delete; active-run spinner |
| `SidebarSplit.jsx` | Resizable chat sidebar wrapper |
| `ContextMenu.jsx` / `TextContextMenu.jsx` | Context menus |
| `formatDrift.js` | Format-drift patterns mirrored from `FORMAT_DRIFT_PATTERNS` in `dashboard/chat/llm_proxy.py` — same kinds, same priorities; detection also runs client-side so conversations predating the `parse_warning` column still surface the chip |
| `pendingFlush.js` | Empty-state composer flush decision helper |
| `FormatDriftChip.jsx` | Drift indicator chip |

### Projects feature

| File | Purpose |
|------|---------|
| `ChatPage.jsx` | Route owner: resolves the effective project (walks the parent chain for spinoffs), renders `ProjectChatSplit` or `ProjectPage`, guards navigation away from a dirty editor, queues the empty-state first message (`pendingFlush.js`) and retries `create` without a reasoning level on a 400 (`levelRejection.js`) |
| `ProjectChatSplit.jsx` | Resizable file-explorer strip + chat; editor overlay; dirty tracking |
| `ProjectExplorerPane.jsx` | Read-mostly file tree for the chat split |
| `ProjectPage.jsx` | Full standalone explorer: DnD, cut/copy/paste, breadcrumbs, context menu |
| `ProjectFileEditor.jsx` | Text editor with dirty tracking, Ctrl+S save, optimistic concurrency (base revision SHA256 prefix; 409 conflict → reload or force-overwrite) |
| `projectTree.jsx` | Recursive `TreeFile`/`TreeDir` components |
| `projectTreeUtils.js` | Pure helpers (`findNode`, `listDir`, `parentDir`, `ancestorsOf`) |

## Theme System (`index.css`)

- `@theme static` declares the full semantic token set: surfaces
  (`--color-app`, `--color-surface`, …), foreground (`--color-fg*`), borders,
  state colors, engine badges, chart colors. `static` keeps every token in the
  built CSS even when nothing references it yet, so consumers can read them as
  runtime `var(--…)`.
- Two layers, only one of them themed: the `--color-<role>` tokens above are
  overridden per theme, while the #29 brand-fixed layer (the gray ramp, accent,
  critique, mcp, spinoff, error) is identical in both. Re-theming a brand-fixed
  hue is the change that breaks contrast claims in the token block.
- Dark is the `@theme` default; `[data-theme="light"]` overrides only the
  variables. The `[data-theme="dark"]` rule is intentionally empty — kept for
  symmetry.
- `index.html` has an anti-FOUC inline script that sets `data-theme` (from
  `localStorage['dashboard_theme']`, else `prefers-color-scheme`) before the
  stylesheet and React mount; `ThemeContext` re-asserts it and swaps with a
  `theme-swap-no-transitions` class plus a forced reflow so no cross-fade is
  painted, setting `style.colorScheme` alongside.
- OS-following is **first-load-only** — once the user picks a theme it's
  persisted and the OS is no longer followed (no "system" mode, and
  `AVAILABLE_THEMES` deliberately has no such entry; there is no
  `matchMedia` change listener).
- `useProseClass` is the consumer-side rule: `prose` always, `prose-invert`
  only in dark. Never hand-write the `prose-invert` ternary in a component.

## Gotchas

- **The `vite.config.js` `/api` → `:5000` proxy is dead config** — every client
  prefixes `API_BASE`, which is `:3399` on localhost, so dev traffic never
  reaches the proxy. The dashboard must be running on 3399 for dev to work; the
  proxy only matters if someone starts issuing relative `/api` URLs.
- **Auth token** is `dashboard_token` in localStorage. `fetchAPI` refreshes
  `X-TOTP-Token` and, on 401 or a missing token, `handleAuthFailure()` clears it
  and navigates to the v1 login page once. SSE hooks read the token directly and
  reconnect on token changes via the `storage` event, which another tab must
  have fired. There is no login UI in this app — see
  [Authentication](#authentication).
- **One `/services/stream` connection per `useServicesSSE()` consumer** — the
  hook has no shared provider, so `ServicesTable`, `useServiceDetails`,
  `useRunningServices` and `ReasoningLevelSelect` each hold their own fetch and
  their own reducer state. Adding a consumer is not free, and two consumers can
  briefly disagree (e.g. an optimistic favorite in one, not the other).
- **SSE requires fetch, not EventSource** — auth headers can't be sent via
  EventSource. All stream hooks use `fetch` + `ReadableStream`.
- **`useChat` race discipline is load-bearing.** Do not "simplify" the
  refs/generations — they fix real races (StrictMode double-mount, A→B→A
  navigation, stale fetch clobbering).
- **Navigation is not cancellation** — closing the SSE stream unsubscribes
  the observer but the backend run continues and persists. Only `stopStreaming`
  cancels the server run.
- **A cancelled run emits no terminal frame** — don't wait for a closing
  frame that never comes; the `finally` reconcile handles it.
- **`err.code` over message text** — the UI branches on stable machine
  codes (e.g. `revision_conflict`, `already_exists`, `invalid_reasoning_level`),
  never on message strings.
- **Never synthesize a reasoning level client-side.** The offered list is
  exactly `service.reasoning_levels` (local) or
  `openRouterModels[].reasoning_levels` (remote), both parsed server-side; the
  server rejects an undeclared one with 400 `invalid_reasoning_level` rather
  than the UI ever offering it. The two loss paths have different handling: a
  level rejected at *create* time is caught by `levelRejection.js` and retried
  without it, a level dropped at *run* time is reported only by `runNotice`.
- **The OpenRouter catalog and provider detail are display-time only** —
  neither is persisted, so a stored shortlist cannot drift with the catalogue.
  A save does round-trip each stored entry's `reasoning_levels`, but the server
  derives ladders itself and a request body cannot set one (the `ladders` map is
  the only write path), which is why the picker shows the ladder read back from
  the response rather than one it computed. Provider rows come from
  `useModelProviders(visibleIds)`, capped at `MAX_PROVIDER_BATCH` (60) ids —
  beyond the cap they are skipped, not chunked — and an id the server reports in
  `missing` is retried with the next in-view batch.
- **Stable identity** — any hook receiving inline callbacks from a parent
  should hold them behind a ref and expose a stable wrapper, or effects will
  re-run on every render (streaming deltas re-render constantly).
- **Optimistic mutations must revert on failure** — see `useChatPrompts`
  and `useServicesSSE` favorites.
- **`dist/` is gitignored** — rebuild before deploying.
- **`useRunningServices` returns only chat-capable services** — embedding-pooling
  services are filtered out of the chat composer's default model.
