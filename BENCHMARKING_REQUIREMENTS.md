# Benchmarking Feature Requirements

## Problem Statement

LLM-dock users have no way to measure the performance of their deployed models. When tuning llama.cpp parameters (context length, batch size, GPU layers, flash attention, etc.), users rely on subjective assessment. There is no structured way to compare performance across configurations, track throughput/latency changes, or establish baselines. This feature adds llama-bench integration to the dashboard: run benchmarks from service cards, store results in SQLite, and compare runs over time.

## Scope

### MVP (v1)

- Benchmark llama.cpp services using llama-bench (already built into the Docker image via `LLAMA_BUILD_TOOLS`)
- Dedicated benchmark page accessible from service cards
- Configure benchmark parameters before running (independent from service config)
- Benchmark parameter persistence: last run's params are pre-filled on next visit
- Live output display during execution
- Store results in SQLite
- View benchmark history per service
- Re-run benchmarks with modified parameters
- Apply benchmark configuration back to service config

### Out of Scope (v2+)

- vLLM benchmarking (different tool, different metrics -- `vllm bench serve`)
- Charts/graphs of benchmark trends
- Automated/scheduled benchmarks
- Side-by-side comparison view with diff highlighting
- Export to CSV/JSON
- Multi-GPU benchmark isolation
- Benchmark presets ("quick" vs "thorough")

---

## User Stories

### US-1: Start a benchmark from a service card

**As a** dashboard user
**I want to** click a benchmark button on a llama.cpp service card
**So that** I can measure the model's performance

**Acceptance Criteria:**
- Benchmark icon button appears on llama.cpp service cards only (not vllm, not open-webui)
- Button is always enabled for llama.cpp services (service does NOT need to be running)
- Clicking navigates to the benchmark page with the service context pre-loaded

### US-2: Configure and launch a benchmark run

**As a** dashboard user
**I want to** configure benchmark parameters before running
**So that** I can test specific scenarios

**Acceptance Criteria:**
- Parameters are **dynamic key-value pairs** (like the custom parameters feature in service setup)
- Each row is a flag name (e.g. `-p`, `-ngl`, `-fa`) and an optional value (empty = boolean flag)
- User can add/remove parameter rows freely -- no hardcoded fields, no dropdowns
- On first visit: parameter rows pre-filled from service config (one-way copy, does NOT modify the service). Common defaults: `-p 512`, `-n 128`, `-r 5`, plus relevant flags from the service config (e.g. `-ngl`, `-b`, `-ub`, `-fa`)
- On subsequent visits: parameter rows pre-filled from the most recent benchmark run for this service
- Command preview shows the exact llama-bench command that will execute, updating live as params change
- "Run Benchmark" button starts execution
- "Reset to Service Defaults" button restores params from service config
- UI shows running state with live output
- Only one benchmark can run per service at a time (409 if already running)

### US-3: View benchmark results

**As a** dashboard user
**I want to** see benchmark results after completion
**So that** I can understand my model's performance

**Acceptance Criteria:**
- Results display: prompt processing t/s (with stddev), text generation t/s (with stddev)
- Results include service name, model path, all parameters used, and timestamp
- Results stored automatically in SQLite on completion
- Failed/timed-out benchmarks show error details

### US-4: View benchmark history

**As a** dashboard user
**I want to** view past benchmark results for a service
**So that** I can compare performance across parameter changes

**Acceptance Criteria:**
- History table shows all runs for the service, sorted newest-first
- Each row shows: timestamp, key parameters (pp, tg, batch, GPU layers), pp t/s, tg t/s, status
- User can delete individual benchmark results

### US-5: Re-run with modified parameters

**As a** dashboard user
**I want to** clone a past benchmark run and modify parameters
**So that** I can A/B test configurations

**Acceptance Criteria:**
- Each historical run has a "Re-run" button
- Clicking pre-fills the configuration form with that run's parameters
- User can modify parameters before launching

### US-6: Apply benchmark configuration to service

**As a** dashboard user
**I want to** apply a benchmark run's model configuration back to my service
**So that** I can deploy the best-performing configuration I discovered through benchmarking

