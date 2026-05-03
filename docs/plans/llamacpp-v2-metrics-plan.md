# Plan: llama.cpp Metrics in v2

## Goal

Enable llama.cpp services to expose Prometheus metrics and display them in the React v2 metrics tab, using the same application path currently used for vLLM metrics.

This is v2-only for the UI. The legacy frontend does not need changes.

## Current State

- vLLM metrics are fetched through `GET /api/services/<service_name>/metrics`.
- Backend metric support is implemented in `dashboard/routes/metrics.py`.
- The backend currently returns empty metrics for non-vLLM services.
- The v2 metrics UI is composed from:
  - `dashboard/frontend/src/hooks/useServiceMetrics.js`
  - `dashboard/frontend/src/components/MetricsPanel.jsx`
  - `dashboard/frontend/src/components/TokenSparkline.jsx`
  - `dashboard/frontend/src/components/RequestStrip.jsx`
  - `dashboard/frontend/src/components/GaugesRow.jsx`
- `ServiceDetailsPage.jsx` only enables metrics for running vLLM services.
- llama.cpp supports a Prometheus-compatible `/metrics` endpoint when `llama-server` is started with `--metrics`.

## llama.cpp Metrics To Surface

Curate these llama.cpp metrics:

- `llamacpp:prompt_tokens_total`
- `llamacpp:tokens_predicted_total`
- `llamacpp:prompt_tokens_seconds`
- `llamacpp:predicted_tokens_seconds`
- `llamacpp:kv_cache_usage_ratio`
- `llamacpp:kv_cache_tokens`
- `llamacpp:requests_processing`
- `llamacpp:requests_deferred`
- `llamacpp:n_tokens_max`

The main token/sec display can use either:

- frontend-derived rolling rates from `llamacpp:prompt_tokens_total` and `llamacpp:tokens_predicted_total`, matching the current vLLM approach, or
- direct server averages from `llamacpp:prompt_tokens_seconds` and `llamacpp:predicted_tokens_seconds`.

Prefer derived rolling rates for chart consistency, while still returning the direct averages for future display.

## Implementation Steps

### 1. Enable Metrics In llama.cpp Services

Update `dashboard/templates/llamacpp.j2` so generated llama.cpp services include:

```text
--metrics
```

Add `--metrics` to `LLAMACPP_LLAMA_SERVER_FLAGS` in `dashboard/flag_metadata.py` with a short description and a monitoring/server category.

Existing services will need a compose rebuild and container recreate before `/metrics` is available.

### 2. Make Backend Metrics Engine-Aware

Update `dashboard/routes/metrics.py`:

- Split curated metrics into engine-specific sets:
  - `VLLM_CURATED_METRICS`
  - `LLAMACPP_CURATED_METRICS`
- Change `_parse_metrics(text)` to `_parse_metrics(text, engine)`.
- Preserve existing vLLM behavior, including flattening `vllm:spec_decode_num_accepted_tokens_per_pos_total`.
- For `template_type == "llamacpp"`, fetch and parse the llama.cpp curated metrics instead of returning `{}`.
- Return `engine` in the API response:

```json
{
  "engine": "llamacpp",
  "metrics": {},
  "scraped_at": "..."
}
```

Keep the existing `404` behavior for unknown services and empty metrics on scrape timeout/connection failure.

### 3. Normalize Metrics In The v2 Hook

Update `dashboard/frontend/src/hooks/useServiceMetrics.js`.

Add an engine-aware normalization layer that converts raw metric names into the existing history data shape:

```js
{
  promptTokensRate,
  generationTokensRate,
  kvCache,
  prefixHitRatio,
  specAcceptRatio,
  running,
  waiting,
  preemptRate
}
```

For vLLM, preserve current behavior.

For llama.cpp:

- prompt counter: `llamacpp:prompt_tokens_total`
- generation counter: `llamacpp:tokens_predicted_total`
- KV cache ratio: `llamacpp:kv_cache_usage_ratio`
- running requests: `llamacpp:requests_processing`
- waiting requests: `llamacpp:requests_deferred`
- prefix hit ratio: unavailable, leave undefined
- spec accept ratio: unavailable from Prometheus, leave undefined
- preempt rate: unavailable, leave undefined

Use `data.engine` from the backend response. If absent, infer from metric prefixes as a compatibility fallback.

### 4. Update v2 Metrics UI Copy And Enablement

Update `dashboard/frontend/src/components/ServiceDetailsPage.jsx`.

Change metrics enablement from vLLM-only to vLLM or llama.cpp:

```jsx
enabled={['vllm', 'llamacpp'].includes(templateType) && runtime?.status === 'running'}
```

Update `dashboard/frontend/src/components/MetricsPanel.jsx` copy:

- Disabled text should say metrics are available for running vLLM and llama.cpp services.
- Empty state should refer to “the Prometheus endpoint,” not “the vLLM prometheus endpoint.”

Keep the existing panels where possible:

- `TokenSparkline` works for both engines once history is normalized.
- `RequestStrip` works for both engines, with missing fields shown as `—`.
- `GaugesRow` works for llama.cpp KV cache and shows unsupported prefix/spec gauges as `—`.

### 5. Tests

Backend tests in `dashboard/tests/test_metrics.py`:

- Add sample llama.cpp Prometheus text.
- Assert llama.cpp services return curated llama.cpp metrics.
- Assert unrelated llama.cpp metrics are filtered out.
- Update the existing “llamacpp returns empty metrics” test because that behavior should change.
- Keep vLLM parsing tests unchanged.

Frontend tests:

- Add or update `useServiceMetrics` tests for llama.cpp:
  - computes prompt token rate from `llamacpp:prompt_tokens_total`
  - computes generation token rate from `llamacpp:tokens_predicted_total`
  - passes through `llamacpp:kv_cache_usage_ratio`
  - maps `llamacpp:requests_processing` and `llamacpp:requests_deferred`
  - leaves vLLM-only ratios undefined
- Update `MetricsPanel` tests for the generic disabled/empty copy.

### 6. Verification

After implementation:

1. Rebuild compose and recreate one llama.cpp service.
2. Confirm the direct endpoint:

```bash
curl http://localhost:<llamacpp-port>/metrics
```

3. Confirm the dashboard endpoint:

```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:3399/api/services/<service-name>/metrics
```

4. Open:

```text
http://localhost:3399/v2/services/<service-name>/metrics
```

5. Generate tokens and confirm:

- token throughput chart updates
- request strip reflects processing/deferred counts
- KV cache gauge updates when llama.cpp reports it

## Acceptance Criteria

- New llama.cpp services expose `/metrics` by default.
- Backend metrics endpoint returns curated llama.cpp metrics for llama.cpp services.
- vLLM metrics behavior is unchanged.
- v2 metrics tab is enabled for running llama.cpp services.
- v2 token throughput chart works for llama.cpp.
- Unsupported llama.cpp metric panels degrade cleanly with `—`.
- Backend and frontend tests cover both vLLM and llama.cpp metric paths.

## Reference

llama.cpp server metrics documentation:

https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md#metrics
