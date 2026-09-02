# Plan: Dynamic OpenRouter Model Selector

## Goal

Replace the hand-edited JSON textarea that curates the OpenRouter chat picker
with a picker over the **live OpenRouter catalog**: the settings page lists
every model OpenRouter currently serves, lets the user search / filter / sort
it, and add or remove entries from the short list the chat dropdowns show —
without anyone touching JSON or a hardcoded list.

"Add / remove models from OpenRouter" means add to or remove from the **short
list**. Nothing is created or deleted on OpenRouter: their API is read-only
here and has no such operation.

Scope: one settings card + one backend catalog proxy. The chat pickers, the
storage format, and the `openrouter:<model-id>` service-string convention do
not change.

## Non-Goals

- The chat dropdown does **not** become a catalog browser. It keeps showing
  only the curated short list; discovery happens in settings only.
- **No allowlist semantics.** A curated entry is a picker convenience — any
  `openrouter:<id>` still resolves as long as the key is set (existing
  behaviour, regression-tested as
  `tests/test_openrouter_routes.py:test_resolution_ignores_curated_list`).
  This is what makes removal from the list safe.
- No per-model overrides (temperature, reasoning effort, provider routing).
- No change to the legacy v1 frontend or the Android client — neither reads
  the curated list.
- No removal of `DEFAULT_MODELS`: it stays the built-in baseline that
  "Reset to built-in" restores and the fallback on a fresh install.
- No auto-sync of the short list when OpenRouter adds or drops a model. The
  badge in the short list is the only feedback; the list stays as the user
  left it.
- No multi-select / bulk add in v1. One Add toggle per row; the Advanced JSON
  panel covers pasting a list of ten.

## Current State

**Backend**

- `dashboard/chat/openrouter.py` — `DEFAULT_MODELS` (20 entries),
  `is_configured()`, `resolve()`, `SERVICE_PREFIX`, `OPENROUTER_BASE_URL`,
  `OPENROUTER_EXTRA_HEADERS`. Holds **no network calls and no mutable state**
  today; keep it that way (see Design Decision 1).
- `dashboard/chat/settings_store.py` — `get_openrouter_models()`,
  `set_openrouter_models()`, `is_openrouter_models_customized()`,
  `reset_openrouter_models()`. Stored as `openrouter_models` in
  `chat_settings.json`, atomic write under `_lock`, validated
  (`{id: non-empty string, label?: string}`, no duplicate ids, empty list
  allowed and honored as "hide all").
- `dashboard/chat/routes.py:184-226` — `GET/PUT/DELETE
  /api/chat/settings/openrouter-models`, all returning
  `{configured, current, builtin, customized}` via
  `_openrouter_settings_payload()`.

**Frontend** (`dashboard/frontend/src`)

- `components/tools/OpenRouterModelsEditor.jsx` — the current UI: JSON
  textarea + a client-side `validateModelsJson()` mirror of the server rules,
  Save / Discard / two-step Reset.
- `hooks/useOpenRouterModels.js`, `services/openrouterModels.js` — load / save
  / reset against `/chat/settings/openrouter-models`.
- `utils/openrouter.js` — prefix encode/decode + `formatModelLabel()`.
- `components/chat/ModelSelector.jsx` → `ModelOptions.jsx` consume
  `data.current` (only when `data.configured`); a stale selected model already
  renders as a fallback "(not in list)" option.
- Card lives on `/tools` (`components/tools/ToolsPage.jsx:163`).
  `/settings` (`components/SettingsPage.jsx`) renders ThemeCard,
  PromptsEditor, TOTPSetup — the OpenRouter editor is **not** there today.

## Upstream facts (verified against the live API)

`GET https://openrouter.ai/api/v1/models`

- **No auth required** — works without `OPENROUTER_API_KEY` (sending the key
  as a bearer only buys better rate limits). Still proxied server-side, never
  fetched from the browser (Decision 1).
