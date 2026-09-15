# NInfer metrics — plan (issue 195)

**Issue:** #195 `[PLAN] Add ninfer metrics` — this document is the deliverable for the
issue. The implementation sequence at the bottom is the follow-up work.

**Baseline:** `origin/main` at `db82406` (post-PR-194 merge `5dfd75d`); NInfer pinned at
`d4929686` (`origin/master` — zero commits since the pin, verified 2026-09-13).

## 1. Goal and scope

Enable the existing **Live Metrics** panel and the `/api/services/<name>/metrics`
contract for `template_type: "ninfer"` services, with data sourced from NInfer's own
runtime statistics.

| Req | Requirement |
|---|---|
| R1 | `GET /api/services/<ninfer-service>/metrics` returns parsed, curated metrics with `engine: "ninfer"` for a running ninfer service |
| R2 | The dashboard Live Metrics panel renders for ninfer services: running/waiting request counts, cumulative prompt/generated token totals with live rates, active-KV gauge, prefix-hit gauge |
| R3 | Absent spec-acceptance data renders as "—"/hidden (no crash, no fake zero) |
| R4 | vLLM / llama.cpp / ik_llama.cpp metrics and slots paths are unchanged; metrics for other engines remain unavailable as today |
| R5 | The engine-side change is a tracked patch under the existing pin+patch discipline (Dockerfile, check-upstream skill, engine guide) |
| R6 | `/metrics` on the engine stays behind the service API key; the dashboard scrape already sends it |

**Acceptance (observable):**
- `curl 127.0.0.1:<host-port>/metrics` without a key → 401; with the service key → 200,
  Prometheus text exposing the §3.1 family set.
- `GET /api/services/ninfer-qwen38-27b-nvfp4/metrics` (dashboard key) →
  `{"metrics": {"ninfer:…": …}, "engine": "ninfer", "scraped_at": …}` with non-empty
  metrics for a running service.
- Dashboard service-detail page of a running ninfer service: the Live Metrics panel is
  live (not "disabled", not "No metrics available"); idle message when stopped.
- Dashboard suite and frontend suite pass with the new tests (§5).

**Non-goals / explicit exclusions:**
- **Spec-acceptance metrics** (Spec Accept donut, SpecDecodeBar). NInfer keeps
  draft/accept counts per request only (`GenerationMetrics.speculative_*`,
  `src/serve/generation_service.h`); there is no service-level aggregate in
  `RuntimeStats` (`include/ninfer/types.h:885`). Creating one means new atomics inside
  the engine runtime — a much larger patch. Phase 1 leaves the gauge "—" (the panel
  components already render undefined as "—" — `GaugesRow.jsx:54-56`, and
  `SpecDecodeBar` is hidden when `specPerPos` is null — `MetricsPanel.jsx:19-24`).
  Follow-up option, documented here rather than deferred silently.
- **`/slots` parity.** NInfer exposes no per-lane generation state; the slots endpoint
  stays llama.cpp-only.
- **Preemption counter.** NInfer's pressure counters (`pressure_*_evicted`) are KV
  evictions, a different mechanism from vLLM preemption; the Preempt cell stays "—".
- **Reasoning levels, Open WebUI, benchmarking** — untouched by this work.

## 2. Verified current behavior

Dashboard side (all at baseline):

- `routes/metrics.py:154-158` — `get_service_metrics` gates on
  `template_type in ("vllm", "llamacpp")`; anything else returns `{"metrics": {}}` with
  the engine name. `ik_llamacpp` is therefore empty today (known, documented in the
  engine guide).
- `routes/metrics.py:_fetch_metrics` — scrapes `http://127.0.0.1:<host_port>/metrics`
  with the service `api_key` as a Bearer header, 2 s timeout; non-200 or connection
  error → `{}`. The scrape already sends the key — no dashboard auth plumbing is
  missing for an authenticated engine endpoint.
