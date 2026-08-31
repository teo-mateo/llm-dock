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
| Testing | Vitest 4 + Testing Library (`@testing-library/react`, `user-event`, `jest-dom`), `jsdom`, `vitest-canvas-mock` |

### Key `package.json` scripts

```bash
npm run dev          # Vite dev server; proxies /api → http://localhost:5000
npm run build        # Production build → dist/
npm run lint         # ESLint over the whole project (`eslint .`; react-hooks + react-refresh rules)
npm run test         # Vitest run
npm run test:watch   # Vitest watch
npm run preview      # Serve the built dist/
```

## How to Work

### Dev mode

```bash
cd dashboard/frontend
npm install
npm run dev
```

Vite serves on the port printed by Vite and proxies `/api` to Flask on
`:5000`. The app expects a Flask backend on the same host; in production
the built `dist/` is served by Flask under `/v2`.

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
(`vitest.config.js`) uses jsdom + `src/test/setup.js`. Run a single file:

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

- **Token source & storage** — `localStorage['dashboard_token']`; the
  frontend never creates it itself, only reads/refreshes/clears it.
- **Sliding refresh** — `fetchAPI` (`api.js`) reads the `X-TOTP-Token`
  response header on every reply and writes it back to localStorage, so the
  token's 8-hour window keeps sliding while the app is used.