- **425 models, ~690 KB raw JSON.** Catalog changes slowly.
- Fields worth surfacing: `id`, `name` (`"Tencent: Hy4 preview"`), `created`
  (unix), `context_length`,
  `pricing.{prompt,completion,input_cache_read}` (strings, **$ per token** →
  ×1e6 for $/M), `supported_parameters`, `architecture.input_modalities` /
  `architecture.output_modalities` / `architecture.tokenizer`,
  `hugging_face_id`, `expiration_date`,
  `benchmarks.artificial_analysis.{intelligence_index,coding_index,agentic_index}`
  (present on 242 of 425), `canonical_slug`. Everything else
  (`description` in full, `top_provider`, `links`, `per_request_limits`,
  `default_parameters`, `supported_voices`, `knowledge_cutoff`) is dropped.
- **Id variants are separate rows, not a hierarchy**: `:free`, `:batch`,
  `:extended` suffixes (88 ids currently carry a `:`), plus dated snapshots as
  distinct ids (`deepseek-v4-flash-0731`, `hy3-20260827`).
- **Zero price ≠ `:free` suffix.** 21 models price at `prompt == "0"`; only 18
  carry the suffix. The three without it are `openrouter/free` and the two
  Lyria music previews → `free` must be derived from price, never from the id.
- **`Free` can be a lie.** `google/lyria-3-pro-preview` prices at `$0/$0` while
  its description says "$0.08 per song" — per-unit pricing is not
  representable in `pricing`. One more reason its row hides by default, and a
  reason to show the description on hover for revealed zero-price rows.
- **58 distinct vendor prefixes** (`openai/` 89, `qwen/` 53, `google/` 41,
  `anthropic/` 28, `mistralai/` 25, `z-ai/` 16, `deepseek/` 16, …) — the org is
  worth its own filter, since "everything except Anthropic and OpenAI" is a
  common ask.
- **359 of 425 are tool-capable** (`"tools" in supported_parameters`). The chat
  uses MCP tools, so this is a first-class filter and badge.
- **19 rows are not chat models**: 6 OpenRouter pseudo-routers
  (`openrouter/free`, `/auto`, `/auto-beta`, `/fusion`, `/pareto-code`,
  `/bodybuilder`) plus 13 that emit non-text output (9 image-output — Gemini
  / GPT image models; 4 audio-output — Lyrias, `gpt-audio*`). Both groups price
  cleanly and would look pickable → hide by default, behind a reveal toggle.
  Note the correct test is *output* modalities containing `image`/`audio`, not
  "`text` absent from output modalities" — every one of these rows still lists
  `text` among its outputs, so the naive test hides zero rows.
- **`expiration_date` is mostly sentinel.** 6 rows carry one and 5 read
  `2098-12-31`. Only treat an expiry within ~10 years as real;
  `deprecated = expires < today`.
- All 425 rows have `name` and `context_length`; descriptions top out at 336
  chars; key presence is otherwise **not** uniform → every field access
  degrades to `None` / empty rather than raising.
- Float artifacts: `pricing` strings are decimal-ish text, so `×1e6` yields
  `0.09999999999999999`. Round on the **server** (`round(x, 4)`) so the client
  never sees it.

## Design Decisions

1. **Server-side proxy + cache, in its own module.** Fetching goes through the
   dashboard: one network egress path, the upstream shape stays out of the
   client, one place to normalize units and to serve stale data when OpenRouter
   is unreachable. Browser-side fetching would add CORS and a duplicated
   normalize step. The code lands in a **new** `chat/openrouter_catalog.py`,
   not in `openrouter.py`, which today is pure resolution logic with no I/O or
   mutable state.
2. **Storage shape unchanged.** Still `[{id, label}]`. The catalog is
   display-time enrichment, never persisted — so there is no migration, stored
   metadata cannot go stale, and the existing `PUT` validation plus
   `test_openrouter_settings.py` / `test_openrouter_routes.py` pass untouched
   (that passing-unchanged is itself an acceptance criterion, see Testing).
3. **Card moves to `/settings`.** The ask is "settings page", and `/settings`
   already holds the other chat settings (`PromptsEditor`). `/tools` keeps the
   MCP registry and drops this card — exactly one editor per setting. The two
   placements are one import line apart if that call is revisited.
4. **JSON editor stays, demoted.** Kept as a collapsed "Advanced: edit JSON"
   panel below the picker, sharing the extracted validator. Bulk paste-in of a
   model list is genuinely useful and costs nothing once the validator is
   shared; it is also the escape hatch that keeps shortlist editing available
   when OpenRouter is unreachable.