- `routes/metrics.py:_parse_metrics` — `prometheus_client.parser` over the text,
  whitelisted by `VLLM_CURATED_METRICS` / `LLAMACPP_CURATED_METRICS`; one special case
  flattens vLLM's `…_per_pos_total` into `position_N` keys (vLLM-only branch).
- Frontend `useServiceMetrics.js` — polls the API every 200 ms, renames `llamacpp:`
  names to `vllm:` names via a table (`LLAMACPP_TO_VLLM`, lines 10-17) and reads only
  `vllm:*` keys downstream: `prompt_tokens_total`, `generation_tokens_total`,
  `kv_cache_usage_perc` (0..1 gauge), `prefix_cache_hits/queries_total`,
  `spec_decode_num_accepted_tokens_total` / `num_draft_tokens_total`,
  `num_requests_running` / `num_requests_waiting`, `num_preemptions_total`. Token rates
  are client-side counter deltas for non-llama.cpp engines (the llama.cpp branch
  prefers `/slots` deltas).
- `ServiceDetailsPage.jsx:184` — the panel's `enabled` prop is
  `templateType ∈ {vllm, llamacpp, ik_llamacpp} && status == running`.
- `test_metrics.py` — the test pattern: fixture builds a temp compose + services.json,
  mocks `routes.metrics.requests.get` with sample Prometheus text, asserts engine gate,
  whitelist, error states, auth.

NInfer side (pinned `d4929686`, source inspected; the host's running service
`ninfer-qwen38-27b-nvfp4` on port 3302 probed live):

- **No metrics route exists.** Live probe: `GET /metrics` → **401** unauthenticated
  (the pre-routing handler guards every path but `/health` and OPTIONS —
  `src/serve/http_server.cpp:355-357`), **404** with a valid key. Registered routes are
  `/health`, `/v1/models`, `/v1/models/<id>`, `/v1/chat/completions`,
  `/v1/responses*`, `/v1/messages*` (`http_server.cpp:register_routes`).
- **The data exists in-process.** `GenerationService` exposes
  `runtime_stats()` / `memory_summary()` / `is_available()`
  (`src/serve/generation_service.h:107/109/111`). `RuntimeStats`
  (`include/ninfer/types.h:885`) carries: `running_requests`, `prefilling_requests`,
  `decode_ready_requests`, `waiting_requests`, `computed_prefill_tokens`,
  `committed_decode_tokens`, `decode_rounds`, `reused_prompt_tokens`,
  `device_main_kv_occupied_pages`, `host_kv_occupied_bytes`, and the pressure
  counters. `MemorySummary` (`types.h:827`) carries `kv_capacity_page_groups` /
  `kv_capacity_max_page_groups`. The engine's own periodic reporter reads exactly these
  snapshots every `--log-stats-interval-ms` (default 5000) —
  `http_server.cpp:run_stats_reporter` — so a second reader at scrape frequency is the
  same access pattern.
  **[Corrected 2026-09-15, see §8: not the same access pattern.]** The reporter reads
  only `runtime_stats()`. `memory_summary()` is *not* a peer of `runtime_stats()`: it
  takes `execution_mutex_`, while `runtime_stats()` takes `stats_mutex_`. Reading the
  pair at scrape frequency is therefore not a read-only variant of the reporter's
  pattern — it contends with generation. §8 records what that cost and how the patch now
  avoids it.
- **No service-level spec aggregation** (see §1 exclusions): per-request
  `draft_n` / `draft_n_accepted` only (`src/serve/openai_chat_response.cpp:69-71`).
- **Patch discipline precedent:** `ninfer/Dockerfile:34-35` applies
  `ninfer-cu129-port.patch` with `git apply` at build time; a build-time apply failure
  fails the image build loudly. ds4 carries two independent patches the same way.
- **Upstream:** `git rev-list --count d4929686..origin/master` → 0 (2026-09-13). There
  is no upstream `/metrics` to adopt; waiting for one is not a plan.

