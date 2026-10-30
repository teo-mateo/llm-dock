# Project Maya as an llm-dock engine

Status: implemented as `template_type: "maya"` (eighth engine). Image build and
first container start not yet run — the GPU was busy with the native install.
Upstream: `mw00/project-maya`, v1.1.28, checked out at `/github/mw00/project-maya`
(branch `ds4-pics-slots`, `ca25174`, 39 commits ahead of `origin/main`).

## What Maya is

Expert-tiering engines for two large MoE models — DeepSeek-V4.1-Flash
(`build/maya-ds4`) and GLM-5.3-Flash (`build/maya`) — that keep experts across
VRAM → pinned RAM → NVMe. `serve/server.py` (stdlib Python) spawns the engine
with `--serve` on stdin/stdout pipes and serves OpenAI (`/v1/chat/completions`,
`/v1/responses`, `/v1/models`), Anthropic (`/v1/messages`), its web UI on `/`,
`/health`, JSON `/metrics` and Prometheus on `/metrics/prometheus`. `maya.py` is
the interactive installer that writes the server's run config; upstream has no
Docker support.

## The service it was built for

Native reference: `run-maya-deepseek-2.25-dspark.sh` →
`maya-deepseek-2.25-dspark.json` (ISTA-DASLab GSQ-RCO IQ2_XS 2.25 bpw, 512K
context, pictures, DSpark drafter; calibrated 74.8 tok/s with DSpark vs 35.4
without). The machine-local service `maya-deepseek-v41-flash-dspark` (port 3304)
carries the same settings:

| Native config | llm-dock param |
|---|---|
| `--pack …/pack-vision-dspark` | `model_path` |
| `--max-context 524288 --tp 1 --threads on --mmap-experts on --dspark on --multi 2 --reserve-mib 1536` | the same flags |
| `sampling {temperature 1.0, top_p 1.0}` | `--sampling-temperature 1.0`, `--sampling-top-p 1.0` |
| `reasoning_effort high`, `engine_ready_s 3600` | `--reasoning-effort high`, `--engine-ready-s 3600` |
| `env MAYA_DS4_SLOT_KEEP=1, MAYA_DS4_SLOT_GB=8` | `env:MAYA_DS4_SLOT_KEEP`, `env:MAYA_DS4_SLOT_GB` |
| `model_name deepseek-v4.1-flash` | the service alias (display-only in Maya) |
| `systemd-run --scope` (oomd kills only Maya) | the container's own cgroup scope |

## Decisions

1. **Container, not a host process.** Compose, start/stop, logs, the inspector
   and the model proxy all assume one. Shelling out to `maya.py` was rejected:
   it is interactive, mutates its checkout and self-updates.
2. **Skip `maya.py` at runtime.** `maya/launcher.py` writes the run config
   `maya.py:write_config_ds4` would write (`/maya-state/maya.json`) and execs
   `server.py --engine strata --config …`. Engine family comes from the pack:
   `ds4.txt` → `maya-ds4 --pack`, `index.txt` → `maya --glm-pack`. `--parent-pipe`
   is not passed (compose holds no stdin); `server.py` handles SIGTERM itself and
   sends the engine QUIT, so `stop_grace_period` is 150 s (`STOP_WAIT_S`).
3. **Build from the local checkout at a commit.** The running engine comes from
   local, unpushed commits, so `./build-maya.sh` extracts `git archive <commit>`
   into `~/.cache/llm-dock-maya-build/<sha>/` and passes it as a BuildKit named
   context. Configure line is `compile_engine()`'s (Release, `STRATA_ENABLE_CUDA`,
   `STRATA_NATIVE_EXPERTS`, sm_120) with the arch as a build arg, so no GPU is
   needed. CUDA 12.9 (driver 575). Runtime image carries cudart/cublas from
   `nvidia/cuda:12.9.1-runtime` and the serve-time Python packages at the
   native venv's versions.
4. **Mount packs at their host paths.** A pack records the absolute HF snapshot
   (`ds4.txt` `model_dir`) and reaches the engram GGUF, `dspark/` and `vision/`
   through relative links between the HF cache and `~/.cache/maya`. Mounting
   both at identical paths runs the native pack unchanged — no re-pack, and the
   native install keeps working on the same files. A separate `/maya-models`
   tree with container-path symlinks (the first draft) would have broken it.
5. **Run as the host user.** The engine writes `slots/`, `expert-profile.bin`
   and `lane-times.txt` into the pack; root-owned files there would lock the
   native install out. State lives in `~/.cache/maya/llm-dock/<service>` and is
   created at render time — `~/.cache/llm-dock` is already root-owned from a
   Docker-created sglang bind source.
6. **Params.** Launcher knobs have names the engine cannot collide with (the
   engine has its own `--temperature`); every other `--flag` goes to the engine
   verbatim, `env:` reaches it through the inherited container env.
7. **Logs.** Without a config `log`, `server.py` sends engine stderr to
   `/dev/null`; the launcher logs to `/maya-state/engine.log` and tails it to
   stdout.

## Integrations

- **Open WebUI / chat / model proxy / inspector:** OpenAI-compatible on
  `:8080/v1`. Chat sends no `model`. The inspector does not capture
  `/v1/messages` (not in `CAPTURED_PATHS`).
- **Reasoning levels:** mapped to `reasoning_effort`, `off` → `none`. Maya reads
  none/low/high/max and silently maps `medium` → high, `xhigh` → max. No ladder
  declared on the service yet: probe `off,low,high,max` first.
- **Not done:** metrics (the scraper reads `/metrics`, Maya's Prometheus is
  `/metrics/prometheus` with `llamacpp:*` + `maya:*` names), benchmarking, a
  recorded flag surface, sampling-param mapping, the legacy vanilla-JS UI.

## First start (when the GPU is free)

1. `./build-maya.sh` (both engines; `MAYA_TARGETS=maya-ds4` for DeepSeek only).
   It compiles with nproc/2 jobs, so do it while nothing CPU-heavy runs — the
   native Maya decode uses the CPU lane.
2. Stop the native Maya (one GPU, and both bind host RAM).
3. Check free RAM (`free -g`): the engine sizes its pinned tier from free RAM at
   start; large tmpfs/shmem shrinks it.
4. `docker compose up -d maya-deepseek-v41-flash-dspark`, then
   `docker logs -f` until the `ready: http://…/v1` line.
5. Verify: `/health`, `/v1/models`, one chat completion, a picture, a restart
   that resumes a kept conversation, and decode speed against the native 74.8
   tok/s.

## Risks

- **RAM pinning starves the host.** All but ~6 GB pinned while it runs
  (`MAYA_GLM_RAM_HEADROOM_GB` / `STRATA_GLM_RAM_HEADROOM_GB` raise the headroom
  for GLM).
- **Shared pack, two runners.** Native and container write the same `slots/`
  and profile; never run both at once.
- **Fast-moving upstream:** pinned by commit; bump deliberately and re-check the
  configure line against `maya.py:compile_engine()`.
- **Pack invalidation:** a re-downloaded shard means re-packing (natively, or a
  `docker run` of `tools/` in the image).