**Acceptance Criteria:**
- Each completed benchmark run has an "Apply to Service" button
- Clicking maps recognized benchmark flags back to service config fields (e.g. `-ngl` → gpu_layers, `-b` → batch_size, `-ub` → ubatch_size, `-fa` → flash_attn, `-t` → threads)
- Unrecognized flags are ignored (they are llama-bench-only flags like `-p`, `-n`, `-r`)
- User sees a confirmation dialog listing which service params will change
- Service must be restarted for changes to take effect (show message)

---

## Technical Specification

### Dockerfile Change

The current Dockerfile builds with `LLAMA_BUILD_EXAMPLES=OFF`. The `LLAMA_BUILD_TOOLS` flag (which controls llama-bench) defaults to ON, so llama-bench should already be available at `/llama.cpp/build/bin/llama-bench`. However, add an explicit flag to prevent future breakage:

```diff
 RUN cmake -B build \
    -DGGML_CUDA=ON \
    -DCMAKE_CUDA_ARCHITECTURES=120 \
    -DLLAMA_BUILD_EXAMPLES=OFF \
    -DLLAMA_BUILD_TESTS=OFF \
+   -DLLAMA_BUILD_TOOLS=ON \
    -DCMAKE_BUILD_TYPE=Release
```

### Execution Strategy: Temporary Container

**llama-bench does NOT require the llama-server to be running.** It loads the model file directly and benchmarks independently. Instead of `docker exec` into a running service container (which causes GPU memory contention), benchmarks run in a **temporary container** using the same image and volume mounts.

**Benefits:**
- No GPU memory contention with the running server
- Can benchmark even when the service is stopped
- Clean isolation -- benchmark doesn't affect serving
- Container is removed automatically after completion

**Mechanism:**
```
docker run --rm --gpus all \
    -v <same model volume as service> \
    llm-dock-llamacpp \
    /llama.cpp/build/bin/llama-bench -m <model_path> -o json [params]
```

The executor must read the service's volume mounts and GPU configuration from docker-compose.yml to construct the correct `docker run` command.

### File Structure

```
dashboard/
  benchmarking/
    __init__.py
    models.py          # Dataclasses for BenchmarkRun, BenchmarkParams
    db.py              # SQLite operations (CRUD, schema creation)
    executor.py        # docker run logic, background thread management
    validators.py      # Input validation for benchmark parameters
    routes.py          # Flask Blueprint with /api/benchmarks/* endpoints
  tests/
    __init__.py
    conftest.py
    test_bench_db.py
    test_bench_validators.py
    test_bench_executor.py
    test_bench_routes.py
  static/
    benchmark.html     # Benchmark page (separate from index.html)
    benchmark.js       # Benchmark page JavaScript
```

**Rationale:** Separate `benchmarking/` package registered as a Flask Blueprint keeps the new code isolated from the existing monolithic `app.py`. Separate `benchmark.html` avoids further bloating `index.html` (already 400 lines of modals). Tests go in `dashboard/tests/`.

### Database Schema

SQLite file: `dashboard/benchmarks.db`

```sql
CREATE TABLE IF NOT EXISTS benchmark_runs (
    id           TEXT PRIMARY KEY,   -- UUID4
    service_name TEXT NOT NULL,
    model_path   TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    -- status values: pending, running, completed, failed, cancelled

    -- Parameters stored as JSON object of flag→value pairs
    -- e.g. {"-p": "512", "-n": "128", "-ngl": "99", "-fa": "", "-r": "5"}
    -- Empty string value = boolean flag (no argument)
    params_json  TEXT NOT NULL DEFAULT '{}',

    -- Results (populated on completion)
    pp_avg_ts    REAL,     -- prompt processing: avg tokens/sec
    pp_stddev_ts REAL,     -- prompt processing: stddev
    tg_avg_ts    REAL,     -- text generation: avg tokens/sec
    tg_stddev_ts REAL,     -- text generation: stddev

    -- Raw output and errors
    raw_output    TEXT,    -- Full JSON output from llama-bench
    error_message TEXT,    -- Error details if status=failed

    -- Timestamps
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    started_at   TEXT,
    completed_at TEXT,

    -- Build/hardware metadata (from llama-bench JSON output)
    build_commit TEXT,
    model_type   TEXT,     -- e.g. "7B", "70B"
    model_size   INTEGER,  -- bytes
    model_n_params INTEGER,
    gpu_info     TEXT,
    cpu_info     TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_service ON benchmark_runs(service_name);
CREATE INDEX IF NOT EXISTS idx_runs_status ON benchmark_runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_created ON benchmark_runs(created_at);
```

