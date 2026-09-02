# Adding exllamav3 as a model runner — analysis

Status: **Phase 1 implemented** (image + template + registry + badges + one live service).
Phase 0's end-to-end run is still pending — it needs ~16 GB of VRAM, currently held
by `vllm-qwen3-8-flash-next-mixed-nvfp4-fp8`. See §7 for what shipped and what broke.
Original analysis follows.

## 1. The thing we're actually integrating is TabbyAPI, not exllamav3

ExLlamaV3 is an inference **library**. It ships `convert.py`, `examples/chat.py`, a HF
Transformers plugin, and eval scripts — **no HTTP server** (grep for `fastapi|uvicorn|/v1/`
in the repo returns nothing relevant). Its README states plainly:

> The official and recommended backend server for ExLlamaV3 is TabbyAPI.

So "add exllamav3 to llm-dock" = "add **TabbyAPI** (`ghcr.io/theroyallab/tabbyapi`) as a
fifth runner image, with exllamav3 as its backend". Three options:

| Option | What | Verdict |
|---|---|---|
| **A** | Run upstream `ghcr.io/theroyallab/tabbyapi` pinned **by digest** | ✅ Recommended MVP. Verified publicly pullable; `latest` = `sha256:3a1418a7a2828fc405d592b54107cc3b9f6fef78235022494eaa7e9114809f67` (amd64). Tags: `latest` (cu128), `cu13`, `latest-extras`. |
| **B** | Build `llm-dock-tabbyapi` from TabbyAPI's own `docker/Dockerfile`, with the exllamav3 wheel overridden from a local checkout | Do later, when we need a custom/dev exl3 build. Mirrors the `llm-dock-vllm` pattern (`FROM` upstream + labels). |
| **C** | Write our own thin FastAPI server on the exllamav3 API | ❌ Rejected. Would mean reimplementing OpenAI schema, streaming, continuous batching, tool-call parsing, Jinja chat templates, multimodal preproc. That's TabbyAPI. |

License note: TabbyAPI is **AGPLv3** (llm-dock is MIT). Consuming it as a separate container
image is fine; do not vendor its source into this repo.

**Version coupling is already resolved upstream:** TabbyAPI's `pyproject.toml` pins
`exllamav3 @ .../v1.4.5/...+cu128.torch2.9.0` — the same version as the local checkout. So
Option A gets exl3 1.4.5 with torch 2.9 / cu128.

## 2. Three structural mismatches with llm-dock's current runner model

### 2.1 Config is a YAML file, CLI flags are *overrides* — and they behave differently

TabbyAPI reads `config.yml`, and its argparse surface is **generated from the pydantic config
model** (`common/args.py`): every nested field becomes `--<field-with-dashes>` and **takes a
value, including booleans**. There are no `store_true` flags.

```
--host 0.0.0.0  --port 8000  --model-dir /models  --model-name Qwen3-32B-4.0bpw
--max-seq-len 32768  --cache-mode 8,8  --chunk-size 2048  --vision True
--disable-auth False  --gpu-split 90  --cache-size 32768  --max-batch-size 4
```

Consequence for llm-dock: `render_cli_flag()` (`flag_metadata.py:1362`) renders an empty
string as a **bare flag**. `--vision` with no value is a hard argparse error for TabbyAPI. So
every TabbyAPI bool param must be stored with an explicit `True`/`False` value (pydantic
coerces the strings `"True"`/`"False"` correctly). The flag metadata entry for `tabbyapi`
needs `type: "bool"` to *always* render a value, or the UI must forbid empty values. This is
the one real friction point with the existing `params` dict convention.

Also note the dash convention (`--max-seq-len`, not `--max_seq_len`) and that
`--gpu-split` is `nargs="+"` (space-separated list).

### 2.2 Model addressing is `model_dir` + folder name, not a file path

`model.model_name` is "Folder name of a model to load" inside `model.model_dir`. Not a path
to a file (llama.cpp/ds4 `model_path`) and not an HF repo id (vLLM `model_name`). And the HF
cache layout (`hub/models--org--name/snapshots/<rev>/`) is not a flat model dir, so mounting
`~/.cache/huggingface` as `model_dir` does **not** work.

Practical shape:

- New host dir `~/.cache/exl3/<folder>/`, mounted read-only at `/app/models`.
- Populate with **symlinks** into HF snapshot dirs:
  `ln -s ~/.cache/huggingface/hub/models--X--Y/snapshots/<rev> ~/.cache/exl3/<folder>`
  (EXL3 repos on HF usually publish one branch per bitrate, e.g. `--revision 4.0bpw`, and each
  revision is its own snapshot dir — so the symlink *is* the bitrate selector.)