## 3. Proposed design and contracts

### 3.1 Engine patch — a protected `GET /metrics` rendering Prometheus text

New file `ninfer/ninfer-metrics.patch` (a plain `git diff` of the pinned tree, same
nature as the port patch), applied in `ninfer/Dockerfile` after the port patch:

```dockerfile
COPY ninfer-cu129-port.patch /src/ninfer-cu129-port.patch
RUN git -C /src apply --verbose /src/ninfer-cu129-port.patch
COPY ninfer-metrics.patch /src/ninfer-metrics.patch
RUN git -C /src apply --verbose /src/ninfer-metrics.patch
```

The two patches touch disjoint files (CMake/`.cu` vs `src/serve/*`), so sequential
apply is clean. They stay **separate files** because their retirement conditions differ:
the port patch dies when upstream accepts CUDA ≤ 12.9; the metrics patch dies when
upstream ships a stats endpoint of its own.

Patch contents (minimal, two files, no CMake change):

- `src/serve/http_server.h` — one new private method declaration
  `void handle_metrics(const httplib::Request&, httplib::Response&) const;`.
- `src/serve/http_server.cpp` — route registration
  `server_.Get("/metrics", …)` next to `/health`, plus the handler:
  - `service_ == nullptr || !service_->is_available()` → **503** (mirrors `/health`,
    `http_server.cpp:428-433`);
  - otherwise read `service_->runtime_stats()` and `service_->memory_summary()` and
    render Prometheus text (`# HELP` / `# TYPE` + one sample line per family, no
    labels) from an anonymous-namespace formatter. **(Revision 1 drops the
    `memory_summary()` call from the scrape path — see §8.)**
- **No auth-handler change.** The pre-routing guard already protects `/metrics`
  (verified live: 401 before the route exists, so it will 401 after too until the key
  is presented), and `_fetch_metrics` already presents the service key. This is the
  smallest possible engine surface change and the more conservative exposure choice.

**Emitted family set** (the contract the dashboard whitelists):

| Prometheus name | TYPE | Source (pinned `d4929686`) | Panel meaning |
|---|---|---|---|
| `ninfer:prompt_tokens_total` | counter | `RuntimeStats.computed_prefill_tokens` | prefill work done (excludes reused checkpoint-prefix tokens — same semantics as the panel's llama.cpp `/slots` prompt rate) |
| `ninfer:generation_tokens_total` | counter | `RuntimeStats.committed_decode_tokens` | tokens committed by decode rounds |
| `ninfer:decode_rounds_total` | counter | `RuntimeStats.decode_rounds` | extra, debug |
| `ninfer:num_requests_running` | gauge | `RuntimeStats.running_requests` | RequestStrip "Running" |
| `ninfer:num_requests_waiting` | gauge | `RuntimeStats.waiting_requests` | RequestStrip "Waiting" |
| `ninfer:num_requests_prefilling` | gauge | `RuntimeStats.prefilling_requests` | extra; see §5 gate G3 |
| `ninfer:kv_cache_usage_perc` | gauge | `device_main_kv_occupied_pages / kv_capacity_page_groups`, clamped 0..1 (0 when denominator 0) | "Active KV" donut (0..1, like vLLM) |
| `ninfer:kv_occupied_pages` | gauge | `RuntimeStats.device_main_kv_occupied_pages` | extra, raw |
| `ninfer:kv_capacity_page_groups` | gauge | `MemorySummary.kv_capacity_page_groups`, captured at attach since revision 1 | extra, raw |
| `ninfer:prefix_cache_queries_total` | counter | `computed_prefill_tokens + reused_prompt_tokens` (prompt tokens presented) | prefix-hit ratio denominator |
| `ninfer:prefix_cache_hits_total` | counter | `RuntimeStats.reused_prompt_tokens` | prefix-hit ratio numerator |
| `ninfer:host_kv_occupied_bytes` | gauge | `RuntimeStats.host_kv_occupied_bytes` | extra, debug |

Notes on the mapping:

- `prefix_cache_queries_total` is a **derived counter** (sum of two monotonic
  counters, hence monotonic); the client-side delta math in the hook stays valid.
  `hits ≤ queries` holds by construction, so the ratio is in [0, 1].
- The `prompt_tokens_total` semantic (work done, not tokens presented) is deliberate:
  the panel's prompt rate is "prefill speed" for every engine (llama.cpp's branch
  deliberately uses processed-token deltas from `/slots`), and one counter keeps one
  meaning across the cumulative line and the sparkline.
