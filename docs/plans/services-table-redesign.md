# Services table redesign — implementation plan

Redesign of the v2 dashboard home page (`/v2`): the services table and the GPU
monitor above it. A static HTML mockup of the target design lives next to this
plan — open `docs/plans/services-table-redesign.mockup.html` in a browser
before writing any code. The mockup is light-themed; the implementation must
work with **both** themes via the existing semantic tokens (see "Theming"
below), not the mockup's hardcoded hex values.

**Scope: frontend only.** Every piece of data the redesign needs is already in
the API payloads. No backend changes.

## Why (the problems being fixed)

1. **Red is meaningless today.** `StatusLabel` in `ServicesTable.jsx` renders
   every `exited` container in danger red — but exit 0 is a clean stop and 137
   is docker's SIGKILL. With ~13 stopped services the page screams "broken"
   while a genuinely crashed service (exit 1 or 255) looks identical to the
   healthy stopped ones.
2. **Running services are buried.** Rows are in API order (alphabetical); the
   1–2 running services — the ones holding VRAM — are lost mid-table.
3. **API-key noise.** Every row repeats the same default key
   (`key-d45f8969...` × 19), doubling row height for zero information.
4. **Status is triple-encoded** (dot + colored text + full-row tint).
5. **Size lacks context.** "80.76 GB" means nothing without the GPU's total
   VRAM next to it.
6. **Mixed icon language.** Unicode glyphs (`▶ ✎ ✕ ⧉ ◎`) plus one FontAwesome
   icon; Delete sits one mis-click from Logs; the `◎` set-public-port button
   is cryptic and shown on every row.
7. **Layout jump.** "Loading GPU info..." renders as a bare paragraph, then the
   500px GPU card + graph pop in and shove the table down.

## Code geography

All paths relative to repo root.

| File | Role |
|---|---|
| `dashboard/frontend/src/components/ServicesTable.jsx` | The table, mobile cards, toolbar, actions — most of the work |
| `dashboard/frontend/src/components/GpuMonitor.jsx` | GPU SSE consumer, keeps 60s history, renders GpuStats + GpuGraph |
| `dashboard/frontend/src/components/GpuStats.jsx` | 500px stats card (name, memory bar, temp, util, power) |
| `dashboard/frontend/src/components/GpuGraph.jsx` | Canvas line chart, theme-aware via `--color-chart-*` tokens |
| `dashboard/frontend/src/components/RotateDefaultKeyModal.jsx` | Existing, keep as-is |
| `dashboard/frontend/src/hooks/useServicesSSE.js` | Services snapshot + deltas |
| `dashboard/frontend/src/hooks/useGpuSSE.js` | GPU stats stream (~3s tick) |
| `dashboard/frontend/src/App.jsx` | Route `/` renders `<GpuMonitor /><ServicesTable />` |
| `dashboard/frontend/src/index.css` | Semantic theme tokens (dark default + `[data-theme="light"]`) |

Commands (from `dashboard/frontend/`): `npm run dev`, `npm test` (vitest),
`npm run lint`, `npm run build`.

## Data contract (already available, verify — don't extend)

Service objects from `useServicesSSE`:

- `name`, `status` (`"running" | "exited" | "not-created"`), `exit_code`
  (number or null), `host_port` (9999 means none), `api_key`,
  `model_size` (bytes, numeric), `model_size_str` (e.g. `"80.76 GB"`),
  `openwebui_registered` (bool), `container_id`.
- **Caveat:** SSE *deltas* (`applyDeltaToState`) only carry
  `name`/`status`/`container_id` — a delta for a brand-new service produces a
  row missing `model_size`, `api_key`, etc. All new rendering must tolerate
  missing fields (the current code already does; keep it that way).

GPU objects from `useGpuSSE` (array `gpus`):

- `index`, `name`, `memory.used` / `memory.total` (MiB),
  `temperature.current`, `utilization.gpu_percent`,
  `power.draw` / `power.limit.current`.

The public port is `3301` (hardcoded in `PortInline` today; keep a named
constant `PUBLIC_PORT = 3301` in one place).

## Theming