- A ~30-line helper (`scripts/exl3-link.py`) to create/refresh those links is worth it;
  `hf download <repo> --revision <bpw>` + manual symlink is the no-code fallback.
- `MANDATORY_FIELDS["tabbyapi"] = ["port", "model_path", "alias", "api_key"]` reuses
  `model_path` = container path to the model **directory** (`/app/models/<folder>`), then the
  template splits it into `--model-dir /app/models --model-name <basename>`. That keeps the
  existing model-picker/`compute_model_size()`/`resolve_host_path()` machinery mostly intact.

### 2.3 Per-service API keys need a mounted `api_tokens.yml`

TabbyAPI authenticates with `Authorization: Bearer <key>` against `api_tokens.yml`
(`{api_key: [..], admin_key: ..}`). If the file is absent it **generates its own keys** and
writes them to `/app/api_tokens.yml` + logs them — which silently diverges from the
`api_key` llm-dock stores in `services.json`, and chat would 401.

Two coherent choices (mirror existing precedent):
- **Per-service key file**: llm-dock writes `dashboard/tabby-keys/<service>.yml` with the
  service's `api_key` as both `api_key` and `admin_key`, bind-mounted to `/app/api_tokens.yml`.
  TabbyAPI polls that file (mtime, 2 s) and hot-reloads, so rotation is picked up without a
  restart. Needs the host dir in `.gitignore` (contains secrets).
- **`--disable-auth True`**: same posture as ds4 (no in-container auth). Simplest; the port is
  still published on the host, so it's no better or worse than ds4 today.

Recommendation: key file. It preserves the per-service `api_key` invariant that
`chat/llm_proxy.py` and Open WebUI registration depend on. Rotation logic
(`key_rotation.rotate_keys_in_db`) then only needs to also rewrite that file.

## 3. Runtime facts for this host

| Item | Value |
|---|---|
| Image | `ghcr.io/theroyallab/tabbyapi:latest` (digest-pinned) — cu128/torch2.9/python3.13 base |
| GPU | RTX PRO 6000 Blackwell (sm_120), 96 GB, driver 575.57.08 → CUDA 12.8 runtime OK |
| Internal port | Container listens on **8000** (`--port 8000`), mapped `"{{ port }}:8000"`. Keeps `docker_utils.py:149` (`internal_port = 8080 if llamacpp-ish else 8000`) and `openwebui_integration.py` working **unchanged** |
| Host port | 3328 (next free; 3301–3327, 3329–3330, 3370, 3380 are taken) |
| Entrypoint | image `ENTRYPOINT ["python3"]`, `CMD ["main.py","--host","0.0.0.0"]` → llm-dock overrides `command:` with `main.py --host 0.0.0.0 --port 8000 …` |
| Required extras from upstream compose | `shm_size: 8g`, `ulimits: {memlock: -1, nofile: 1048576}`, plus `ipc: host` like the other templates |
| Health | `GET /health`, **unauthenticated**, 503 + `issues[]` until a model is loaded. Currently unused by llm-dock (status comes from Docker only), but it's the right probe for "running but still loading weights" |
| Metrics | no Prometheus endpoint, no `/slots` → `MetricsPanel` must stay gated off (`ServiceDetailsPage.jsx:184` already gates on engine) |
| Benchmarks | `benchmarking/executor.py` is hard-wired to `llama-bench` in the llamacpp image → exclude exl3 from the benchmark UI; no exl3 equivalent exists in-repo (`qbench.py` is a dev micro-benchmarker) |

VRAM: there is no `--gpu-memory-utilization` equivalent. Control surface is
`--gpu-split <GB>`, `--autosplit-reserve`, `--cache-size`, `--cache-mode k,v`,
`--max-batch-size`, `--chunk-size`, `--output-chunking True`. Since all llm-dock services use
`devices: count: all` and share one GPU, an explicit `--gpu-split` (e.g. `60`) is the honest
analogue of today's `--gpu-memory-utilization 0.55` and should be in the default params.

## 4. Blocker: there is nothing to run

No EXL3 model exists on this host (`~/.cache/huggingface/hub` has GGUF + safetensors only),
and EXL3 is a **weight format, not a GGUF alias** — QTIP/trellis-quantized `.safetensors` with
`quant: {method: exl3}` in `config.json`. Two supply paths:

- **Download pre-quantized** from HF (`turboderp/*-exl3` collection and community repos),
  one branch per bitrate. Cheap, and the only thing to do for a spike.
- **Convert** from HF FP16 with `python convert.py -i <in> -o <out> -w <work> -b <bpw>`: needs
  minutes→hours of GPU and a working dir as large as the output model. Treat as a **separate
  later feature** (`convert` job container), not part of runner plumbing.