5. **Filters are client-side.** 425 normalized rows are small enough to return
   whole and filter in memory, which keeps search instant and makes new vendor
   facets free. Server-side filtering would just move the problem.

## Backend Implementation

### 1. New module `dashboard/chat/openrouter_catalog.py`

Mirrors the pure/IO split of `settings_store.py`: unit-testable, no Flask
import.

```python
CATALOG_URL = f"{openrouter.OPENROUTER_BASE_URL}/models"   # reuse the existing base URL
CACHE_TTL_SECONDS = 900          # 15 min — the catalog drifts slowly
FETCH_TIMEOUT_SECONDS = 10       # explicit timeout, as chat/llm_proxy.py does
```

- `fetch(force: bool = False) -> dict` →
  `{fetched_at, stale, count, models: [...], error: str | None}`
  - cache hit within TTL and not `force` → cached payload (`stale=False`)
  - `requests.get(CATALOG_URL, timeout=FETCH_TIMEOUT_SECONDS)` (bearer key
    attached when `openrouter.is_configured()`); on 2xx, normalize, store
    `{models, fetched_at}`, return
  - on **any** failure (timeout, non-2xx, malformed JSON, missing `data`):
    serve the previous good payload with `stale=True` and `error` set; if there
    is no previous good payload, raise `CatalogUnavailable(reason)`
  - the whole read-fetch-cache path runs under a `threading.Lock` (same intent
    as `settings_store._lock`) so concurrent requests don't stampede
    OpenRouter. Precedent for an in-process dict cache:
    `chat/mcp_client.py:_tools_cache`.
  - **stale-if-error, not hard failure**: the picker must stay usable when
    OpenRouter is down. The `stale` flag drives a banner; the frontend also
    keeps its last good render.
- `_normalize(raw: list) -> list` — pure, one record per model, sorted by
  `name` for a stable baseline order, entries with no `id` skipped:

```python
{
  "id": m["id"],
  "name": m.get("name") or m["id"],
  "label": <name with the "Vendor: " prefix stripped>,   # default shortlist label
  "created": int | None,
  "context_length": int | None,
  "price_in": float,             # $/1M tokens, round(x, 4)
  "price_out": float,            # $/1M tokens
  "price_cache_read": float | None,
  "free": price_in == 0 and price_out == 0,             # NOT id.endswith(":free")
  "variant": "free" | "batch" | "extended" | None,      # id suffix
  "vendor": id.split("/")[0],
  "router": id.split("/")[0] == "openrouter",           # pseudo-models
  "image_out": "image" in output_modalities,            # 9 rows
  "audio_out": "audio" in output_modalities,            # 4 rows
  "chat_model": not router and not image_out and not audio_out,   # 406 rows
  "tools": "tools" in supported_parameters,
  "structured_outputs": bool,
  "reasoning": bool,
  "input_modalities": ["text", "image", "file", ...],
  "tokenizer": str | None,
  "hugging_face_id": str | None,
  "expires": "YYYY-MM-DD" | None,      # expiration_date, sentinel dates → None
  "deprecated": bool,                  # expires is set and expires < today
  "benchmarks": {"intelligence": …, "coding": …, "agentic": …} | None,
}
```

  `chat_model` (and its constituents) exist so the UI can default-hide rows
  that don't belong in a chat short list. They are **not** server-side
  exclusions: the endpoint returns everything and the hide is a client filter
  the user can turn off, so OpenRouter adding a new router or image model
  needs no backend change.
  Shortlist labels default to `label` (the `name` minus its `"Vendor: "`
  prefix) rather than the full `name` — `"Hy4 preview"` reads better in a
  dropdown than `"Tencent: Hy4 preview"`, and the vendor has its own column
  upstream of it.
- `known_ids() -> set[str]` from the last good cache (`set()` if never
  fetched), so the shortlist can badge stale entries without a second fetch.

`short_description` (upstream `description` truncated to ~200 chars) is
deliberately **not** in the default payload — measured, it costs ~75 KB of the
response for a hover tooltip. Ship it only under `?detail=1`, and have the
client request that lazily for the rows it renders, or skip it entirely in v1
and rely on the id + name. (See Payload.)