The app has a full semantic token system in `index.css` (issue #5): dark is
the default `:root`, light overrides under `[data-theme="light"]`. **Never
hardcode colors in JSX.** Map the mockup like so:

- Mockup greens/reds → existing `success` / `danger` token families
  (`bg-success-subtle`, `text-success-fg`, etc.).
- Engine badge colors → existing `--color-badge-{llamacpp,vllm,ds4,webui,neutral}-*`.
- Chart lines/grid → existing `--color-chart-memory`, `--color-chart-compute`,
  `--color-chart-grid`.
- If a needed shade doesn't exist (e.g. a subtle pill background that works in
  both themes), **add a token pair** to `index.css` (root + light) rather than
  inlining hex. Follow the naming convention already there.

Fonts: the app already loads Archivo (UI) and IBM Plex Mono (code/labels) via
`--font-sans` / `--font-mono`. Use `font-mono` + `tabular-nums` for service
names, ports, and sizes.

## Phased delivery

Each phase is one branch + one PR, sequentially (do not start phase N+1 until
phase N is merged). Keep each PR reviewable in isolation — the table must
render correctly at the end of every phase. Suggested branch names:
`feat/services-table-redesign-p1` … `-p5`.

---

### Phase 1 — status semantics + derived-state module

**New file** `dashboard/frontend/src/components/serviceState.js` (pure, no
React) exporting:

```js
export const CLEAN_EXIT_CODES = [0, 137]  // clean stop / docker SIGKILL

// → 'running' | 'failed' | 'stopped' | 'not-created'
export function deriveState(service)

// stable group order: running, failed, stopped, not-created;
// alphabetical by name within a group. Also returns per-group counts.
export function groupServices(services)
```

`failed` = `status === 'exited' && exit_code != null && !CLEAN_EXIT_CODES.includes(exit_code)`.
`exited` with exit 0/137 (or null) = `stopped`.

**In `ServicesTable.jsx`:**

- Replace `StatusDot` + `StatusLabel` with a single `StatusPill` component:
  - `running`: success-subtle bg, success-fg text, filled dot, label "Running".
  - `failed`: danger-subtle bg, danger-fg text, label "Failed" + mono
    `exit N` suffix.
  - `stopped`: neutral (surface-strong bg, fg-muted text), label "Stopped";
    when exit code is 137 append a small mono `137` (informational, not red).
  - `not-created`: no fill, dashed border (`border-dashed border-border`),
    fg-subtle, hollow dot, label "Not created".
- Remove the full-row tint (`bg-success-subtle` on running rows). Instead give
  running rows a 3px left stripe (`box-shadow: inset 3px 0 0` via an arbitrary
  Tailwind value or a tiny CSS class) in success color, failed rows the same
  in danger.
- Rows stay in API order in this phase (grouping lands in phase 2) but the
  `groupServices` util ships now, fully tested.

**Tests** (`serviceState.test.js`): exit 0 → stopped; 137 → stopped; 1 →
failed; 255 → failed; null exit_code + exited → stopped; running; not-created;
group ordering incl. alphabetical tie-break; missing fields don't throw.

---

### Phase 2 — grouping, toolbar, key chip

**Grouping:** render rows via `groupServices`. Before each non-empty group,
a slim full-width group header row: uppercase label + count
(`Running 2`, `Failed 1`, `Stopped 9`, `Not created 6`). Header text color:
success-fg for Running, danger-fg for Failed, fg-subtle otherwise. Grouping is
derived at render time from the live services array — never store an order in
state (SSE deltas would go stale).

**Count chips** next to the "Services" heading: `N running` (success),
`N failed` (danger, omit when zero), `N idle` (neutral; stopped +
not-created). Compute client-side from `deriveState` — the `running`/`stopped`
counters in `useServicesSSE` don't know about `failed`.

**Default-key chip:** remove the per-row api_key line entirely (desktop row
and mobile card). In the toolbar add a chip: small "default key" label +
truncated mono key + copy button (reuse the copy-feedback pattern from
`CopyButton`). Source the key from the existing global-api-key endpoint
(`GET /api/services/global-api-key` — see `getGlobalApiKey` usage in the
codebase / `dashboard/routes/services.py:793`). If a service's key ever
differs from the global key, show a small key icon with tooltip on that row —
otherwise rows show nothing.