- No `ninfer:num_preemptions_total`, no spec families → RequestStrip "Preempt" and the
  Spec Accept donut render "—"; SpecDecodeBar is hidden (R3).
- Counter resets on container restart are handled by the existing
  `Math.max(0, delta)` clamp in the hook — same as every engine today.

### 3.2 Dashboard contract

`routes/metrics.py`:

- Gate: `template_type not in ("vllm", "llamacpp", "ninfer")` → empty (R1, R4).
- New `NINFER_CURATED_METRICS` set = the 12 names in §3.1 (the whitelist keeps
  uninteresting families out, matching the existing mechanism). The curated-set
  selection in `_parse_metrics` is currently a binary expression
  (`VLLM_CURATED_METRICS if engine == "vllm" else LLAMACPP_CURATED_METRICS`,
  `routes/metrics.py:60`); it becomes a 3-way lookup keyed on `engine`.
- `engine` payload value: `"ninfer"`; the vLLM-only `per_pos` flattening branch in
  `_parse_metrics` stays vLLM-only (ninfer emits no labeled samples in phase 1).
- `/slots` route unchanged; a ninfer service hits the existing 400 branch.

Frontend:

- `useServiceMetrics.js` — add a `NINFER_TO_VLLM` table (7 rows, §3.1 "Panel meaning"
  column) and make `normalizeMetrics` table-driven for both engines:

  ```js
  const RENAMES = { llamacpp: LLAMACPP_TO_VLLM, ninfer: NINFER_TO_VLLM }
  const rename = RENAMES[engine]
  if (!rename) return raw
  ```

  The hook then needs **no other changes**: it reads `vllm:*` keys, computes rates
  from counter deltas (the non-llama.cpp branch), skips the `/slots` fetch for
  `eng !== 'llamacpp'`, and every downstream component already tolerates the missing
  spec/preemption values.
- `ServiceDetailsPage.jsx:184` — add `'ninfer'` to the `enabled` condition.

Docs:

- Engine guide (CLAUDE.md, NInfer section): move the metrics panel out of
  "Not supported" and record the emitted family set + the authed-endpoint decision.
- `.pi/skills/check-upstream/SKILL.md` NInfer section: second patch
  (`ninfer-metrics.patch`), its retirement condition, and the cheap-apply check for it.
- `CHANGELOG.md` entry.

### 3.3 Compatibility and state

- **Old image + new dashboard** (the intermediate rollout state): the scrape gets
  401→non-200 → `_fetch_metrics` returns `{}` → the panel shows "No metrics available".
  Graceful; no error state, no broken panel.
- **New image + old dashboard**: the gate returns `{"metrics": {}}` for ninfer as
  today; the panel stays disabled. Also graceful.
- No `services.json` schema change, no migration, no per-service opt-in. A ninfer
  service gets metrics purely by being a ninfer service with a rebuilt image.
- No container flags: the endpoint is always on, like vLLM's default Prometheus
  surface; llama.cpp's explicit `--metrics` flag has no ninfer analogue because the
  route is part of the binary the image ships.
- Scraper load: ~5 small GETs/s per open panel rendering ~12 lines from two in-memory
  struct snapshots — the engine already does the same read every 5 s for its reporter.

### 3.4 Alternatives considered