No new dependency: `requests` is already in `requirements.txt` (used by
`chat/llm_proxy.py`, `chat/critique.py`).

### 2. New route in `dashboard/chat/routes.py`

```
GET /api/chat/settings/openrouter-catalog?refresh=1&detail=1
```

- `@require_auth` like its siblings, added next to the existing
  openrouter-models settings section. Settings-namespaced on purpose: every
  other settings verb lives under `/api/chat/settings/*`.
- Returns `openrouter_catalog.fetch(force=<refresh>)` plus
  `"configured": openrouter.is_configured()` and `"known_ids": sorted(...)` —
  one round-trip drives the picker, the "key not set" banner, and the stale-id
  badges.
- `CatalogUnavailable` → `502 {"error": "OpenRouter catalog unavailable: …",
  "models": []}` so the UI renders an inline retry instead of a generic
  failure.
- Envelope:
  `{models: [...], count, fetched_at, stale, cached, configured, error}`.
- Leave the three existing `/openrouter-models` verbs **untouched**.

Do **not** gate the catalog on `OPENROUTER_API_KEY`: upstream is public, so the
picker stays usable for authoring the list before the key exists — the same
posture as today's editor, which works while `configured` is false. The
existing "key not set" banner explains the chat impact.

### Payload (measured, not assumed)

Normalized at 425 models: **~205 KB** with the field list above, ~280 KB with
`short_description`, ~156 KB with tersely-named keys, **~14-16 KB gzipped**.
That is acceptable for a settings page that fetches once per mount and caches
server-side for 15 min — but it is *not* the "40-60 KB" this plan originally
estimated, hence the description deferral above. The dev server does not
compress, so budget the uncompressed figure on first paint. Revisit (server-side
paging or a `?vendor=` filter) only if the catalog grows an order of magnitude.

## Frontend Implementation

### 3. `services/openrouterCatalog.js` + `hooks/useOpenRouterCatalog.js`

Same shapes as the existing service/hook pair.
`getOpenRouterCatalog(refresh = false)` → `fetchAPI('/chat/settings/openrouter-catalog' + (refresh ? '?refresh=1' : ''))`.
Hook exposes `{ data, loading, error, refresh(force) }` with the `mountedRef`
guard from `useOpenRouterModels.js`, and **never auto-refreshes** — the card
fetches once on mount; refresh is an explicit button. Catalog state is held in
React state for the session, so navigating away and back is the only refetch.

### 4. `components/settings/OpenRouterModelsPicker.jsx`

Two-column card (`max-w-3xl` page → stack the columns below `md`):

```
┌────────────────────────────────────────────────────────────────┐
│ OpenRouter models          [Modified] [Reset] [Save] [Discard]  │
│ Models offered in the chat model pickers. Not an allowlist.     │
│ (banners: OPENROUTER_API_KEY not set · catalog stale/unreachable)│
├─────────────────────────────────┬──────────────────────────────┤
│ All models          [search___] │ Chat dropdown        (7)     │
│ [Refresh] [filters…]            │ ↑ qwen/qwen3.7-flash     ✎ ✕ │
│ ┌─────────────────────────────┐ │ ↑ z-ai/glm-5.2           ✎ ✕ │
│ │ Tencent: Hy4 preview   [Add]│ │   …                          │
│ │ 1M ctx · $0.83/$2.50 · tools│ │ (rows badged "not in catalog" │
│ └─────────────────────────────┘ │  / "deprecated" when applies)│
│ showing 118 of 425 · clear      │                              │
└─────────────────────────────────┴──────────────────────────────┘
│ ▸ Advanced: edit JSON   (shared validator, same state)          │
└─────────────────────────────────────────────────────────────────┘
```