**Toolbar order:** heading + chips + connection dot | spacer | key chip,
"⟳ Rotate key" (ghost button style, opens existing `RotateDefaultKeyModal`),
filter input, "+ New service" (primary). When filtering, groups with no
matches disappear (headers included); the empty state keeps its current copy.

**Tests:** group headers render in order and hide when empty; failed chip
hidden at zero; api_key no longer rendered per row; filter hides empty groups.

---

### Phase 3 — columns: port, size-with-VRAM-bar, WebUI

**Port:** mono figure. Keep the llama.cpp-only hyperlink behavior. When
`host_port === PUBLIC_PORT`, render a small uppercase `PUBLIC` tag
(warning-subtle bg / warning-fg text) after the number. **Remove** the
per-row `◎` set-public-port button — that action moves to the overflow menu
in phase 4. `host_port === 9999` or missing → `—` in fg-subtle.

**Size:** right-align the column (header too). `model_size_str` in mono
`tabular-nums`. Underneath, a 72px × 3px bar: fill = `model_size` scaled
against **total GPU VRAM** (from `useGpuSSE`, `gpus[0].memory.total` MiB
converted to bytes; multi-GPU: use the max). Fill color: neutral
(`fg-faint`-ish) normally, success on running rows, danger + clamped to 100%
when the model exceeds total VRAM. When GPU data or `model_size` is absent,
render no bar (never a broken 0% bar). Plumb the total via a prop/context from
the GPU strip (phase 5 refactor makes this natural — until then read
`useGpuSSE` directly in `ServicesTable`; the hook is cheap and shares the
stream).

**WebUI column:** replace "✓ Registered"/"Not registered" text with a
centered ✓ (success-fg) or `—` (fg-faint), header shortened to "WebUI",
tooltip on hover ("Registered in Open WebUI"). Infra rows (open-webui): `—`.

**Tests:** public tag only on 3301; size bar width math incl. >100% clamp and
missing-data cases; WebUI check/dash rendering.

---

### Phase 4 — actions: one icon set + overflow menu

**New file** `dashboard/frontend/src/components/icons.jsx`: small inline-SVG
icon components (play, stop, restart, logs, edit, open-external, copy,
ellipsis, key, trash). `stroke="currentColor"`, 14–16px, consistent stroke
width. Replace every unicode glyph and the lone FontAwesome `fa-terminal` in
the table/cards with these (FontAwesome stays elsewhere in the app — out of
scope).

**Visible actions per row (in order):** Start *or* Stop (primary — slightly
stronger resting color; hover tints success for start, danger for stop),
Logs, Edit, `⋯` overflow. Infra row (open-webui) keeps Open + Restart only.
Non-primary actions rest at `text-fg-subtle`/near-invisible and brighten on
row hover — but must remain **keyboard-reachable and focus-visible** at all
times (opacity trick, not `display:none`; add `focus-visible` ring styles).

**Overflow menu** (custom popover — check first whether any dropdown/popover
component already exists under `src/components/` and reuse it if so):

- "Make public port (3301)" → existing `handleSetPublicPort`; hidden when the
  row already is the public port.
- "View YAML" → navigate to the service details route that shows YAML if one
  exists; otherwise omit this item (do not build a new YAML view).
- "Rename" → service details page handles rename today; link there, or omit.
- "Delete" (danger-fg, separated by a divider) → existing confirm + DELETE
  flow.

Menu closes on outside click and Escape; trigger has `aria-haspopup="menu"`
and `aria-expanded`.

While a transition is in-flight, swap the primary icon for a spinner
(existing `...` text is fine to replace with a small CSS spinner) and disable
the row's buttons — same semantics as today's `transitioning` map.

**Tests:** overflow opens/closes (incl. Escape), delete confirm still fires
the DELETE call, set-public-port item hidden on the public-port row, primary
button flips between start/stop by state.

---

### Phase 5 — GPU strip with utilization graph

Replace the current stacked `GpuStats` card + wide `GpuGraph` block with one
compact **GpuStrip** per GPU, docked directly above the services toolbar so
the strip and table read as a single panel.

**Layout** (single row, ~56–64px tall, wraps on narrow screens):