| Alternative | Why not |
|---|---|
| Parse `--request-log-jsonl` (the dashboard tails the engine's JSONL) | That file is a versioned *measurement* format (`kRequestLogSchemaVersion = 20`, `request_log.h`) owned by upstream's campaign tooling; a live dashboard panel coupled to it breaks on any upstream schema bump. Opt-in flag, unbounded growth, no rotation. |
| Tail `docker logs` for the periodic throughput line | Racy at 200 ms polling, lossy formatting, no gauges — only the reporter's delta view. |
| Dashboard-only adapter over `/health` + `/v1/models` | Yields liveness + model id, not metrics; not the panel's contract. |
| Upstream PR first, bump the pin when merged | No timeline control; the pin+patch pattern is already established in this repo (port patch, ds4), and the patch retires when upstream ships the feature. |
| JSON `/stats` endpoint + new dashboard parse path | A second fetch/parse/whitelist mechanism next to the Prometheus one; Prometheus text reuses `_fetch_metrics`, `_parse_metrics`, and the curated-set mechanism unchanged. |

## 4. Implementation sequence

One follow-up PR (or two: 1+2 ship independently of 3 by §3.3). Files relative to the
repo root.

| Step | Files / symbols | Behavior | Depends on | Acceptance test |
|---|---|---|---|---|
| 1. Engine patch | `ninfer/ninfer-metrics.patch` (new), `ninfer/Dockerfile` (two lines), `.pi/skills/check-upstream/SKILL.md` | `GET /metrics` route per §3.1; build-time apply | — | G1 live probe: unauth 401, authed 200 with all 12 families, 503 while unavailable (probe before `attach`, or a stopped-then-starting container); `git apply --check` passes on a fresh clone of the pin |
| 2. Dashboard | `dashboard/routes/metrics.py` (`NINFER_CURATED_METRICS`, gate, engine pass-through); `dashboard/tests/test_metrics.py` (`TestNinferMetrics` + ninfer service in fixture, slots-400 case) | R1, R4 | 1 (for the live gate; unit tests mock the fetch and need no image) | `venv/bin/python -m pytest tests/test_metrics.py -q` |
| 3. Frontend | `dashboard/frontend/src/hooks/useServiceMetrics.js` (`NINFER_TO_VLLM`, table-driven `normalizeMetrics`), `…/ServiceDetailsPage.jsx:184`; `…/hooks/useServiceMetrics.test.js` (ninfer rename test mirroring the llamacpp one; assert no `/slots` fetch for `engine: "ninfer"`) | R2, R3 | 2 | `npm test`, `npm run build` |
| 4. Docs | CLAUDE.md NInfer section, `CHANGELOG.md` | R5 | 1-3 | Manual: copy still matches code (review gate) |

Step 1 is the long pole (full CUDA source build of the image, `./build-ninfer.sh`);
steps 2-3 are short and land in the same PR.

## 5. Verification

**Checks actually run (planning evidence, 2026-09-13):**

- Live probes against `ninfer-qwen38-27b-nvfp4` (port 3302): `/metrics` 401/404,
  `/health` 200, `/v1/models` 200 (§2).
- Upstream delta: `git rev-list --count d4929686..origin/master` → 0.
- Source claims cited in §2 (route table, auth handler, `RuntimeStats`,
  `GenerationService` accessors, per-request-only spec stats, reporter access
  pattern, patch-apply mechanics).

**Tests proposed (requirement → test):**

| Req | Test |
|---|---|
| R1 | `test_metrics.py::TestNinferMetrics` — `SAMPLE_PROMETHEUS_TEXT_NINFER` (12 families + an off-whitelist `ninfer:extra` family): happy path returns `engine: "ninfer"` with the curated names and without the extra; connection error → `{}`; no auth → 401 |
| R1/R4 | slots endpoint: ninfer service → 400 (mirrors the existing vLLM case); vllm/llamacpp fixtures unchanged and green |
| R2 | `useServiceMetrics.test.js` — ninfer payload renames to `vllm:*` keys; derived data points carry running/waiting, rates from counter deltas, `kvCache`, `prefixHitRatio`; `specAcceptRatio` stays `undefined`; no `/slots` call issued for `engine: "ninfer"` |
| R3 | same test file: with spec keys absent, `specPerPos` stays null (SpecDecodeBar hidden) — and `GaugesRow`/`RequestStrip` render "—" for undefined (covered by existing component tests + the live check) |
| R4 | full dashboard + frontend suites; the vLLM/llama.cpp metrics tests are untouched and green |
| R5 | `apply --check` of both patches in sequence on a fresh clone of the pin (G1); check-upstream skill documents the second patch |
| R6 | G1 unauth-401 probe |

**Live acceptance gates (not unit-testable):**

- **G1 — image build + probe.** `./build-ninfer.sh`, recreate
  `ninfer-qwen38-27b-nvfp4`, then: unauth `/metrics` → 401; authed → 200 with all 12
  families; `/health` still 200; a chat completion still works (route addition did not
  disturb the server).
- **G2 — KV gauge units.** `device_main_kv_occupied_pages` is a target-level physical
  page count while `kv_capacity_page_groups` is the capacity resolver's unit
  (`src/targets/qwen3_6/impl/runtime/program_impl.h:9482`,
  `src/runtime/engine/causal_score_core.h:86`). NInfer's own logs do not pair them:
  the occupancy field is only compared between snapshots to decide whether a stats
  report is worth emitting (`src/serve/http_server.cpp:109-110`), and exported to the
  request JSONL as `device_main_kv_pages` (`src/serve/request_log.cpp:790`); the one
  `pages {}/{}` log line is `OperationalLog::engine_capacity`
  (`src/serve/operational_log.cpp:455-461`) pairing `kv_capacity_page_groups` with
  `kv_capacity_max_page_groups` — capacity against capacity, both `MemorySummary`
  fields. The ratio therefore has no in-tree precedent and its units are not proven
  1:1 from source. Gate: run a growing-context workload
  and confirm the gauge climbs with context, stays within [0, 1], and tracks
  `nvidia-smi` VRAM growth. If the scale is wrong, expose the raw pair (already
  curated) and fix the ratio before declaring R2 done.
- **G3 — Running semantics.** Confirm under 2 concurrent requests that
  `running_requests` (the mapped gauge) shows the active lanes as the panel expects;
  if the engine's `running` state excludes prefilling requests and the panel reads
  low, map `running + prefilling` instead (one-line change in the patch;
  `num_requests_prefilling` is already emitted to tell which).

## 6. Rollout and risks

- **Rollout:** merge → `./build-ninfer.sh` (long) → `docker compose up -d --force-recreate
  ninfer-qwen38-27b-nvfp4` → verify G1-G3. Only the ninfer container is recreated.
- **Rollback:** dashboard side is a plain revert; engine side is a rebuild without the
  metrics patch (or restore the previous image). No data is written anywhere by this
  feature; no migration to undo.
- **Patch maintenance:** the metrics patch is a plain `git diff` of the pinned tree;
  a future pin bump that fails `git apply` fails the image build loudly (existing
  property of the port patch). The check-upstream skill's "cheap check" extends to both
  patches; retirement of either is a two-line Dockerfile edit.
- **Risk — 200 ms scrape on the engine:** bounded (two struct reads, ~12-line render);
  same access pattern as the 5 s reporter. No lock added in the patch; if the live
  checks show contention, that is a patch revision, not a dashboard workaround.
  **Realised:** live checks showed contention, and the contingency was followed — see §8.
  The claim that the scrape had the reporter's access pattern was wrong (§2 correction).
- **Risk — KV ratio unit mismatch (G2)** is the one contract in this plan not fully
  proven from source; the raw counters are emitted regardless, so a wrong ratio is a
  visible fix, not a silent one.

## 7. Readiness

**Ready for implementation.** G2/G3 are named acceptance gates on one formula and one
mapping, each with a one-line fallback and the raw values already in the emitted set —
they do not block starting step 1. The only open question worth a decision before
coding is deliberately none: the exclusions in §1 (spec metrics, slots, preemption)
are the scope, and the follow-up spec-counter patch is recorded there for whoever
picks it up next.

## 8. Revision 1 — the scrape blocked behind generation (2026-09-15)

The first live run reproduced the symptom the operator reported: points arrive very
slowly, spike, and disappear for the duration of a generation. Measured against the
deployed image (pin `d4929686`), one 3000-token generation:

| Event | Wall clock | Detail |
|---|---|---|
| generation start | `1789501831.854` | 3000 tokens, non-streaming |
| scrape issued | `1789501833.882` | t+2.0 s into the generation |
| scrape returned | `1789501858.008` | **24.117 s — exactly at generation end** |

Four consecutive dashboard-shaped scrapes (2 s timeout) all timed out during a
1500-token generation; the first success afterwards came back in 0.663 s. Idle, the
same endpoint answers in 0.4–0.7 ms. During the blocked window the engine's own
reporter kept ticking (`decode 106.6 tok/s … 110.8 … 115.4`), and `/v1/models` answered
in under 1 ms — so the counters were live and published; only the HTTP pull was stuck.

**Cause.** `handle_metrics` rendered from `runtime_stats()` **and** `memory_summary()`.
`runtime_stats()` takes `stats_mutex_` and returns the published snapshot; `memory_summary()`
takes `execution_mutex_` (`engine_core.h:235-236`), the same mutex `worker_loop()` holds
across every execution unit, releasing it only for a 1 ms condition-variable wait between
units (`engine_core.h:1962-2034`). A metrics thread waiting on it is barged until the
request finishes — hence a scrape latency equal to the remainder of the generation, the
dashboard's 2 s timeout firing for the whole request, and the pool of
`max_concurrency + max_pending_requests + 1 = 19` worker threads parking one scrape at a
time at 5 scrapes/s. The patch added no lock; it inherited one from an existing API.

**Fix (this revision).** The only value `MemorySummary` contributed was
`kv_capacity_page_groups`, which `KvCapacityResolution` fixes at load. `attach()` already
read `MemorySummary` once for the startup log line and runs before `listen()`, so the
capacity is now captured there into `HttpServer::kv_capacity_page_groups_`, and
`render_metrics_snapshot` takes that integer instead of a `MemorySummary`. `/metrics` now
reads `runtime_stats()` alone: sub-ms regardless of load, and no dependency on
`execution_mutex_`. Scrapes stay cheap enough that the 200 ms poll rate is still right.

**Also fixed, because a slow scrape can still happen on any engine.** The dashboard now
returns `scrape_error` instead of collapsing a failed scrape into `{}` (the panel had no
way to tell "engine idle" from "engine unreachable"), and logs the first failure of a
streak at warning rather than every one at debug. The frontend holds one scrape in flight
instead of letting 200 ms ticks stack up, and skips the datapoint on a failed scrape so
the counter baseline survives the gap — previously a gap zeroed the rate and the next
success divided the whole gap's counter delta by one 200 ms window, which is what the
"spikes" were.

**Not the cause.** The engine's 5 s reporter cadence (counters publish per execution
unit, so they advance mid-generation) and a frozen snapshot. Both were hypotheses in
earlier passes; the probe above shows live counters and a blocked pull.

**Verification.** Image rebuilt from the revised patch. `./build-ninfer.sh` compiles it.
`useServiceMetrics.test.js` pins single-flight, gap-spanning rates, and the no-point-on-
failure rule; `test_metrics.py::TestScrapeErrorSurface` pins `scrape_error` and the log
streak. G2/G3 (KV ratio units, running-request semantics) are unaffected by this revision
and remain open.
