# Live vLLM Metrics — Frontend Implementation Plan

**Captured:** 2026-05-01
**Status:** scoped / ready to build
**Backend:** `dashboard/routes/metrics.py` — complete

## Backend API Reference

`GET /api/services/<name>/metrics` (Bearer auth required)

Returns:
```json
{
  "metrics": {
    "vllm:num_requests_running":                 { "{}": 3 },
    "vllm:num_requests_waiting":                 { "{}": 1 },
    "vllm:kv_cache_usage_perc":                  { "gpu_id=0": 0.72 },
    "vllm:prefix_cache_queries_total":           { "{}": 1000 },
    "vllm:prefix_cache_hits_total":              { "{}": 800 },
    "vllm:prompt_tokens_total":                  { "{}": 50000 },
    "vllm:generation_tokens_total":              { "{}": 120000 },
    "vllm:spec_decode_num_drafts_total":         { "{}": 10000 },
    "vllm:spec_decode_num_accepted_tokens_total": { "{}": 5000 },
    "vllm:spec_decode_num_accepted_tokens_per_pos_total": { "position_0": 150, "position_1": 120 }
  },
  "scraped_at": "2026-05-01T14:32:01.234567+00:00"
}
```

For non-vLLM services or unreachable endpoints, `metrics` is `{}`. Returns 404 for unknown service names.

---

## Charting Approach

Raw Canvas 2D + SVG, matching the existing `GpuGraph` pattern. Zero new dependencies. Keeps bundle size at +0 KB. Gauges and bar charts use inline SVG; the sparkline uses Canvas 2D the same way `GpuGraph` draws GPU history.

---

## 1. Test Infrastructure

Add Vitest + @testing-library/react to the frontend. Currently zero frontend tests exist.

**New files:**
- `dashboard/frontend/vitest.config.js` — Vitest config, extends Vite's TSX/JSX + Tailwind plugin setup
- `dashboard/frontend/src/test/setup.js` — `@testing-library/jest-dom` global setup

**`package.json` additions:**

Scripts:
```json
"test": "vitest run",
"test:watch": "vitest"
```

Dev dependencies:
- `vitest`: `^3.x`
- `@testing-library/react`: `^16.x`
- `@testing-library/jest-dom`: `^6.x`
- `@testing-library/user-event`: `^14.x`

---

## 2. New Hook — `useServiceMetrics`

**File:** `dashboard/frontend/src/hooks/useServiceMetrics.js`

### Signature:
```js
export default function useServiceMetrics({ serviceName, enabled })
```

- `enabled` = `templateType === 'vllm' && runtime?.status === 'running'`

Polls `GET /api/services/${serviceName}/metrics` every 3 seconds (same cadence as `useServiceDetails` runtime polling). When `enabled` is false, returns null/empty state without polling.

### Returns:
```js
{
  metrics,
  history,
  loading,
  error,
  lastScraped
}
```

- `metrics` — current response metrics object (or `{}` on error)
- `history` — circular buffer of derived data points, max 60 entries (2-min window at 3s interval):
  ```js
  {
    promptTokensRate,    // tokens/sec, derived from delta of prompt_tokens_total
    generationTokensRate, // tokens/sec, derived from delta of generation_tokens_total
    kvCache,             // 0..1, from kv_cache_usage_perc gauge
    prefixHitRatio,      // 0..1, prefix_cache_hits_total / prefix_cache_queries_total
    specAcceptRatio,     // 0..1, spec_decode_num_accepted_tokens_total / spec_decode_num_drafts_total
    running,             // integer, num_requests_running
    waiting,             // integer, num_requests_waiting
    preemptRate          // preemptions per second
  }
  ```
- `lastScraped` — ISO timestamp from `scraped_at` response field

### Rate Computation

First scrape sets baseline (rates = 0). Subsequent scrapes compute:
```js
rate = (currentTotal - previousTotal) / deltaSeconds
```

Handles counters gracefully: on first scrape (no previous), rates are 0. On error response, skips update but keeps history intact.

---

## 3. New Components

### `MetricsPanel.jsx`

**File:** `dashboard/frontend/src/components/MetricsPanel.jsx`
**Lines:** ~50

Card wrapper (`bg-gray-800 rounded-lg border border-gray-700`) with:
- Header: "Live Metrics" title + green pulse dot (polling active indicator) + last scraped time
- 2-column grid:
  - Left column: `RequestStrip`, `TokenSparkline`
  - Right column: `GaugesRow`, `SpecDecodeBar` (conditional)
- Shows "No metrics available" placeholder with explanation when `metrics` is empty (non-vLLM engine, service not running, or /metrics endpoint unreachable)

### `RequestStrip.jsx`

**File:** `dashboard/frontend/src/components/RequestStrip.jsx`
**Lines:** ~35

Compact horizontal strip showing request state:
```
Running: 3  |  Waiting: 1  |  Preemptions: 0.2/s
```

Each value shows "—" when metric is missing (endpoint down). Uses FontAwesome icons (`fa-bolt`, `fa-clock`, `fa-arrotate`).

