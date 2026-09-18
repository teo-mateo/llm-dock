# Changelog

## 2026-09-18
- **Request inspector** - Per-service request capture, end to end. Toggling *Request inspection* on a service relocates its container to loopback and puts a capturing proxy on the service's public port — clients keep the same URL — recording every inference request with assembled streaming output, redacting credentials in storage only (the container still authenticates), on an allowlist of inference paths so metrics/health polling never crowds the store. Captures live in `dashboard/inspector.db` (2000 rows, 1 MB bodies, both flagged), are browsable on the new `/inspector` page (conversation as sent, tool definitions, raw request, response, metadata) with per-capture and bulk delete, and the service detail page gained the toggle card with its recreate confirmation

## 2026-09-16
- **Service image display** - The service-details page shows which Docker image a service runs with; clicking the image cell opens a popover with its provenance (built locally vs pulled, created date, build date/commit, registry, upstream source and size)

## 2026-09-15
- **NInfer metrics scrape fix** - The `/metrics` route no longer reads `MemorySummary` per scrape: that call takes the engine's `execution_mutex_`, which the worker holds across every execution unit, so a scrape issued during generation returned only when the request ended (measured: 24.1 s for one scrape inside a 3000-token generation) and the panel went dark for the whole request. The KV capacity it needed is fixed at load, so `attach()` now captures it and `render_metrics_snapshot` takes that integer; `/metrics` reads only the published `RuntimeStats` snapshot, which the worker publishes per execution unit under `stats_mutex_`. The dashboard now returns `scrape_error` instead of collapsing a timed-out scrape into an empty map, and logs the first failure of a streak at warning. The metrics hook holds one scrape in flight instead of stacking a request per 200 ms tick, and skips the datapoint on a failed scrape so the counter baseline survives the gap — that stacking and baseline loss were what turned a stalled endpoint into flat gaps and 10-100x spikes
- **Ghost chats** - New ephemeral chat mode that leaves no trace: the reply streams from a stateless request with zero database writes, and the v2 UI's Ghost Chat page keeps every message in browser memory only — a refresh erases the thread by design
- **NInfer metrics** - Live Metrics panel for NInfer services: running/waiting requests, token rates, and KV/prefix-cache gauges, served by a `GET /metrics` route added at image build time. Spec-acceptance and preemption cells stay "—" (the engine keeps no service-level aggregate for either)

## 2026-09-13
- **NInfer engine** - New sixth inference engine for `.ninfer` Qwen artifacts, built from source (`build-ninfer.sh`) with a CUDA 12.9 port patch
- **NInfer services** - `template_type: "ninfer"` services on port 8080 with API-key auth; the HF cache is mounted read-only

## 2026-02-15
- **Service rename** - Rename services directly from the dashboard with a modal UI
- **Chat templates** - Added chat-templates directory with StepFun Step-3.5 Flash template

## 2026-02-14
- **Unified parameter editor** - Free-form flag+value rows (benchmark-style) replace dropdown-based parameter selection for llama.cpp services, with arbitrary CLI flags beyond the predefined set
- **Inline parameter reference** - Searchable side panel with tooltips for all llama-server flags
- **Benchmarking system** - Full `llama-bench` integration: run benchmarks from the dashboard, view results history, compare runs
- **Global API key** - Shared API key support across services
- **Build metadata** - Docker images track build date and commit, displayed in the dashboard header
- **vLLM improvements** - Updated to v0.12.0 with a newer base image and CUDA architecture updates
- **Container diagnostics** - Exit codes shown for crashed containers
- **Systemd integration** - Installer script and `start.sh` for quick startup

## 2025-11-27
- **Open WebUI integration** - Register/unregister services with Open WebUI, restart button on the Open WebUI card
- **Auto port assignment** - Next available port (3301-3399) auto-selected on service creation
- **Service deletion** - Now properly stops and removes containers before deleting
- **Image rename** - llama.cpp image renamed from `my-llamacpp` to `llm-dock-llamacpp`
- **Clean installs** - `docker-compose.yml` generated from template, not tracked in git