- **Logout on 401** — `fetchAPI` removes the token on any 401, which
  effectively logs the user out (the next request fails with "Not
  authenticated"). There is no redirect to a login page — the user must
  re-authenticate in the v1 dashboard.
- **SSE hooks read the token directly** — `useServicesSSE`, `useGpuSSE`,
  `useServiceLogsSSE`, and `services/sse.js` call `getToken()` themselves
  (they use raw `fetch`, not `fetchAPI`). `useServicesSSE` listens for the
  `storage` event on `TOKEN_KEY` and reconnects when the token changes.
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
| `src/App.css` | (legacy/minimal) |
| `src/index.css` | Tailwind entry + full semantic theme token system (`@theme static`), dark/light overrides |
| `vite.config.js` | Vite config: `base: '/v2/'`, `/api` proxy → `:5000`, sourcemaps |
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
| `components/navItems.jsx` | Shared nav item list (Services/Chat/Tools/Settings) consumed by both Sidebar and MobileNav so they never drift |
| `components/Header.jsx` | Top bar with "Back to v1" link |

### API client layer

| File | Purpose |
|------|---------|
| `src/api.js` | `fetchAPI` wrapper: bearer token from localStorage (`dashboard_token`), `X-TOTP-Token` refresh, 401 → logout, stable `err.code` for UI branching; `API_BASE` resolves to `:3399/api` on localhost else `/api` |
| `src/utils.js` | `getValue`/`totalValue` (metric access), `timeAgo` |
| `src/utils/fence.js` | Fence helpers for markdown/code fences |
| `src/utils/openrouter.js` | Pure helpers for the `openrouter:<model-id>` service-string convention (`isOpenRouterService`, `openRouterModelId`, `serviceNameForModel`, `formatModelLabel`) |
| `src/utils/openrouterModels.js` | Curated-list helpers shared by the picker and its JSON panel: `validateModelsJson`/`validateModels` (mirror of the server rules), `deriveLabel`, `formatPricePerMtok`, `formatContext` |

### Services (per-domain API clients under `src/services/`)

| File | Purpose |
|------|---------|
| `lifecycle.js` | `startService` / `stopService` / `restartService` |
| `sse.js` | `streamChat` — raw SSE chat stream parser (fetch + ReadableStream); dispatches typed events (`run_started`, `message_saved`, `tool_call`, `tool_result`, `artifact`, `heartbeat`, `run_status`, `conversation_updated`, …) |
| `chat.js` | Conversations CRUD, projects CRUD, project files (tree/upload/download/read/write/mkdir/move/copy/delete), critique, runs + `cancelActiveRun` |
| `chatPrompts.js` | Saved prompt CRUD + reorder (`/chat/prompts`) |
| `chatSettings.js` | Default system prompt get/put/reset (`/chat/settings/main-system-prompt`) |
| `openrouterModels.js` | Curated OpenRouter model list get/put/reset |
| `openrouterCatalog.js` | Live OpenRouter catalog get (`/chat/settings/openrouter-catalog`), with `refresh`/`detail` flags |
| `mcpRegistry.js` | Registry get/json/put/reload/test; surfaces structured `err.body` validation errors |

### Hooks (`src/hooks/`)

| File | Purpose |
|------|---------|
| `useServicesSSE.js` | **Core services state**: snapshot+delta reducer over `/services/stream` SSE; reconnect, token-change handling, optimistic favorite toggle; `sortServices` (open-webui first, favorites, alpha) |
| `useGpuSSE.js` | GPU stats via `/gpu/stream` SSE |
| `useServiceLogsSSE.js` | Live container logs via `/services/:name/logs/stream`; `snapshot_start/log/stream_end` frames; 2000-line cap; reconnect only on unexpected drops |
| `useServiceDetails.js` | Per-service config fetch + lifecycle actions; runtime from shared SSE; `setPublicPort` re-fetches config + refreshes SSE |
| `useServiceMetrics.js` | Polled metrics (`/services/:name/metrics` + `/slots` for llama.cpp); normalizes llama.cpp→vLLM metric names; computes token rates, KV cache, prefix-hit and spec-decode ratios; 60-point history |
| `useChat.js` | **The chat engine hook** — see Chat subsystem below |
| `useConversations.js` | Conversation list (fetches entire list, `limit=-1`), create/remove/rename, `patchConversation` for SSE auto-title |
| `useProjects.js` | Project list CRUD |
| `useChatPrompts.js` | Saved prompts with optimistic create/update/remove/reorder |
| `useCritique.js` | Request/store per-message critiques |
| `useRunningServices.js` | Filters running chat-capable services (llama.cpp/vLLM/DS4/PAIR_), excludes embedding-pooling ones; `kind: 'all'` for the dashboard |
| `useOpenRouterModels.js` | OpenRouter model list load/save/reset |
| `useOpenRouterCatalog.js` | Live OpenRouter catalog, loaded once on mount; `refresh(true)` is the explicit Refresh |
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
| `settings/OpenRouterModelsPicker.jsx` | Curated OpenRouter list: live-catalog pane (search, vendor/facet filters, sort, counted "show N non-chat" reveal) + short-list pane (reorder, inline labels, stale/deprecated badges) + collapsed JSON panel |
| `tools/ToolsPage.jsx` | MCP registry UI: server list (built-in/external), details, test panel |
| `tools/RegistryEditor.jsx` | JSON editor for `mcp_servers.json` |
| `tools/DefaultPromptEditor.jsx` | Default system prompt editor |
| `tools/ServerTestPanel.jsx` | Discover tools + run a tool against a server |
| `ThemeSwitcher.jsx` | Theme toggle |
| `contexts/ThemeContext.jsx` | Theme provider: OS-following first-load-only, persisted override, no-transition swap |

## Chat Subsystem (the big one)

### `hooks/useChat.js` — the engine

Owns all conversation state for one open chat: `conversation`, `messages`,
`critiques`, streaming buffers (`streamingContent`, `streamingReasoning`),
`toolEvents`, `pendingToolCalls`, `heartbeat`, `artifacts`,
`streamingParseWarning`, `error`, and the run-control flags (`runReady`,
`cancelling`).

Exposes `loadConversation`, `sendMessage`, `editMessage`, `deleteMessage`,
`stopStreaming`, `setConversation`. It is heavily engineered around races:

- **Request sequencing** — `observedConvIdRef` + a monotonic `loadGenRef`
  ensure a late-resolving fetch or a superseded same-id load (StrictMode
  double-mount, A→B→A navigation) never clobbers the intended conversation.
- **Optimistic user rows** — `id: 'temp-user'` / `'temp-edit'` replaced on
  `message_saved`; removed on error.
- **Drain phase** — after `message_saved`, the stream stays alive for the
  trailing `conversation_updated` (auto-title). `loadConversation` won't
  abort a draining stream; `liveControllersRef` sweeps detached controllers
  on unmount.
- **Cooperative cancellation** — `stopStreaming` cancels the *server* run by
  conversation id via `cancelActiveRun`, passing a captured `expected_run_id`
  guard so a late cancel can't kill a newer run. `cancellingRef` blocks
  send/edit during the cancel window.
- **Background-run reattach** — returning to a conversation whose
  `active_run` is still running reattaches via `GET /chat/runs/:id/stream`
  (replay + live tail). `onRunStatus` handles already-terminal runs.
- **Stable callbacks** — `onConversationUpdatedRef` wrapper keeps stream
  callbacks identity-stable so `loadConversation` doesn't loop.

### `components/chat/` — chat UI

| File | Purpose |
|------|---------|
| `ChatArea.jsx` | Orchestrates the transcript, composer, model/prompt selectors, critique panel, spinoff window, MCP toggle |
| `ChatInput.jsx` | Composer: textarea, image paste/attach, send/stop, edit mode |
| `MessageList.jsx` / `MessageBubble.jsx` | Rendered transcript; markdown + KaTeX via `react-markdown`; role styling |
| `ThinkingBlock.jsx` | Collapsible reasoning trace |
| `ToolCallBubble.jsx` / `ToolResultBlock.jsx` | MCP tool call + result display |
| `CopyablePre.jsx` | Copy-to-clipboard code blocks |
| `CritiquePanel.jsx` / `CritiqueButton.jsx` / `CritiqueOverlay.jsx` | Response critique UI |
| `DebugOverlay.jsx` | Dev overlay for streaming internals |
| `ModelSelector.jsx` | Choose main/sidekick/model service (local + OpenRouter) |
| `PromptSelector.jsx` | Choose a saved prompt |
| `McpToggle.jsx` | Enable/disable MCP servers for a conversation |
| `SpinoffWindow.jsx` / `SpinoffTaskbar.jsx` | Spinoff conversation UI |
| `ChatSidebar.jsx` | Conversation tree grouped by project; rename/delete/select-all, shift-click range selection, bulk move/delete; active-run spinner |
| `SidebarSplit.jsx` | Resizable chat sidebar wrapper |
| `ContextMenu.jsx` / `TextContextMenu.jsx` | Context menus |
| `formatDrift.js` | Format-drift detection (markdown vs. saved view) |
| `pendingFlush.js` | Empty-state composer flush decision helper |
| `toolCallUtils.js` | Tool-call rendering helpers |
| `FormatDriftChip.jsx` | Drift indicator chip |

### Projects feature

| File | Purpose |
|------|---------|
| `ChatPage.jsx` | Resolves effective project (walks parent chain for spinoffs), renders `ProjectChatSplit` or `ProjectPage`; dirty-editor discard guards on navigation |
| `ProjectChatSplit.jsx` | Resizable file-explorer strip + chat; editor overlay; dirty tracking |
| `ProjectExplorerPane.jsx` | Read-mostly file tree for the chat split |
| `ProjectPage.jsx` | Full standalone explorer: DnD, cut/copy/paste, breadcrumbs, context menu |
| `ProjectFileEditor.jsx` | Text editor with dirty tracking, Ctrl+S save, optimistic concurrency (base revision SHA256 prefix; 409 conflict → reload or force-overwrite) |
| `projectTree.jsx` | Recursive `TreeFile`/`TreeDir` components |
| `projectTreeUtils.js` | Pure helpers (`findNode`, `listDir`, `parentDir`, `ancestorsOf`) |

## Theme System (`index.css`)

- `@theme static` declares the full semantic token set: surfaces
  (`--color-app`, `--color-surface`, …), foreground (`--color-fg*`), borders,
  state colors, engine badges, chart colors.
- Dark is the default; `[data-theme="light"]` overrides only the variables.
- `index.html` has an anti-FOUC inline script that sets `data-theme` before
  React mounts; `ThemeContext` re-asserts it and swaps without transitions.
- OS-following is **first-load-only** — once the user picks a theme it's
  persisted and the OS is no longer followed (no "system" mode).

## Gotchas

- **`/api` proxy points at `:5000`** in dev (`vite.config.js`). If the Flask
  backend runs on 3399, the dev proxy must be updated, or use the built app
  served by Flask.
- **Auth token** is `dashboard_token` in localStorage. `fetchAPI` refreshes
  `X-TOTP-Token` and logs out on 401. SSE hooks read the token directly and
  reconnect on token changes via the `storage` event. There is no login UI
  in this app — see [Authentication](#authentication).
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
  codes (e.g. `revision_conflict`), never on message strings.
- **Stable identity** — any hook receiving inline callbacks from a parent
  should hold them behind a ref and expose a stable wrapper, or effects will
  re-run on every render (streaming deltas re-render constantly).
- **Optimistic mutations must revert on failure** — see `useChatPrompts`
  and `useServicesSSE` favorites.
- **`dist/` is gitignored** — rebuild before deploying.
- **`useRunningServices` defaults to `kind: 'chat'`** — embedding-pooling
  services are filtered out of the chat composer's default model; pass
  `kind: 'all'` for the dashboard.