**Design decisions:**
- **Dynamic params as JSON**: `params_json` stores all llama-bench flags as a `{flag: value}` object. Empty string value means boolean flag (e.g. `{"-fa": ""}`). This allows any llama-bench flag without schema changes.
- Flat table with denormalized results (pp and tg metrics): llama-bench produces exactly 2 result rows per run. Avoids joins.
- UUID primary key: avoids integer collision in async contexts.
- `raw_output` stored for future UI enhancements without schema changes.
- On Flask startup, scan for `status='running'` rows and mark as `'failed'` (stale recovery).
- **No separate settings table**: the most recent run's `params_json` serves as persisted settings. On first visit (no runs yet), params derived from service config.
- History table extracts display values (pp, tg, ngl) from `params_json` client-side via `JSON.parse()`.

### Parameter Loading Priority

When the benchmark page loads for a service:

1. **Query most recent benchmark run** for this service (any status)
2. **If found**: pre-fill form with that run's parameters
3. **If not found** (first visit): pre-fill from service config via `services.json`
4. **"Reset to Service Defaults" button**: always available to restore params from service config

This gives parameter persistence across visits without a separate settings table.

### API Endpoints

All endpoints use `@require_auth` and follow existing error format: `{"error": {"code": "...", "message": "..."}}`.

#### POST /api/benchmarks
Start a new benchmark run.

Request:
```json
{
    "service_name": "llamacpp-qwen3-30b-q8",
    "params": {
        "-p": "512",
        "-n": "128",
        "-r": "5",
        "-ngl": "99",
        "-b": "2048",
        "-fa": ""
    }
}
```
`service_name` is required. `params` is a JSON object of flag→value pairs. Empty string value = boolean flag (no argument). `-m` and `-o` are always set by the executor and cannot be overridden.

Response: `202 Accepted`
```json
{
    "id": "uuid-...",
    "service_name": "llamacpp-qwen3-30b-q8",
    "status": "pending",
    "message": "Benchmark queued"
}
```

Errors: 400 (invalid params / not llamacpp), 409 (already running for this service)

#### GET /api/benchmarks
List runs. Query params: `?service_name=...&status=...&limit=20&offset=0`

Response: `200 OK`
```json
{
    "runs": [...],
    "total": 42,
    "limit": 20,
    "offset": 0
}
```

#### GET /api/benchmarks/{run_id}
Get full details of a specific run including params, results, metadata, raw output.

Response: `200 OK` (full run object) or `404`

#### DELETE /api/benchmarks/{run_id}
Cancel running benchmark or delete completed result.

- If running: kill process, set status to "cancelled"
- If pending: set status to "cancelled"
- If completed/failed/cancelled: delete the record

Response: `200 OK` with `{"success": true, "message": "..."}` or `404`

#### PUT /api/benchmarks/{run_id}/apply
Apply a completed benchmark run's model configuration back to the service.

Uses a **denylist** of benchmark-only flags. Everything else is treated as a model parameter and applied to the service config.

```python
# Denylist: benchmark-only flags that must never be applied to service config
BENCHMARK_ONLY_FLAGS = {"-p", "-n", "-r", "-o", "-m"}
```

- Iterates `params_json` from the benchmark run
- Skips any flag in `BENCHMARK_ONLY_FLAGS`
- Applies all remaining flags to the service config
- Returns the list of params that were applied and those that were skipped