- **Left — "All models" (the catalog).** Debounced (~150 ms) search over `id`,
  `name`, `vendor`. Filter row:
  - **vendor multi-select**, derived from the catalog's own prefixes so it
    can't go stale (58 today)
  - tool-capable only (default **on** — the chat depends on MCP tools)
  - free only · min context (128K / 256K / 1M presets) · max $/M in ·
    modality (vision, audio, file, video)
  - hide `:batch` variants (default on — batch is not chat-conversational) ·
    hide `:free` / hide dated-snapshot variants · hide `deprecated`
  - **hide non-chat, default on**, with a toggle labelled with the count
    ("show 19 non-chat") so filtered-away rows are visible rather than silently
    missing — that toggle covers `router` + `image_out` + `audio_out`
  - sort: name · newest (`created`) · price ↑ · context ↓ · intelligence /
    coding index
  - `showing N of M` line + "Clear filters": with 425 rows and filters active,
    an empty list must read as filtered, not broken
  - toggle-style **Add / Added** button per row (Added = highlighted; clicking
    it removes from the short list), so add and remove are one control and a
    duplicate add is unconstructible. `Enter` in the search box adds the first
    not-yet-added result.
  - already-added rows stay visible but dimmed/checked (rather than vanishing
    mid-search), so re-finding one you just added costs nothing.
- **Right — "Chat dropdown" (the short list).** `N selected` count; ordered
  rows with ↑/↓ reorder (no drag in v1), inline-editable label (defaults to the
  catalog `label`), remove (✕), and a badge when the id is missing from the
  fetched catalog (`not in catalog`) or is `deprecated`. Reorder / label / remove
  are local state; Save issues **one** `PUT` with the whole list.
- **Header actions**: Refresh (`?refresh=1`, bypasses the server cache), Save
  (enabled when dirty and valid), Discard, Reset to built-in (the existing
  two-step confirm), plus "stale catalog" and "key not set" banners reusing
  today's copy.
- **Advanced: edit JSON** collapsible holding today's textarea. Both panels
  drive the same state; the picker reflects the last saved/validated JSON.
- Memoize filter+sort (`useMemo` on `[catalog, query, filters, sort]`). 425 rows
  render fine unwindowed — no virtualization in v1.

### 5. Extract shared pieces

- Move `validateModelsJson()` out of `OpenRouterModelsEditor.jsx` into
  `utils/openrouterModels.js` (alongside the existing `utils/openrouter.js`
  prefix helpers) so the picker's Advanced panel, the old editor, and the
  service layer validate in one place.
- `deriveLabel(catalogEntry)` → catalog `label` → catalog `name` → id after
  `/`. Used when adding from the catalog. Explicit user-entered labels always
  win and are never rewritten by a later catalog refresh.
- `formatModelLabel(name, models)` needs no change: it already falls back to the
  bare id, which stays correct.

### 6. Wire the page

`components/SettingsPage.jsx`: mount `<OpenRouterModelsPicker />` between
`PromptsEditor` and `TOTPSetup`. `components/tools/ToolsPage.jsx`: drop the
import and the render at line 163, and delete `OpenRouterModelsEditor.jsx`
once its validator has moved (its JSON panel lives on inside the picker).
`ModelSelector.jsx` / `ModelOptions.jsx` / `useOpenRouterModels.js` are
unchanged — they keep reading `current`.

## Phase 4: provider detail in the catalog rows

Goal: show, per row, which endpoint providers serve a model — DeepInfra, Tencent,
Amazon Bedrock — since the model-level price is only the cheapest of them and the
spread is the interesting part.

Upstream constraints, all verified:

- No bulk endpoint (`/api/v1/endpoints` → 404), no expansion flag on `/models`
  (`?include=endpoints` and `?expand=endpoints` return the byte-identical 705 KB
  payload with no `endpoints` key), no singular `/models/{id}` route. Provider
  names exist **only** in `GET /api/v1/models/{id}/endpoints`.
- Fan-out over all 425 models at concurrency 8: **14.3 s, 10 failures (2.4 %)**,
  mean **2.9 endpoints** per model, **18 rows with zero**, **73 distinct**
  providers. Summary payloads: 23 KB names-only, 134 KB slim, 195 KB verbose.
- Per-model responses carry `provider_name`, `quantization`, `context_length`,
  `max_completion_tokens`, `pricing` (per token, with time-of-day `overrides`),
  `uptime_last_1d/30m/5m` (**already a percentage**), `latency_last_30m`,
  `throughput_last_30m`, `status` (**integer enum, undocumented for non-zero
  values**), `supported_parameters`, `supports_tool_choice`.

Decisions:

1. **Fetch the visible page, not the catalog.** The picker posts the ids it is
   rendering (cap 60) to `POST …/openrouter-catalog/endpoints`; the server caches
   per model id, so the cost is proportional to what is on screen — measured
   **0.345 s for 4 ids** cold, 0 s warm. A whole-catalog fetch would be 425
   upstream requests and 14 s to describe rows nobody is reading.
2. **Per-id failure isolation, no cached holes.** A batch whose one id 404s still
   returns the other three; the failure lands in `missing`, and the client drops
   it from its requested-set so the next request retries. Without this, one
   transient upstream error would punch a permanent gap in the session's map.
3. **Per-id cache, 5 min TTL** — shorter than the catalog's 15 min, because price
   and uptime move. Separate lock: provider fan-out must never block a catalog
   read.
4. **`status` passed through verbatim.** Non-zero values are not documented
   upstream, so the row prints `status -2` rather than inventing a label like
   "degraded" for an enum it cannot read.
5. **Chips fade in, no per-row spinner.** A row without detail renders no provider
   line; ~300 ms later it has one. A row that never gets one (zero endpoints, or a
   rejected id) looks the same as one in flight — accepted, since the alternatives
   (skeleton rows, per-row spinners) read worse for something this incidental.
   Zero-endpoint rows get an explicit "no endpoints listed upstream" line, which
   is a fact rather than a loading state.
6. **Line format**: `4 providers · Z.ai, DeepInfra, Novita +1 · fp8/int4 ·
   $1.00/M–$3.00/M`, expanding to a table of provider / quant / ctx / in-out /
   uptime (with `no tools` and non-zero `status` flags inline). Single-provider
   models — the common case — render `provider · name`, not `1 providers`.

Deliberately **not** built: a provider filter across the catalog. It needs the
model→provider map for all 425 rows, i.e. the 14 s sweep, and a filter that only
correctly describes the models whose providers happen to be warm would be worse
than none. If wanted later: a single-flight background sweep endpoint, warmed by
the Refresh button, with the filter disabled until it completes.

## Edge Cases

- **Curated id disappears upstream** (renamed/retired): badge it, never
  auto-delete, never block Save. Silent deletion would break conversations
  pointing at it, and `resolve()` deliberately doesn't consult the list.
- **Catalog unreachable on first-ever fetch**: short list still renders from
  `current` + `builtin`; the catalog pane shows the error with Retry. Save and
  Reset must keep working — neither needs the catalog.
- **Catalog unreachable later**: stale-if-error keeps the last catalog on the
  server, plus a "catalog stale" banner; the client keeps its last good render.
  Editing continues from the JSON panel.
- **Variant ids of one model** (`x:free`, `x:batch`, dated snapshots): all
  selectable; collapse them under the parent id when the "collapse variants"
  toggle is on so the list isn't 20 % duplicates.
- **Duplicate add** is a visual no-op (button already `Added`); the server still
  400s a duplicate `PUT` payload and the picker must never construct one.
- **Empty short list** is valid and means "no OpenRouter models in chat" — keep
  it reachable (remove-all + Save), matching `test_put_empty_list_is_valid` and
  `test_empty_list_is_honored`.
- **Pricing display**: upstream is $/token; always render $/1M with ≥2
  significant digits (`$0.03/M` … `$2.50/M`) and `Free` for zero. Raw
  `0.000000834` is unreadable and misleading.
- **`Free` badge is not proof of free.** Price-zero rows with per-unit pricing
  exist (Lyria, $0.08/song). They sit in the default-hidden group; if revealed,
  the row tooltip should surface the description so real pricing is one hover
  away.
- **Labels are user text, not upstream names**: adding `tencent/hy4-preview`
  defaults to `Hy4 preview`; upstream renaming the model later must not
  silently rewrite a stored label.
- **Cache invalidation**: `refresh=1` only, no push invalidation — the TTL is
  short enough.

## Testing

**Backend** (`dashboard/tests/`, following the `test_openrouter_settings.py` /
`test_openrouter_routes.py` fixtures; monkeypatch `requests.get`, no network):

