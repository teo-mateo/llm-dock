# Changelog

## 2026-09-16
- **Service image display** - The service-details page shows which Docker image a service runs with; clicking the image cell opens a popover with its provenance (built locally vs pulled, created date, build date/commit, registry, upstream source and size)

## 2026-09-15
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