Response: `200 OK`
```json
{
    "success": true,
    "message": "Configuration applied to llamacpp-qwen3-30b-q8. Restart the service for changes to take effect.",
    "applied_params": {"-ngl": "99", "-b": "2048", "-fa": ""},
    "skipped_flags": ["-p", "-n", "-r"]
}
```

Errors: 400 (run not completed, or no applicable params found), 404 (run not found)

### Benchmark Execution

- **Mechanism**: `docker run --rm --gpus all -v <model_volume> llm-dock-llamacpp /llama.cpp/build/bin/llama-bench -m <model_path> -o json [params]`
- **Volume and GPU config**: Extracted from the service's docker-compose definition via ComposeManager
- **Background execution**: `threading.Thread` with `daemon=True`. No external dependencies (no celery/redis).
- **Process management**: `subprocess.Popen` (not `.run()`) to allow cancellation via `proc.kill()`.
- **JSON output**: Use `-o json` flag for machine-parseable results.
- **Timeout**: 10-minute hard cap via `proc.communicate(timeout=600)`.
- **One per service**: Reject concurrent benchmarks on the same service (409).
- **Thread safety**: `threading.Lock` around the active processes dict.
- **Model path**: Resolved from `services.json` via `ComposeManager.get_service_from_db()`. Never accept user-supplied paths.

### Security

1. No user-supplied file paths (model path from services.json only)
2. No shell injection: `subprocess.Popen` with list-form args, never `shell=True`
3. `@require_auth` on all endpoints
4. Service name validated against services.json
5. Flag names validated: must start with `-`, alphanumeric + hyphens only. Reserved flags (`-m`, `-o`) rejected.
6. 10-minute timeout prevents resource exhaustion
7. Only `/llama.cpp/build/bin/llama-bench` is executed -- no arbitrary commands

---

## UI/UX Specification

### Entry Point: Service Card Button

Add a gauge/tachometer icon button to llama.cpp service cards, in the existing button row alongside YAML Preview, Edit, and Delete.

- Icon: `fa-solid fa-gauge-high` (FontAwesome)
- Only visible on llama.cpp services (check `service.name.startsWith('llamacpp-')`)
- Always enabled (benchmarking does not require the service to be running)
- Clicking navigates to `benchmark.html?service=<service_name>`

### Benchmark Page Layout

Separate HTML file (`benchmark.html`) with the same dark theme, TailwindCSS, FontAwesome.

Full-width stacked layout (not side-by-side):

```
┌──────────────────────────────────────────────────────────────┐
│  ← Back to Dashboard                                         │
│                                                              │
│  Benchmark: llamacpp-qwen3-30b-q8                            │
│  Model: /models/Qwen3-30B-A3B-Q8_0.gguf                     │
│  Status: ● Running  (or ○ Stopped)                           │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ── Parameters ──────────────────────────────────            │
│  Flag          Value                                         │
│  [ -p       ]  [ 512       ]                          [x]   │
│  [ -n       ]  [ 128       ]                          [x]   │
│  [ -r       ]  [ 5         ]                          [x]   │
│  [ -ngl     ]  [ 99        ]                          [x]   │
│  [ -b       ]  [ 2048      ]                          [x]   │
│  [ -fa      ]  [           ]  (empty = boolean flag)  [x]   │
│                                     [ + Add Parameter ]      │
│                                                              │
│  ── Command Preview ───────────────────────────────          │
│  > llama-bench -m /models/Qwen3... -p 512 -n 128 ...        │
│                                                              │
│  [ ▶ Run Benchmark ]              [ Reset to Service Defaults]│
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  ── Live Output ───────────────────────────────────          │
│  (terminal-style, monospace, dark bg, auto-scrolling)        │
│  Poll every 2 seconds while running                          │
│  Status badge: idle / running / completed / failed           │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  ── History ───────────────────────────────────────          │
│  Date       | PP t/s | TG t/s | pp | tg | ngl | Status      │
│  Feb 13 ... | 1240.5 |  85.3  |512 |128 | 99  |   ✓        │
│  Feb 12 ... |  980.2 |  72.1  |512 |128 | 80  |   ✓        │
│                          [Re-run] [Apply to Service] [Delete] │
└──────────────────────────────────────────────────────────────┘
```

