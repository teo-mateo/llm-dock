# Changelog

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