### `TokenSparkline.jsx`

**File:** `dashboard/frontend/src/components/TokenSparkline.jsx`
**Lines:** ~60

Canvas 2D sparkline, last 60 seconds of history. Follows the exact pattern from `GpuGraph.jsx` (DPR-aware canvas, clearRect on each render, two drawn lines):
- Blue line: prompt tokens/sec
- Green line: generation tokens/sec
- Height: `60px`
- Right-aligned label showing current rates: "Prompt: X t/s | Gen: Y t/s"
- Placeholder text when history is empty (< 2 points)

### `GaugesRow.jsx`

**File:** `dashboard/frontend/src/components/GaugesRow.jsx`
**Lines:** ~90

Three circular donut gauges rendered as inline SVG (48px diameter each), arranged horizontally:

1. **KV Cache** — `kv_cache_usage_perc` x 100. Threshold-colored:
   - Green (< 60%)
   - Yellow (60-85%)
   - Red (> 85%)
2. **Prefix Cache Hit %** — derived `prefixHitRatio` x 100. Blue.
3. **Spec Decode Accept %** — derived `specAcceptRatio` x 100. Purple.

Each gauge: donut chart + label below + percentage value. Missing data shows "—" with gray outline.

Donut SVG approach:
- Two `<circle>` elements (track + indicator)
- `stroke-dasharray` / `stroke-dashoffset` for percentage fill
- `transform="rotate(-90)"` to start at 12 o'clock

### `SpecDecodeBar.jsx`

**File:** `dashboard/frontend/src/components/SpecDecodeBar.jsx`
**Lines:** ~60

SVG horizontal bar chart. Renders only when `spec_decode_num_accepted_tokens_per_pos_total` metric exists in the response.

Horizontal bars, one per position (position_0, position_1, ...). Bar width is proportional to accepted token count, normalized to max position value.

Gold/amber color. Right-aligned value labels.

---

## 4. ServiceDetailsPage Integration

**File edit:** `dashboard/frontend/src/components/ServiceDetailsPage.jsx`

Add "Metrics" as a third tab in `TabBar`, after "Configuration" and "Logs". Uses `react-router-dom` `Link` to `/services/:serviceName/metrics`.

The existing catch-all `/*` on `/services/:serviceName/*` already covers the metrics sub-route, so `App.jsx` may not need changes. The `ServiceDetailsPage` will handle the new route via `location.pathname.endsWith('/metrics')`.

The `ServiceDetailsPage` renders `MetricsPanel` when `isMetricsRoute`, alongside the existing `isLogsRoute` check.

---

## 5. Unit Tests

### `src/hooks/useServiceMetrics.test.js`
- Derives correct token rates from counter deltas
- First scrape yields zero rates
- Correctly computes prefix hit ratio
- Correctly computes spec decode accept ratio
- Bounded history (shifts oldest entries beyond 60)
- Empty metrics on error — history not corrupted
- Polling starts/stops based on `enabled` prop

### `src/components/MetricsPanel.test.jsx`
- Renders "No metrics" placeholder for empty metrics
- Renders all sub-panels when metrics present
- `SpecDecodeBar` renders when spec-decode metric exists
- `SpecDecodeBar` is absent when no spec-decode metric
- Green pulse dot renders
- Last scraped timestamp displays

### `src/components/GaugesRow.test.jsx`
- Correct percentage display for KV cache
- Green color below 60%
- Yellow color at 70%
- Red color above 85%
- Prefix hit ratio displays correctly
- Spec accept ratio displays correctly
- Missing data renders "—"

### `src/components/RequestStrip.test.jsx`
- Running count renders
- Waiting count renders
- Preemption rate renders
- Missing data shows "—"

### `src/components/TokenSparkline.test.jsx`
- Canvas element rendered with class
- Label renders with rate values
- Empty history shows placeholder
- Legend renders blue + green lines

---

## File Summary

| File | Action | est lines |
|------|--------|-----------|
| `package.json` | Edit (scripts + deps) | +10 |
| `vitest.config.js` | New | ~8 |
| `src/test/setup.js` | New | ~3 |
| `src/hooks/useServiceMetrics.js` | New | ~90 |
| `src/components/MetricsPanel.jsx` | New | ~50 |
| `src/components/RequestStrip.jsx` | New | ~35 |
| `src/components/TokenSparkline.jsx` | New | ~60 |
| `src/components/GaugesRow.jsx` | New | ~90 |
| `src/components/SpecDecodeBar.jsx` | New | ~60 |
| `src/components/ServiceDetailsPage.jsx` | Edit | +20 |
| `src/hooks/useServiceMetrics.test.js` | New | ~120 |
| `src/components/MetricsPanel.test.jsx` | New | ~50 |
| `src/components/GaugesRow.test.jsx` | New | ~80 |
| `src/components/RequestStrip.test.jsx` | New | ~40 |
| `src/components/TokenSparkline.test.jsx` | New | ~30 |
| **Total** | **7 new + 1 edit** | **~736** |