- `test_openrouter_catalog.py` — normalization (pricing strings → rounded
  floats; `free` from price and **not** from the `:free` suffix; `router` /
  `image_out` / `audio_out` / `chat_model` on the known pseudo-routers and
  image/audio models; sentinel `2098-12-31` → `expires: None`; missing keys
  degrade instead of raising; `label` strips the `"Vendor: "` prefix); TTL
  hit / miss; `force` bypass; stale-on-error returns the previous payload with
  `stale=True` and `error` set; first-ever failure raises
  `CatalogUnavailable`; the lock serializes concurrent fetches; `known_ids()`.
- extend `test_openrouter_routes.py` — catalog route requires auth; 200 shape
  carries `configured` and `known_ids`; 502 with `models: []` when upstream is
  down; `refresh=1` reaches upstream.
- **regression**: the existing `PUT` / `DELETE` / picker-payload tests pass
  unchanged. That is the proof the storage contract held.

**Frontend** (Vitest + Testing Library, colocated):

- `components/settings/OpenRouterModelsPicker.test.jsx` — add from catalog
  inserts with the derived label; clicking an `Added` row removes it; reorder
  persists order in the `PUT` body; unknown-id badge; vendor filter narrows to
  one org; tool-only toggle filters; the 19 non-chat rows are absent until the
  reveal toggle is on and its label carries the count; `showing N of M` and
  `N selected` update; Discard restores; Reset calls DELETE and reseeds from
  `builtin`; Save blocked while the shared JSON payload is invalid; catalog
  error shows Retry without blocking shortlist editing.
- `services/openrouterCatalog.test.js` — `refresh` toggles the query string.
- Move/adapt any `OpenRouterModelsEditor` assertions as that component folds
  into the Advanced panel.

**Commands**

```
cd dashboard && venv/bin/pytest tests/test_openrouter_catalog.py \
    tests/test_openrouter_routes.py tests/test_openrouter_settings.py
cd dashboard/frontend && npm test -- src/components/settings src/utils/openrouterModels.js
cd dashboard/frontend && npm run lint && npm run build
```

**Manual pass**: `/settings` with `OPENROUTER_API_KEY` set and unset; add /
reorder / rename label / remove / save / reset; confirm the `/chat` dropdown
reflects the saved list; block the network and confirm the catalog error path
leaves the short list editable.

## Rollout

1. **Phase 1 [DONE] — backend.** `openrouter_catalog.py` + route + tests. Ships dark:
   nothing in the UI changes, and the endpoint is independently useful (a later
   read-only catalog view, or the Android client).
2. **Phase 2 [DONE] — frontend.** Service/hook, picker component, validator
   extraction, `/settings` mount, `/tools` removal, tests.
3. **Phase 3 [TODO] — polish (optional).** Sort-by-benchmark columns; "N new models
   since you last looked" from `created` vs a stored `seen_at`; pre-filtered
   quick chips ("free", "tool-capable", "cheap"); drag reorder; lazy
   `?detail=1` descriptions.
4. **Phase 4 [DONE, uncommitted] — provider detail** in the catalog rows, per the
   section below: per-id fan-out cache, batch POST route, provider line with an
   expandable table.

One commit per phase, feature branch from a fresh `main`.

## Implementation status

Phases 1 and 2 are on `plans/dynamic-openrouter-model-selector`, one commit per
phase from a fresh `main`. Phase 3 is untouched.

- **Phase 1** — `chat/openrouter_catalog.py`,
  `GET /api/chat/settings/openrouter-catalog`, 33 tests in
  `tests/test_openrouter_catalog.py` and a catalog section in
  `tests/test_openrouter_routes.py`. Checked against live upstream: 425 models,
  238 KB (329 KB with `?detail=1`), 401 unauthenticated, `cached` / `stale`
  flags and `?refresh=1` busting confirmed over HTTP.
- **Phase 2** — `services/openrouterCatalog.js`, `hooks/useOpenRouterCatalog.js`,
  `utils/openrouterModels.js`, `components/settings/OpenRouterModelsPicker.jsx`,
  mounted on `/settings`, JSON editor removed from `/tools`, both `AGENTS.md`
  files updated. 22 picker tests + 4 service tests + 22 util tests; full suite
  green (823 backend, 383 frontend), lint 0 errors, build clean.
