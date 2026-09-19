# Share-a-URL → summarize it (issue 255)

**Issue:** #255 `[mobile app] Make shared URLs quick and reliable to summarize`
**Baseline:** `main` at `2d5d65e` (post-PR-#254). Working tree clean at plan time.
**Owner surfaces:** Android app (`android/`), dashboard chat MCP read path (`dashboard/chat/`).

Evidence for every claim below is `Source inspected` at that revision unless a row says
otherwise. No tests, builds, or device runs were performed for this plan — §5 lists what
must be run.

---

## 1. Goal and scope

Share a web page from any app, tap one thing, and get a summary grounded in the page.
Everything that today needs a conversation, a model, a tool toggle and a written
instruction has to collapse into that one tap, **and** the app must never present a
guessed summary as a real one.

| Req | Requirement (from the issue) |
|---|---|
| R1 | The summarize action is offered for shared text containing an HTTP(S) URL — bare URL or URL inside prose/title |
| R2 | Ordinary sharing is unchanged: content still lands staged in a composer, unsent |
| R3 | A summarize turn is never submitted unless URL retrieval was available for it |
| R4 | Config failure, fetch failure, and empty-fetch are each reported plainly, never replaced by a guessed summary |
| R5 | A missing/stopped remembered model leads to a model choice that keeps the URL and the intent |
| R6 | Recoverable failures leave the prepared message intact for a retry |
| R7 | Navigation, recreation or process death never submit the same turn twice |
| R8 | No avoidable setup latency on the success path |
| R9 | Nothing assumes a specific tool-server id; installs with no retrieval tool are handled |
| R10 | Image/file shares do not see the URL-specific action |

**Non-goals:** shared images/files, the web frontend, changing ordinary share behaviour,
improving any fetcher's extraction quality, notifications, starting stopped containers.

**Constraint conflict, stated not smoothed over.** `android/docs/Plan_TOC.md` §2 rule
**R-A** says no feature may need new server code. Issue 255 explicitly permits backend
changes ("allowed if they provide the cleanest and most reliable implementation") while
listing a new endpoint as *not required*. This plan proposes **one additive change to an
existing endpoint** (§3.2) because the alternative — guessing which configured MCP server
can read a URL from its display name — cannot satisfy R3/R9. Precedent for relaxing R-A
for a phone feature exists: F15's reasoning-level backend shipped in PR #128. If R-A is
held absolutely instead, §3.7's client-only fallback is the only honest design and R9
degrades to "feature hidden on installs whose tool names don't say what they do".

---

## 2. Verified current behaviour

### 2.1 The share path today (F14, `[DONE]`)

| Path | Entry | State owner | Final consumer | Note |
|---|---|---|---|---|
| Share arrives | `MainActivity.stageShareIfAny` (`MainActivity.kt:91`) | `SharedDraftStore.stage` | `ShareTargetScreen` | parses at intent time; the `content://` grant dies with the activity |
| Classify | `SharedKindParser.classify` (`SharedDraft.kt`) | same | `StagedShare(text/attachments/error)` | `Text` / `Image` / `TextFile` / `Unsupported`; `foldTitle` only for a bare link (`Regex("https?://\\S+")`) |
| Picker | `Destinations.SHARE_PICKER` → `ShareTargetViewModel` | `ConversationsRepository.list()` (`limit=-1&unfiled=true`) | row tap → `reassign` | `AppNavHost.kt:81` navigates here for any non-null pending share |
| Pick a row | `AppNavHost.kt:240` | `SharedDraftStore.reassign` | `ThreadViewModel.load` | text → `DraftStore`, attachments → `cacheDir/shared-drafts/conv_<id>/n.txt`, pending cleared |
| New chat from share | `NEW_CHAT` → `NewChatViewModel.create` → `onConversationCreated` (`AppNavHost.kt:309`) | same | same | `reassign(id)` then navigate, `popUpTo(SHARE_PICKER)` |
| Send | `ThreadViewModel.send` (`ThreadViewModel.kt:216`) | composer state | `POST …/messages` SSE | clears draft + attachments, `restoreOnEarlyFailure` puts text back if no frame arrived |

`AppNavHost.kt:81` re-navigates to the picker whenever a pending share exists on disk —
so a flow that leaves the pending record in place **is** the app's existing resume
mechanism.

### 2.2 What the send path will and will not honour

- `POST /api/chat/conversations/<id>/messages` reads `conv.mcp_servers_json` from the
  **stored row** (`chat/routes.py:1026`) and builds the MCP manager from it
  (`_mcp_for_conversation`, `routes.py:225`; read at `routes.py:1031`). There is **no
  per-request tool override**.
  ⇒ Tools must be on the conversation *before* the send.
- `POST /api/chat/conversations` accepts `main_service` (required), `title`, `prompt_id`,
  `main_system_prompt`, `reasoning_level`, `sampling_params` (`routes.py:663`), and does
  **not** accept tools — hence `ConversationsRepository.setMcpServers` as a second call,
  and `NewChatViewModel.applyTools`/`ToolsFailure` as the existing failure surface.
- `db.update_conversation` allowlist includes `mcp_servers_json` (`chat/db.py:457`).
- Auto-title fires **only** while `title == "New Conversation"` (`chat/runtime.py:52`) ⇒
  a summarize thread must not set `title` if it wants a generated title.
- One active run per conversation, enforced atomically in `create_run_with_user_message`;
  a second send is a 409 and the user message is rolled back (`routes.py:948`).
- `GET /api/chat/mcp-servers` → `mcp_config.list_enabled()` →
  `{id,name,description,icon}` only, filtered by `_chat_available` (`chat/mcp_config.py:259`),
  which already hides stdio entries whose command is missing precisely to avoid *"fabricated
  'I used the tool' answers"*. **No tool names are exposed anywhere** on that payload;
  `GET /api/chat/mcp-registry` adds paths/errors but still no tools; tool names are only
  visible via the dashboard-only `POST /api/chat/mcp-registry/test` with `tool_name: null`
  (`mcp_admin_routes.py:156`, 5s `DISCOVER_TIMEOUT`, returns `parameters`).
- Tool discovery is real work: `MCPClientManager.get_tools` spawns the server, 30s timeout,
  results memoized in `_tools_cache`, failures **not** cached (`chat/mcp_client.py:112`).
  `run_with_timeout(coro, timeout)` is already public for bounded one-shot probes.
- Tool failures are visible to the user: a tool card renders `name/arguments/result` for
  both live (`StreamingToolCall`) and persisted (`ToolCallRecord`) calls
  (`ThreadMessages.kt:158,227`), and `mcp_manager.call_tool` errors come back as the tool
  result text the model sees.

### 2.3 What exists on this machine (probe, not assumption)

`dashboard/mcp_servers.json` (machine-local) enables `websearch`, `webfetch`,
`browser-fetch` (stdio) and `ragflow` (http). Source-inspected tool surfaces:
`webfetch` exposes `fetch_readable/fetch_markdown/fetch_txt/fetch_json`, each
`(url: str, headers?, max_length?, start_index?)`
(`ai-toolbox/mcp/webfetch-mcp/src/webfetchmcp/server.py:202-270`); `browser-fetch`
exposes `screenshot_page(url, …)` (`browser_fetch_mcp/src/browser_fetch_mcp/server.py:83`).
`websearch`'s tool takes `query`. **A tool that takes a `url` string parameter is the
capability we need, and it is visible in the MCP `inputSchema`** — the ids themselves are
not a usable signal.

---

## 3. Design

### 3.1 One sentence

A URL-bearing share grows one primary action in the picker header; tapping it resolves a
model, creates a fresh conversation, puts a URL-capable fetcher on it, writes a
single-use "send this" claim next to the conversation, and opens the thread, which fires
the turn exactly once through the existing send path.

### 3.2 Capability: how the phone knows a page *can* be read

Additive, opt-in, on the endpoint the app already calls:

```
GET /api/chat/mcp-servers                 → {"servers": [...] }                    # byte-identical to today
GET /api/chat/mcp-servers?probe=url-fetch → {"servers": [...],
                                              "url_fetch": {
                                                "available": true,
                                                "servers": [{"id": "webfetch",
                                                             "name": "WebFetch",
                                                             "tools": ["fetch_readable", "fetch_markdown", …]}],
                                                "failures": [{"id": "browser-fetch", "error": "timed out after 5s"}]
                                              }}
```

Rules, in this order:

1. Start from `list_enabled()` — disabled entries and stdio entries with a missing
   command are already out.
2. **Cheap candidate filter** on `(id + name + description).lower()` against
   `{fetch, url, browse, web, page, readable}` — narrows what gets spawned.
   (Verified against §2.3: `webfetch` ✓, `browser-fetch` ✓, `websearch` ✓ (probed, then
   rejected), `ragflow` ✗ (never spawned).)
3. **Authoritative test:** the server's `tools/list` contains ≥1 tool whose
   `inputSchema.properties.url` is a `string`. Name heuristics never decide.
4. Rank servers: a url-taking tool whose description mentions
   `markdown|readable|text|content|article` first. Enabling is per **server**, not per
   tool — that granularity does not exist in the backend, so `browser-fetch` alone would
   enable `screenshot_page` too; the prepared message then asks for page *text*, and a
   screenshot-only result falls into R4's "no useful content" path.
5. Bounded discovery: reuse `_tools_cache` when warm, otherwise
   `run_with_timeout(_discover_tools(cfg, id), 5)`. Failures go to `failures`, never
   cached, never fatal.

New pure module `dashboard/chat/url_retrieval.py`: `candidates(servers)`,
`is_url_fetcher(tool)`, `rank(servers_with_tools)` — no I/O, so the rules are unit-tested
without spawning anything. New manager method `discover_bounded(server_id, timeout)`;
`mcp_admin_routes.test_mcp_registry` keeps its current private access untouched (§3.7 of
its own file is the place to migrate it later, not this change).

Web parity (R-B): `/v2` never sends the param, so it sees today's payload
(`McpToggle.jsx:9`). One row is added to `Plan_TOC.md` §5: the same path, `?probe=url-fetch`.

### 3.3 The prepared message, and where the honesty contract lives

Owned by one pure builder, `feature/share/SummarizeMessage.kt`:

```
Summarise this page.

<url>

Use the available URL-fetching tool to read the page first, then summarise what the
fetched content actually says. If the fetch fails, is blocked, or returns nothing useful,
say exactly which of those happened and stop — do not summarise from the URL, the site
name, or prior knowledge.
```

- The URL appears verbatim, one occurrence, no surrounding fences.
- No server id or tool name is ever written into the text (R9): the backend's own
  `tool_hint` injection (`mcp_registry.get_tool_hints`, applied because the server is
  enabled) tells the model which tool it has.
- The contract lives in the **user turn**, not the system prompt: it stays visible in the
  transcript, and overriding `main_system_prompt` would replace the operator's configured
  default (`chat_settings.json`) — a side effect the issue does not ask for.
- No settings surface in v1. The issue allows one; "sensible defaults" plus scope
  discipline says ship the default and let a later issue add overrides.

**Where each failure is reported** (this is the design's sharpest edge, and it narrows one
acceptance criterion deliberately):

| Failure | Point of detection | Where the user sees it | Why not in the conversation |
|---|---|---|---|
| No URL-capable tool configured | probe `available: false` | picker header, action absent + reason line | No conversation is created; posting a chat message to announce "I can't do this" would be a fabricated turn |
| Candidate servers listed but discovery failed | probe `failures` | picker header, names + error, "check Tools → Test" | same |
| Tools `PUT` failed after create | `ToolsFailure` | sheet's existing Retry/Open-anyway surface; no auto-send | R3: no tools ⇒ the turn would be a guess |
| Model stopped between resolve and send | failed run | thread: run-failed `actionError` + transcript | the turn *was* legitimately submitted |
| Fetch failed / empty page | tool result → model obeys the contract | transcript tool card + the assistant's stated failure | only expressible inside the run |

The issue's wording ("the conversation must say so clearly") is taken literally for the
last two rows and *intended* for the first three, where creating a thread to hold an error
message would be the worse product. Recorded here rather than buried in the feature file.

### 3.4 State machine, and the at-most-once argument (R7)

One durable record per share, in `SharedDraftStore` next to `pending.json`:

```
conv_<id>.autosend.json   # prepared message, atomic tmp+rename, consume-once
```

Sibling file, **not** inside `conv_<id>/` — `saveAttachments` deletes every file in that
directory (`SharedDraftStore.kt:61-64`), which would eat the claim.

```
[pending share] --tap Summarize--> create conv --> PUT tools --> write claim + clear pending
     --> navigate(thread) --> ThreadViewModel.load() takes claim (delete-first) --> send()
```

- **At most one turn:** the claim is written once, deleted before the `POST` is issued, and
  the pending share is cleared in the same call that writes it. There is no second reader.
- **Die between create and PUT:** nothing was sent; the pending share is still on disk, so
  `AppNavHost.kt:81` brings the picker back and a second tap creates a *second* (first-use)
  conversation. One turn, one orphan empty thread. Accepted and stated; the alternative is
  a resume-by-plan-id store, which is more machinery than the guarantee is worth.
- **Die with the claim written:** on next launch the claim survives; the next
  `load()` of that thread fires it once. F14-R5 already proves this storage shape
  survives force-stop.
- **Die mid-`POST`:** claim is gone, so nothing re-fires; the server-side run continues
  and F09 reattach shows it.
- **Recoverable failure (R6):** auto-send goes through the existing `send()` →
  `collectRun(restoreOnEarlyFailure=…)` path, so a pre-frame failure restores the *prepared
  message* into the composer and re-saves it as the draft (`ThreadViewModel.kt:644`), and
  the user taps Send by hand. Claim stays spent — a retry is an explicit user act.
- **Double tap / recomposition:** `sending`/`canSend` plus a one-shot `autoSendFired` flag
  on the ViewModel. A brand-new conversation cannot hold an active run, so a 409 on this
  path means a client bug, and is displayed rather than retried.

### 3.5 Model resolution (R5) without a second owner

`NewChatViewModel.load()` already does remembered-model resolution
(`NewChatViewModel.kt:124-160`): preselect beats remembered beats nothing, local must be
running else `rememberedModelUnavailable = true`, OpenRouter is never an allowlist. That
block moves **unchanged in behaviour** into `feature/modelpicker/RememberedModelResolver.kt`
(pure: `resolve(rememberedRaw, localServices, remoteModels, preselected)` →
`Resolved(option)` | `Unavailable(raw)` | `NoneSelected`), called by both
`NewChatViewModel` and the new coordinator. Two copies of that ladder would drift, and
the summarize path must agree with the sheet it falls back to.

Then:

- **resolved & running** → direct path, no sheet (R8: one tap, zero detours).
- **unavailable / none remembered** → navigate to `NEW_CHAT` in summarize mode
  (`Destinations.newChatSummarize()`), where the sheet shows the model row with
  "remembered model unavailable" exactly as F03-R1 criterion 4 already does, pre-selects
  the fetched servers, relabels Start → "Summarize", and refuses Start if the URL-capable
  server got untoggled. The URL and intent ride in a `SummarizeContext` handed to the
  ViewModel, so nothing is lost while choosing (R5).
- Starting a stopped container is **not** offered here: F11 owns it, and the issue asks
  for a model choice, not a warm boot.

### 3.6 Latency (R8)

On `ShareTargetViewModel.refresh()` with a URL-bearing share, fire three reads together:
`GET /api/services`, `GET /api/chat/mcp-servers?probe=url-fetch`, `preferences.lastModel()`.
By the time a finger reaches the button the tap costs one `POST`, one `PUT`, one claim
write and a navigation — no re-read of anything the header already needed. No container
start, no compose rebuild, no restart: a ladder/tools edit needs neither
(`metadata-changed` semantics unchanged).

### 3.7 Rejected / deferred alternatives

| Alternative | Why not |
|---|---|
| Client-only capability guess from `id`/`name`/`description` | `websearch`-only installs would get a summarize action backed by a search tool → exactly the fabricated grounding R3/R4 forbid. Kept only as the degraded fallback if §3.2 is refused (action shown *only* when a candidate's own description names page fetching). |
| New `POST /api/chat/summarize` endpoint doing create+tools+send server-side | One round trip and trivially idempotent, but it forks conversation-creation semantics, breaks R-B (no web counterpart), and the issue lists a new endpoint as not required. |
| Reuse `POST /api/chat/mcp-registry/test` for tool discovery | Already out of the app's surface (F08 *Out of scope*: `/api/chat/mcp-registry/*` is dashboard-only); it is an admin/debug surface and takes a caller-supplied tool+arguments. |
| Summarize into an **existing** conversation | Would silently rewrite that thread's model and tool set. `send_message` reads tools from the row, so the mutation is unavoidable — so summarize owns a new thread, and the ordinary picker rows stay untouched (R2). |
| Auto-title the thread by sending `title` | `runtime.py:52` only auto-titles while the title is still `New Conversation`; a hand-set title would suppress a better one for free. |
| Custom `main_system_prompt` carrying the no-guess rule | Replaces the operator's configured default; see §3.3. |
| A global "always fetch shared URLs" setting | Not asked for; the action is per share. |
| Enabling remembered MCP ids alongside the fetcher | A summarize thread gets the tools the summarize needs, nothing else. `NewChatPreferences.rememberMcpServerIds` is **not** written by this flow — a summarize must not silently change the next ordinary chat's defaults. |

---

## 4. Implementation sequence

| Step / reqs | Files and symbols | Behaviour and responsibility | Depends on | Acceptance |
|---|---|---|---|---|
| P0a | `dashboard/chat/url_retrieval.py` (new): `CANDIDATE_TOKENS`, `candidates()`, `is_url_fetcher()`, `rank()` | Pure classification over `{id,name,description}` + OpenAI-format tool dicts | — | `tests/test_url_retrieval.py`: url+string param ⇒ true; `query`-only ⇒ false; nested/absent schema ⇒ false; ranking prefers a text-returning description; §2.3's four ids behave as stated |
| P0b | `dashboard/chat/mcp_client.py`: `MCPClientManager.discover_bounded(server_id, timeout)` | cache-hit returns cached; else bounded `_discover_tools`; raises on timeout; nothing cached on failure | P0a | `tests/test_mcp_client_probe.py` with a stubbed loop: warm cache ⇒ no spawn; timeout ⇒ raise, cache stays empty |
| P0c | `dashboard/chat/routes.py:get_mcp_servers` + `chat/url_retrieval.py:probe()` | `probe=url-fetch` adds `url_fetch`; **without the param the response stays byte-identical** | P0a,P0b | `tests/test_mcp_probe_endpoint.py`: unauthenticated ⇒ 401; no param ⇒ keys == today; param ⇒ `available`/`servers`/`failures`; a candidate that raises lands in `failures`, response still 200 |
| P1a | `feature/share/SharedUrlExtractor.kt` (new), used by `MainActivity.stageShareIfAny` → `StagedShare.url` | First `http(s)://` URL in `SharedKind.Text` only; trailing punctuation trimmed; uppercase scheme accepted; `Image`/`TextFile`/`Unsupported` never carry one (R1, R10) | — | `SharedUrlExtractorTest`, `SharedDraftStoreTest` (round-trips `url` through the JSON record) |
| P1b | `data/dto/McpServerDto.kt`, `data/McpServersRepository.kt:listForUrlFetch()`, `data/model/UrlRetrieval.kt` | Parses §3.2's payload to `UrlRetrieval(available, servers, failures)`; a missing `url_fetch` key ⇒ `available=false`, `missing_payload` reason | P0c | `McpServersRepositoryTest` (MockWebServer): param present on the wire; absent key degrades, no crash |
| P1c | `feature/share/SummarizeMessage.kt` (new) | The §3.3 text; URL verbatim; no tool ids | — | `SummarizeMessageTest` |
| P1d | `feature/share/ShareTargetViewModel.kt` (`Loaded.summarize`), `ShareTargetScreen.kt` header | Parallel prefetch; `SummarizeOption` = `NotApplicable`/`Checking`/`Available(url,serverIds)`/`Unavailable(reason)`; button only in `Available`; reason line with a next step (R4, R8, R9) | P1a,P1b | `ShareTargetViewModelSummarizeTest`: no url ⇒ `NotApplicable`; probe unavailable ⇒ `Unavailable` naming the fix; failure payload ⇒ distinct reason; prefetch runs once per refresh |
| P1e | `feature/share/SummarizeCoordinator.kt` (new) + `AppNavHost` wiring | Direct path: resolve model → `create` → `setMcpServers` → `stageForAutoSend` → navigate; **no** draft write, **no** `rememberMcpServerIds`; on unavailable model → `newChatSummarize()` | P1c,P1d | `SummarizeCoordinatorTest`: happy path issues exactly one create + one PUT + one navigation; `available=false` ⇒ no create call at all; create failure ⇒ message + picker stays usable; PUT failure ⇒ no claim on disk |
| P2a | `feature/share/SharedDraftStore.kt`: `saveAutoSend`/`takeAutoSend`/`clearAutoSend`/`stageForAutoSend` | Atomic sibling file, consume-once, survives a new store instance | P1e | `SharedDraftStoreAutoSendTest`: write→hydrate→take→take returns null; claim survives `saveAttachments` (sibling, not child); `stageForAutoSend` clears pending in one call |
| P2b | `feature/thread/ThreadViewModel.kt`: claim read in `load()`, `sendPrepared`, `autoSendFired` | Takes the claim before firing; reuses `send()`/`collectRun` untouched below that; a restored composer is the retry surface (R6, R7) | P2a | `ThreadAutoSendTest`: one send per claim; second `load()` sends nothing; pre-frame failure restores the prepared message into the composer and the draft |
| P3 | `feature/newchat/NewChatViewModel.kt` (`summarize: SummarizeContext?`, `summarizeMode`), `NewChatScreen.kt`, `Destinations.newChatSummarize()` | Fallback sheet: forced URL-capable selection, "Summarize" label, `applyTools` success → `stageForAutoSend`, Start blocked when the fetcher is off (R5) | P1e | `NewChatViewModelSummarizeTest`: `Unavailable` remembered model ⇒ sheet, nothing created; toggle fetcher off ⇒ `canStart == false`; retry after `ToolsFailure` → one claim |
| P3b | `feature/modelpicker/RememberedModelResolver.kt` extracted from `NewChatViewModel.load()` | Single owner of the remembered-model ladder, used by sheet and coordinator | — | `RememberedModelResolverTest` + `NewChatViewModelTest` still green (regression guard on the extraction) |
| P4 | `android/docs/F14-share-into-app.md` (**F14-R7**, new IDs only, never renumbered), `android/docs/Plan_TOC.md` §5 row, this doc | Spec + endpoint surface + rationale, in the same commit as the code they describe | all | Spec text matches shipped behaviour; no `[DONE]` marker moved without device evidence |

P0 ships dark: nothing in the app asks for `probe=url-fetch` until P1b, and the web UI is
unaffected at every step. P1 is a usable slice on its own — the action navigates the F03
sheet with the message **staged as the draft** (no auto-send); P2 replaces that draft with
the claim and the fire-on-open.

Verification harness: `android/scripts/dev.sh share-text "…"` already exists; add
`dev.sh share-url <url>` as a thin alias, and reuse `dev.sh stop` / `install` for the
force-stop criteria. Nothing new is needed to drive the flow.

---

## 5. Verification

**Checks actually run for this plan: none** beyond read-only source inspection. Every row
below is proposed. Backend suite: `cd dashboard && pytest tests/`. JVM suite:
`cd android/src && JAVA_HOME=/opt/android-studio/jbr ./gradlew testDebugUnitTest` — read
it, don't count it (`ThreadToolsTest` is a known intermittent, per `android/CLAUDE.md`).

| Req | Test / probe | Observable expected |
|---|---|---|
| R1 | `SharedUrlExtractorTest`; device: `dev.sh share-text "https://example.com/a"` and `dev.sh share-text "great piece → https://example.com/a"` | Header shows "Summarise page" naming the host in both cases |
| R2 | `ShareTargetViewModelTest` (existing, unchanged green); device: share text, pick a row | Content still lands unsent in that thread's composer; the list rows behave exactly as F14-R3 |
| R3 | `SummarizeCoordinatorTest` (`available=false` ⇒ no create), `…(putFails ⇒ no claim)`; device: disable the fetcher in `mcp_servers.json`, reload registry, share | No thread created, no turn submitted, reason on the picker |
| R4 | `ShareTargetViewModelSummarizeTest` (three distinct reasons); device: stop the fetch server's venv path, share, tap | Config failure and fetch failure read differently; the fetch-failure transcript shows the tool card's error and no invented summary |
| R5 | `NewChatViewModelSummarizeTest`, `RememberedModelResolverTest`; device: stop the remembered model, share, tap | Sheet opens with the URL retained; picking another model sends one turn |
| R6 | `ThreadAutoSendTest` restore case; device: `dev.sh net off` just before tapping, then back on | Thread opens, prepared message sits in the composer, Send works, nothing else was sent |
| R7 | `SharedDraftStoreAutoSendTest`, `ThreadAutoSendTest`, `SummarizeCoordinatorTest` (one create per tap); device: tap, force-stop before the stream renders, relaunch, then visit the thread again | Exactly one user turn in the thread; no second anywhere; the run is visible via F09 reattach |
| R8 | instrumented-ish timing on device: tap → first delta < ordinary share+type+send for the same model | No container/compose operation in the trace; prefetch completes before the tap is enabled |
| R9 | `tests/test_url_retrieval.py` (no id is privileged); device: disable `webfetch` + `browser-fetch`, reload | Action disappears with a "no page-fetch tool" reason rather than a failing summary |
| R10 | `SharedKindParserTest` additions; device: `dev.sh share-image`, `dev.sh share-file` | No summarize affordance anywhere in either flow |
| Payload safety | `tests/test_mcp_probe_endpoint.py` no-param case byte-compared to today's | `/v2` tool toggles unchanged |
| Ops | `GET /api/services/<…>/health` untouched; `dev.sh logs` shows the dashboard never spawns a server on a plain `mcp-servers` read | No subprocess storm from ordinary UI polling |

---

## 6. Rollout and risks

**Order:** P0 → P1 → P2 → P3 → P4, each a branch off a fresh `main` (repo rule), one
PR per phase for P0 and P1+P2 combined if the reviewer prefers two commits inside one PR.
The app degrades safely against an older dashboard: no `url_fetch` key ⇒ `Unavailable`
⇒ the action never appears ⇒ today's F14 behaviour in full. That is the rollback:
reverting the backend leaves the phone with no summarize action and no broken share path.
No migration, no destructive step, nothing in `chat.db` changes shape.

| Risk | Mitigation |
|---|---|
| The model skips the tool and answers from prior knowledge anyway | Residual, model-dependent. Contract text in the user turn, tool card visible, and R3's gate means the *only* way to a summarize answer is a thread that has a fetcher. A hard "did a fetch tool actually run" guard belongs to the run layer and is a follow-up, not this issue |
| Probe cost: a subprocess spawn per candidate per uncached call | Candidate filter first, 5s bound, successful discoveries land in `_tools_cache`; failures are not cached so a retry can succeed. If a dead server turns out to be hammered, add a short failure TTL — deliberately not in v1 |
| Enabling `browser-fetch` only yields a screenshot, not text | Ranking puts a text-returning tool first; the message asks for page text; the "nothing useful" contract path reports it. Not fixed here — extraction quality is an explicit non-goal |
| Orphan empty thread after a crash between create and tools PUT | Stated in §3.4; the share returns and one turn follows |
| Auto-send firing on a thread the user reopened days later | Consume-once at `load()`; it fires at most once ever, and only for a claim that was written by an explicit tap |
| `saveAttachments` wiping a claim placed inside `conv_<id>/` | Claim is a sibling file; asserted by a named test, not by prose |
| `mcp_servers.json` differs per machine | Everything is probe-driven; the only install-specific assertion in this plan is §2.3, labelled as a probe of *this* machine |

**Open, non-blocking, for the implementer to settle with the reviewer:** button wording and
placement in `ShareHeader`, and whether the reason line collapses behind a "why?" affordance.
Nothing in the contracts above depends on either.

---

## 7. Readiness

**Ready for implementation**, with one named product decision to confirm before P1d is
wired: *summarize always creates a new conversation* (§3.7), which is what makes R3
enforceable and R2 untouched. If the owner instead wants summarize-into-an-existing-thread,
that thread's model and tools get rewritten and R2/R3 need re-opening — say so before P1e.

Everything else is settled by the source above: the capability contract (§3.2), the message
shape (§3.3), the state machine and its at-most-once argument (§3.4), the single model
resolver (§3.5), and the phase table (§4). Backend work is one endpoint param plus one pure
module plus one manager method; the app change reuses F03's create flow, F08's tool write,
F14's durable staging and F04's send path rather than inventing a parallel one.

---

## 8. Implementation status

Shipped on `feature/issue-255-share-summarize`, P0 → P3 in one branch, three commits.
Device criteria (three, all in F14-R7's list) are **not** yet run — they need an emulator
or the phone, and none is attached here.

| Phase | Where it landed | Difference from the plan above |
|---|---|---|
| P0 | `dashboard/chat/url_retrieval.py`, `MCPClientManager.discover_bounded`, `?probe=url-fetch` on `get_mcp_servers`; `test_url_retrieval.py`, `test_mcp_probe_endpoint.py`, `test_mcp_client_probe.py` | As designed. `probe()` takes an injected `discover` callable instead of a timeout, so the module stays I/O-free and the deadline lives with the caller. |
| P1 | `SharedUrlExtractor`, `StagedShare.url`, `UrlRetrieval` + `McpServersRepository.catalog(probe)`, `SummarizeMessage`, `SummarizeOption`, `SummarizeCoordinator`, `ShareTargetViewModel/Screen` | `SummarizeOption` carries the user-facing reasons, so the three failure readings are one owner and JVM-assertable. The picker's Blocked row has its own Retry. |
| P2 | `SharedDraftStore.stageForAutoSend/takeAutoSend`, `ThreadViewModel.fireAutoSend` | Claim file is `conv_<id>.autosend.txt` (sibling of `pending.json`, as specified); `clear()` also drops it, so a spent thread cannot re-owe a turn. |
| P3 | `Destinations.newChatSummarize()`, `NewChatViewModel(summarizeMode, sharedDraftStore)`, `StartButton(label)` | The sheet forces the fetched server set and blocks Start without it, rather than adding a new control. `rememberMcpServerIds` is untouched in this mode, as specified. |
| P3b | `feature/modelpicker/RememberedModelResolver` extracted from `NewChatViewModel.load()` | `RememberedModel` has three cases (`Resolved`/`Unavailable`/`None`) because "never chose" and "chose, then it died" need different copy. |
| P4 | `android/docs/F14-share-into-app.md` (F14-R7 + three Deviations), `Plan_TOC.md` §2/§5/§6 | The R-A exception is recorded at the rule itself, not only in the feature file, so the next reader does not "fix" it. |

Backend suite: 1449 passed, 1 skipped, 6.5s under `-n auto` (after PR #253 landed). The
probe was also run against this machine's real registry, not fakes: `webfetch` and
`browser-fetch` qualify, `websearch` does not (its one tool takes `query`), `ragflow`
surfaced as a discovery failure rather than as unavailable. That run caught one real bug —
`screenshot_page`'s docstring says "dynamic content" and "<title> text", which satisfied the
positive text-keyword test and put the screenshotter first — fixed in fa2f93e by ranking on
the output format a tool names for itself. JVM suite: the new classes and every touched class
pass (`SharedUrlExtractorTest`, `SummarizeMessageTest`, `SharedDraftStoreAutoSendTest`,
`RememberedModelResolverTest`, `SummarizeCoordinatorTest`, `ThreadAutoSendTest`,
`ShareTargetViewModelTest` 15, plus `NewChatViewModelTest`/`SharedDraftStoreTest`/
`ThreadShareTest` untouched and green). The full JVM run is still subject to the
cross-class `Dispatchers.Main` flake `android/CLAUDE.md` already documents — it moved
between runs and every affected class passes in isolation.
