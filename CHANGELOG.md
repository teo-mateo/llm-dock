# Changelog

## 2026-09-15
- **Ghost chat default model** - The ghost composer no longer starts with a blank model slot: it preselects the same default as the empty-state composer (first running local service, else first curated OpenRouter model), so the input is enabled on load instead of waiting for a redundant re-selection — the endpoint 400s a turn without a `service_name`
- **Ghost chats** - New ephemeral chat mode that leaves no trace: `POST /api/chat/ghost` streams a reply from a stateless request (full history in the body, MCP tools supported) with zero DB writes and `Cache-Control: no-store` on the SSE response; the v2 UI adds a Ghost Chat page (`/chat/ghost`, sidebar button, entered with `replace: true`) whose `useGhostChat` hook keeps every message in React state only — no localStorage, no conversation row, no history entry. A refresh or tab close erases the thread by design
- **NInfer metrics** - Live Metrics panel enabled for `template_type: "ninfer"` services: the image now ships an authed `GET /metrics` route (second build-time patch, `ninfer/ninfer-metrics.patch`, 12 Prometheus families from the engine's runtime stats), the dashboard whitelists them via `NINFER_CURATED_METRICS`, and the v2 panel renders running/waiting requests, token rates, the Active KV and prefix-hit gauges. Spec-acceptance and preemption cells stay "—" (the engine keeps no service-level aggregate for either); `/slots` stays llama.cpp-only

## 2026-09-13
- **NInfer engine** - New sixth inference engine for `.ninfer` Qwen artifacts (`llm-dock-ninfer` image, `ninfer.j2` template, `NINFER_FLAGS` metadata), built from source by `build-ninfer.sh` with the CUDA 12.9 port patch
- **NInfer services** - `template_type: "ninfer"` services on port 8080 with `--api-key` auth, artifact as a positional argument, and the HF cache mounted read-only at `/hf-cache`

## 2026-02-15
- **Service rename** - Rename services directly from the dashboard with a modal UI
- **Rename API endpoint** - New `/api/v2/services/<name>/rename` endpoint
- **Chat templates** - Added chat-templates directory with StepFun Step-3.5 Flash template

## 2026-02-14
- **Unified parameter editor** - Replaced dropdown-based parameter selection with free-form flag+value rows (benchmark-style) for llama.cpp services
- **Inline parameter reference** - Searchable side panel with categories, color-coded badges, and rich HTML tooltips for all llama-server flags
- **Benchmarking system** - Full `llama-bench` integration: run benchmarks from the dashboard, view results history, compare runs
- **Benchmark UI** - Collapsible live output, parameter reference with tooltips, auto-added flags (-m, -o), safe defaults for new models
- **Global API key** - Shared API key support across services
- **Build metadata** - Docker images now track build date and commit; displayed in dashboard header
- **vLLM improvements** - Updated to v0.12.0, newer base image, CUDA architecture updates
- **Custom parameters** - Support for arbitrary CLI flags beyond the predefined set
- **Container diagnostics** - Exit codes shown for crashed containers
- **Systemd integration** - Installer script and `start.sh` for quick startup

## 2025-11-27
- **Open WebUI integration** - Register/unregister services with Open WebUI, restart button on Open WebUI card
- **Auto port assignment** - Next available port (3301-3399) auto-selected on service creation
- **Fixed path mapping** - `~/.cache/models` now correctly maps to `/local-models` in containers
- **Service deletion** - Now properly stops and removes containers before deleting
- **GPU info in edit modal** - GPU stats display when editing existing services
- **Simplified UI** - Parameters section always visible (removed collapsible)
- **Image rename** - llama.cpp image renamed from `my-llamacpp` to `llm-dock-llamacpp`
- **Clean installs** - `docker-compose.yml` now generated from template, not tracked in git