1. GPU name (bold, truncating, `title` attr for the full name).
2. Memory bar (flex-grow, min 160px / max 320px, 6px tall, accent fill) —
   fill = used/total.
3. Figures in mono `tabular-nums`: `78.4 / 97.9 GB · 19.5 GB free` (convert
   MiB → GB, one decimal; **free = total − used** is the number the size bars
   in the table key off, make it visually primary), then compact
   `· 62°C · 315 W · 87%`.
4. **The 60s history graph** — this is required, do not drop it. Reuse
   `GpuGraph.jsx` (canvas, theme-aware `cssVar` redraw — keep that mechanism
   and its theme-change repaint) at a reduced height (~40–48px) and a fixed
   width slot (~200–280px) at the right end of the strip. Keep both series
   (memory % + compute %) and the existing `MAX_POINTS = 20` ≈ 60s window.
   Replace the verbose legend with two tiny color-keyed labels ("mem",
   "gpu") or a `title` tooltip; the `--color-chart-*` tokens stay the source
   of truth for line colors.

**Mechanics:**

- Keep `useGpuSSE` and the history accumulation currently in
  `GpuMonitor.jsx` (`updateHistories`) — lift it unchanged into the new strip
  container (or keep `GpuMonitor` as the container and have it render strips).
- **No layout jump:** the strip container has a fixed height from first
  paint. While `gpus === null` render a skeleton strip (pulsing placeholder
  bars) at identical height, not a text paragraph. `error` / no-GPU states
  render inside the same fixed-height strip in fg-muted.
- Multi-GPU: one strip per GPU, stacked.
- Wire the total-VRAM value into the size bars from phase 3 here if a
  context/prop plumb was deferred.
- `App.jsx` route `/` likely changes from `<GpuMonitor /><ServicesTable />`
  to a single composed component (or GpuMonitor renders the strip and the
  fragment stays) — either is fine; keep the diff minimal.

**Tests:** MiB→GB formatting, free-memory math, skeleton renders at fixed
height when `gpus === null`, history trimming still capped at 20 points
(existing behavior, move the test if one exists).

---

### Phase 6 (small) — mobile cards + polish

- Bring `ServiceCard` (the `md:hidden` stacked card) to parity: StatusPill,
  no api_key line, new icons, overflow menu, PUBLIC tag, size bar optional
  (fine to show just the mono size on mobile).
- Row density: desktop rows are single-line now — tighten padding
  (`py-2`/`py-2.5` instead of `py-3`) and verify a 20-service table fits a
  1440p viewport without scrolling inside the panel.
- Sweep for leftovers: unused `StatusDot`/`StatusLabel`/`CopyButton`-glyph
  code, the old `PortInline` public-port button, dead Tailwind classes.
- `npm run lint` clean.

---

## Acceptance checklist (final state)

- [ ] Exit 0 / 137 rows are neutral; only real crash exits are red.
- [ ] Order: Running → Failed → Stopped → Not created, each under a labeled
      group header with counts; chips summarize (`N running · N failed · N idle`).
- [ ] No API key on any row; one copyable default-key chip in the toolbar next
      to Rotate key.
- [ ] Status appears exactly once per row (pill) + left stripe on
      running/failed.
- [ ] Size right-aligned, tabular-nums, VRAM-scaled bar; >VRAM models clamp
      with danger fill; missing data degrades gracefully.
- [ ] One SVG icon language; Delete/Rename/YAML/public-port live in `⋯`;
      focus-visible works on all controls.
- [ ] GPU strip: fixed height (no jump), memory bar, used/free GB, temp,
      power, util, **and the 60s memory+compute canvas graph**, all
      theme-aware in dark and light.
- [ ] Mobile cards at parity; `npm test` and `npm run lint` pass; both themes
      checked manually.

## Process notes for the implementer

- One branch + PR per phase, merged sequentially, per this repo's workflow.
- Real data to sanity-check against: the dashboard runs at
  `http://localhost:3399/v2`; ~19 services exist in `services.json`
  (`open-webui` is the only infra service).
- **Never start/stop/restart the LLM containers or the dashboard service to
  test** — use `npm run dev` (Vite proxies the API) and read-only browsing.
- Do not edit the legacy `dashboard/static/` frontend; this is v2-only.
- No AI attribution in code, commits, or PRs.