Corollary: `model_discovery.py` needs an EXL3 detector (dir containing `config.json` whose
`quant.method == "exl3"`, plus sharded `*.safetensors`) and `_CONTAINER_PATH_MAP`
(`model_discovery.py:13-18`) needs the new mount prefix. Until then, discovery keeps offering
only GGUF/safetensors and the service has to be authored by hand — which is exactly how
`ik_llamacpp` shipped.

## 5. Touchpoint checklist

`ik_llamacpp` is the precedent for the minimal viable surface — it's 9 backend/frontend
files + template + Dockerfile, **with no create-service UI**. That's the floor for exl3 too.

**Backend (must)**
- `dashboard/templates/tabbyapi.j2` — new. Modeled on `ds4.j2`; sets `--host/--port
  8000/--model-dir/--model-name`, `ipc: host`, `shm_size: 8g`, ulimits, `/app/models` `:ro`
  mount, `/app/api_tokens.yml` `:ro` mount, `HF_HUB_OFFLINE=1`, `rendered_flags` loop.
- `dashboard/compose_manager.py:548-561` — add `elif template_type == "tabbyapi":` context
  branch (`model_path` → dir + name split, `api_key`, `alias`).
- `dashboard/flag_metadata.py` — `MANDATORY_FIELDS["tabbyapi"]` (~line 17),
  `TABBYAPI_FLAGS` + `TABBYAPI_VALIDATION` (new block next to `DS4_FLAGS` at 1191),
  `get_flag_metadata()` 1317, `get_validation_rules()` 1331.
- `dashboard/routes/services.py:245` — engine allowlist; `:533` — flag-metadata allowlist.
- `dashboard/routes/system.py:100-102` — image metadata entry. Note
  `get_image_build_metadata()` reads `org.llm-dock.*` labels, which the upstream image lacks →
  add the entry only if we go Option B, otherwise report `{exists: <pull status>, pinned_digest}`.
- `dashboard/docker_utils.py:149` — no change if container listens on 8000; `_service_kind()`
  needs exl3 embedding models excluded (exl3/TabbyAPI embeddings are a different stack).
- `dashboard/service_templates.py:271` — engine→prefix handling.

**Frontend v2 (must, for it to render)**
- `components/ServicesTable.jsx:11,58` — name→engine + badge class (`exl3-` prefix).
- `components/ServiceDetailsHeader.jsx:68-70` — badge entry.
- `components/ServiceConfigPanel.jsx:338-345` — `renderCommandPreview` branch
  (`python main.py --host 0.0.0.0 --port 8000 --model-dir /app/models --model-name …`).
- `hooks/useRunningServices.js:21` — name-prefix filter.
- `index.css:105-108,168-171` — `--color-badge-exl3-{bg,fg}` in both light and dark blocks.
- `components/ServiceDetailsPage.jsx:184` — deliberately **not** added to the metrics gate.

**Legacy UI + service creation (should, Phase 2)**
- `static/index.html:173-186` (engine radio), `static/js/service-modal/create-service.js:85,
  260,510,571,630,665`, `param-rows.js:94`, `param-reference.js:16,52-54`,
  `static/js/services.js:68-70` (internal port display).

**Ops / repo hygiene (must)**
- `build-tabbyapi.sh` (Option B only) **or** an image-pull + digest-pin note in the docs, plus a
  `TABBYAPI_IMAGE` constant somewhere central (today image names are hardcoded in templates).
- `CLAUDE.md`/`AGENTS.md`: Supported Engines, API routes table, port conventions, a
  "dash-flags + explicit bool values" gotcha, and the model-dir/symlink gotcha.
- `.pi/skills/check-upstream/SKILL.md`: new runner row. TabbyAPI has **no git tags and no
  GitHub releases** (rolling release) → pinning is by image digest; "how far behind" is
  answered by comparing the pinned digest's config blob against upstream `main`.
- Tests: `dashboard/tests/test_compose_manager.py` (renders `tabbyapi.j2`) and a
  validation/mandatory-fields case; both follow the existing ds4 patterns.

## 6. Phase plan