- **Phase 3** — not started.
- **Phase 4** — `summarize_endpoints()` + `POST /api/chat/settings/openrouter-
  catalog/endpoints`, `services/openrouterProviders.js`,
  `hooks/useModelProviders.js`, provider line in `CatalogRow`. 12 new backend
  module tests + 8 route tests, 6 hook tests, 3 service tests, 7 picker tests.
  Live check: 4 ids cold in **0.345 s**, colon-suffixed id resolves, unknown id
  reported in `missing` and not cached, second call `fetched: 0`, 61 ids → 400.

Two deliberate deviations from the spec above:

- Sort offers the **intelligence** index only; coding/agentic columns are
  Phase 3.
- The `hideDeprecated` filter is labelled **"hide expiring"**, which says what
  it does better than the field name — upstream `expiration_date` means "this
  row goes away", not "this model is deprecated".

**Docs** (done, with Phase 2): `AGENTS.md` had documented both the endpoint
surface and this card as living on the Tools page — "Tools page → 'OpenRouter
models' card" in the *Chatting with OpenRouter models* section. The card's
location now reads `/settings`, the catalog endpoint is described there, and the
list is documented as curated from a live catalog rather than hand-edited as
JSON.

## Resolved Decisions

Taken from the three source plans, with the disagreements settled:

| Question | Decision |
|---|---|
| Card location | `/settings`, card removed from `/tools` (Decision 3) |
| Already-added rows in the catalog pane | dimmed + checked, not hidden |
| Custom labels | inline-editable in the short list (cheap — local state), auto-defaulted from the catalog |
| Reorder | ↑/↓ buttons in v1; drag is Phase 3 |
| Save | explicit Save + Discard, as today; no debounced auto-save |
| `free` derivation | from price, never from the `:free` suffix |
| Endpoint path | `/api/chat/settings/openrouter-catalog` (settings-namespace) |
| Upstream fetch failure | stale-if-error first, 502 only when there is no cached payload |
| Non-chat rows | normalized as flags server-side, hidden by client-side filter with a counted reveal toggle |

Still open, and cheap to change later:

- Should the built-in `DEFAULT_MODELS` survive indefinitely, or eventually
  become "last saved selection"? Kept — it is the reset target and the fresh
  -install fallback.
- Whether Phase 2 ships with descriptions deferred (current plan) or accepts
  the +75 KB payload.

## Provenance

Merges three independently-written plans:

- `plans/dynamic-openrouter-model-selector-deepseek-flash-v4-q2` →
  `docs/plans/dynamic-openrouter-model-selector.md` — contributed the Goal-level
  "shortlist membership, not an OpenRouter write" framing, the vendor filter,
  `free` from price rather than suffix, the two extra non-goals (no auto-sync,
  no bulk add), the counted reveal toggle's ancestor, and the docs step. Not
  taken: its `/api/chat/openrouter/catalog` path, `fetch_catalog()` inside
  `chat/openrouter.py`, a hard 502 in place of stale-if-error, and the
  sort/filter set.
- `plans/dynamic-openrouter-model-selector-deepseek-flash-v4-q8` →
  `docs/plans/openrouter-model-selector-plan.md` — contributed the file map of
  the current state, the ASCII layout, the API summary/envelope, the
  "no schema change" rationale, the edge-case list (variants, label drift,
  empty list honored, cache invalidation), the measured-payload caveat, the
  manual pass, and the open-decisions-with-defaults format (kept here as the
  resolved table). Not taken: mounting the picker without keeping the JSON
  editor, and per-token pricing in the payload.
- `plans/dynamic-openrouter-model-selector-qwen-3-8-flash-next` →
  `docs/plans/dynamic-openrouter-model-selector.md` — the most complete draft
  and the base for this document: non-goals, verified upstream facts, the
  `openrouter_catalog.py` module split, TTL + lock + stale-if-error,
  `known_ids()`, the filter/sort/toggle set, the shared-validator extraction,
  rollout phases, and the docs step.

All upstream numbers above were re-verified against the live API on 2026-07-29
(425 models; the source plans said 395) and two of its claims were corrected:
the "non-text output" test hides zero rows as originally written, and
`expiration_date` is dominated by the `2098-12-31` sentinel.