**Parameter loading on page load:**
1. Fetch most recent benchmark run for this service
2. If found: pre-fill form with that run's params
3. If not found: fetch service config and pre-fill from there

**Interaction details:**
- Changing any parameter updates the command preview live
- "Run Benchmark" disables while a benchmark is running, shows spinner
- "Re-run" on a history row loads that row's params into the form (scrolls to top)
- "Apply to Service" shows a confirmation dialog listing the params that will change, then calls PUT /api/benchmarks/{id}/apply
- "Delete" shows a brief confirmation, then removes the row

### Styling

- Follow existing patterns: `bg-gray-900/800/700`, TailwindCSS via CDN, FontAwesome icons
- Use `fetchAPI()` for authenticated API calls (copy from app.js or share via common module)
- Toast notifications for success/error feedback
- Responsive: stack columns on narrow screens

---

## Testing Strategy

### Unit Tests (no Docker, no Flask, no network)

- **test_bench_db.py**: SQLite CRUD operations using in-memory database
  - Create run, get run, list runs, delete run
  - Parameter loading priority (most recent run vs defaults)
  - Status transitions (pending → running → completed/failed/cancelled)
  - Stale recovery (running → failed on startup)
- **test_bench_validators.py**: Parameter validation
  - Valid flag names accepted (e.g. `-p`, `-ngl`, `--threads`)
  - Invalid flag names rejected (empty, no dash prefix, special characters)
  - Reserved flags (`-m`, `-o`) rejected
  - Values validated as strings (no injection via special characters)
- **test_bench_executor.py**: Command building and execution logic with mocked `subprocess.Popen`
  - Correct docker run command constructed from params
  - Volume mounts extracted correctly from service config
  - Timeout handling
  - Cancellation flow

### Integration Tests (Flask test client, mocked Docker)

- **test_bench_routes.py**: API endpoint behavior
  - Auth required on all endpoints
  - POST creates run and returns 202
  - GET lists/retrieves runs correctly
  - DELETE cancels or removes runs
  - PUT apply copies only non-denylisted flags to service
  - Denylisted flags (`-p`, `-n`, `-r`, `-o`, `-m`) never applied
  - 400 for invalid params or non-llamacpp services
  - 409 for concurrent benchmark on same service
  - 404 for nonexistent runs

### How to run tests:
```bash
cd dashboard
python -m pytest tests/ -v
```

---

## Error Handling Matrix

| Scenario | Response | User Impact |
|----------|----------|-------------|
| Service is vLLM | 400 | Benchmark button not shown for vLLM |
| Concurrent benchmark on same service | 409 | "Benchmark already running" message |
| Benchmark timeout (>10 min) | Process killed, status=failed | Error shown with timeout message |
| Temporary container fails to start | status=failed | Error shown with docker stderr |
| llama-bench not found in image | docker run fails, status=failed | Error shown; user told to rebuild image |
| Invalid JSON from llama-bench | JSONDecodeError, raw stdout stored | Error shown; raw output available |
| Flask restarts during benchmark | Stale "running" rows set to "failed" on startup | User sees failed status |
| Service deleted after benchmark stored | Benchmark history remains (orphaned but viewable) | No impact on stored data |
| Model file not found (moved/deleted) | llama-bench exits non-zero, status=failed | Error shown with message |
| GPU not available | Container fails to start or OOM | Error shown with docker stderr |

---

## Success Metrics

1. Benchmark launchable from service card in 2 clicks (card button → run benchmark)
2. Results persisted across dashboard restarts
3. Benchmark execution does not block the Flask request/response cycle
4. All key llama-bench metrics (pp t/s, tg t/s, stddev) correctly parsed and stored
5. Parameter persistence: returning to benchmark page shows last run's params
6. Apply-to-service correctly updates service config
7. Clean code: separate package, Blueprint registration, layered architecture, tests passing