**Phase 0 — spike, no llm-dock code (~1–2 h, do first).** It's the only step that can kill
the project, and it's cheap:
1. `docker pull ghcr.io/theroyallab/tabbyapi@sha256:3a1418…`
2. `hf download <some small exl3 repo> --revision 4.0bpw`, symlink into a flat dir.
3. `docker run --rm --gpus all -p 3328:8000 -v ~/.cache/exl3:/app/models:ro --shm-size 8g <image> python3 main.py --host 0.0.0.0 --port 8000 --model-dir /app/models --model-name <folder> --gpu-split 60`
4. Confirm: sm_120 kernels actually load (this is the #1 unknown — cu128 wheels should cover
   Blackwell, but exllamav3's extension is compiled per-arch and we have no CI evidence here),
   `/health` goes healthy, `/v1/chat/completions` streams, tool calls parse with the model's
   own Jinja template, multimodal works if the repo carries a vision tower.

**Phase 1 — MVP plumbing.** Template + compose_manager + flag metadata + the two route
allowlists + badges + service-name prefix + tests. Service authored by hand in
`services.json` and `mgr.rebuild_compose_file()`, exactly like the documented vLLM CLI
workflow. Acceptance: start/stop/logs/rename from the dashboard, chat through
`chat/llm_proxy.py` with tools + streaming, register in Open WebUI.

**Phase 2 — discoverability.** EXL3 discovery + path map + symlink helper, legacy create-UI,
param reference, key-file rotation integration, docs section.

**Phase 3 — optional.** Conversion job container (`convert.py`) as its own feature; `/health`
readiness probe in the dashboard; single-instance dynamic model switching via
`inline_model_loading: true` (one shared TabbyAPI container serving many EXL3 checkpoints —
a genuinely different topology from llm-dock's one-container-per-model, and the only way to
make this format pleasant if you rotate quants a lot).

## 7. What actually shipped (Phase 1)

Image: `tabbyapi/Dockerfile` + `build-tabbyapi.sh`, built as `llm-dock-tabbyapi`
(12.5 GB) — base `@sha256:3a1418a7…`, `exllamav3 1.4.5+cu128.torch2.9.0`,
`torch 2.9.0+cu128`. Blackwell check: capability `(12, 0)`, torch arch list
includes `sm_120`, `exllamav3_ext` loads. Only the actual kernel run against a
loaded model is left unverified.

Wiring: `templates/tabbyapi.j2`, `compose_manager._render_service` branch,
`tabby_keys.py` (new), `TABBYAPI_FLAGS`/`TABBYAPI_VALIDATION` + registration in
`flag_metadata.py`, both allowlists in `routes/services.py`, image metadata in
`routes/system.py`, `/exl3/` in `model_discovery._CONTAINER_PATH_MAP`, and the
v2 UI set (`ServicesTable`, `ServiceDetailsHeader`, `useRunningServices`,
`ServiceConfigPanel` preview, `--color-badge-exl3-*` in both themes).

Service: `exl3-laguna-xs-3bpw`, port 3328, `model_path`
`/hf-cache/hub/models--turboderp--Laguna-XS-2.1-exl3/snapshots/b966d18…`,
params `--max-seq-len 32768 --cache-size 32768 --cache-mode 8,8
--gpu-split-auto False --gpu-split 70 --max-batch-size 4 --output-chunking True`.
Created via `add_service_to_db` + `rebuild_compose_file`, never started.

Three things §4 and §5 got wrong, now corrected in the code:

1. **A symlink farm in `~/.cache/exl3` cannot work.** HF snapshots are relative
   symlinks into `../../blobs`, and bind mounts don't traverse outward, so the
   model must be reached through a mount of the whole `~/.cache/huggingface`
   (`/hf-cache`) — exactly the ds4 path style. `~/.cache/exl3` is still mounted,
   for real directories produced by `convert.py`.
2. **`--model-dir` is derived, not hardcoded.** `compose_manager` splits
   `model_path` into dir + folder name, so either supply path works without a
   template change. Cosmetic wart: the model id on `/v1/models` is then the
   40-char snapshot hash (`--use-dummy-models` + `--dummy-model-names` can mask
   it if it ever matters).
3. **Dots are illegal in service names** — `validate_service_name` rejects them,
   so the existing `vllm-nomic-embed-text-v1.5` must predate that check. Hence
   `exl3-laguna-xs-3bpw`, not `exl3-laguna-xs-2.1-3.0bpw`.

Still open: EXL3 model discovery (Phase 2), legacy create-service UI, key-file
removal on service delete, `/health` readiness probe, and a test that renders
`tabbyapi.j2` (the suite passes at 843 but nothing covers the new template).


## 8. Honest cost/benefit

What EXL3 buys on this host that the existing four runners don't: low-bitrate QTIP quants
(that 1.6 bpw / coherent-70B claim is the actual pitch), `--cpu-moe-offload-layers` /
`--cpu-moe-split-experts` for MoE weight spilling to system RAM, HF-native multimodal, and
cache quantization at 2–8 bit. Overlap with llama.cpp GGUF and vLLM is large for anything
that fits in 96 GB at bf16/fp8 — so the case is specifically "big MoE at 3–4 bpw" and "HF
multimodal models GGUF doesn't have".

What it costs: a fifth image, ~20 touchpoints, bool-flag convention friction, a new model
supply path with no discovery, no benchmarks, no metrics, AGPL server, and a tagless upstream
whose config surface can shift under the template (that's what digest-pinning is for).
