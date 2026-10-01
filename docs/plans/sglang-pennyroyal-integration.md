# SGLang / Pennyroyal service

LLM-Dock's `sglang` engine adapts
[jpezzulli/sglang-rtxpro6000](https://github.com/jpezzulli/sglang-rtxpro6000),
also called Pennyroyal. The default image base is the digest of upstream
`v2.5.3` (source tag `pennyroyal-v2.5.3`, commit
`d00d88efc8d6281b12be4f4073126aec95038c55`). Upstream recipes, model-specific
kernels and chat template are retained. The adapter creates adapted Flash-Next recipe copies
settings before NIXL namespace derivation, recording quantization and capacity
in the namespace rather than overriding the final command.

## Build and host requirements

```bash
./build-sglang.sh
```

The build creates `llm-dock-sglang`. Override the base with
`SGLANG_BASE=<Pennyroyal image> ./build-sglang.sh`; an override must have the
same `/opt/pennyroyal/.venv` and `/usr/local/bin/pennyroyal` layout. A plain
upstream SGLang image does not provide these recipes.

**No host CUDA toolkit or NVIDIA driver is installed or upgraded.** CUDA
13.3 tools, CUDA 13.0 PyTorch/FlashInfer wheels, and any compatibility
libraries are confined to the container. The GPU still uses the host's
existing NVIDIA kernel driver. A successful CPU image build does not prove
GPU compatibility.

The container includes NVIDIA's user-mode compatibility libraries. The
launcher selects the CUDA 13.0/R580 user-mode libraries automatically on drivers
older than R580, and uses native host libraries on newer drivers.
`env:SGLANG_USE_CUDA_COMPAT` accepts
`auto` (default), `0` (disabled), or `1` (forced). See
[NVIDIA forward compatibility](https://docs.nvidia.com/deploy/cuda-compatibility/forward-compatibility.html)
for supported driver branches and GPU SKUs. This mechanism cannot guarantee
that an unsupported host driver works.

The compatibility package is pinned to NVIDIA's signed
`cuda-compat-13-0-580.178.04-1.el9.x86_64` RPM. Fedora 44 only publishes newer
compatibility packages, so the adapter uses NVIDIA's RHEL9 repository for
this package alone. No model service is created or started by the build helper.

Run a small GPU check before loading a model:

```bash
docker run --rm --gpus all \
  --entrypoint /usr/local/bin/llm-dock-sglang-gpu-check llm-dock-sglang
```

## Create a service

Choose **SGLang / Pennyroyal** in the New Service dialog. Enter a checkpoint
**directory**, alias and host port. The container listens on **8001**;
LLM-Dock supplies the API key and served model name. Services use the
`sglang-` prefix and appear in the chat selector when running.

Model paths use `/hf-cache` for `~/.cache/huggingface` or `/local-models` for
`~/.cache/models`. HF snapshot directories work because the full cache is
mounted, retaining access to symlinked blobs. Other paths require an
operator-authored `volumes` entry through the service API.

| Profile parameter | Target directory | Draft directory |
|---|---|---|
| `--profile next` (default) | Flash-Next NVFP4 | none; FR-Spec with native NEXTN |
| `--profile next-plain` | Flash-Next NVFP4 | none; native NEXTN without FR-Spec |
| `--profile 27b` | Qwen3.8-27B FP8 | `--draft-model-path` pointing at its DFlash2 checkpoint |

Example request body for `POST /api/services` (authenticate with the
dashboard token; `api_key` can be omitted to generate one):

```json
{
  "template_type": "sglang",
  "alias": "qwen38-27b-dflash2",
  "port": 3341,
  "model_path": "/local-models/Qwen3.8-27B-FP8",
  "params": {
    "--profile": "27b",
    "--draft-model-path": "/local-models/Qwen3.8-27B-DFlash2",
    "env:PENNY_HICACHE_SIZE_GB": "16",
    "env:SGLANG_HICACHE_NIXL_MAX_CACHE_GB": "100"
  }
}
```

The two launcher CLI parameters above and upstream `env:` knobs are the
configuration surface. Arbitrary `sglang serve` flags are rejected because
overriding a cache-layout flag after the recipe computes its NIXL namespace
can reuse incompatible persisted state. Upstream defaults retain the
524,288-token context and model-specific speculative decoding settings.

Flash-Next reads the checkpoint's `quantization_config`: ModelOpt selects
`modelopt_fp4`, while mixed NVFP4/FP8 compressed-tensors checkpoints select
`compressed-tensors`. No weights or checkpoint metadata are rewritten.
`env:PENNY_CONTEXT_LENGTH` (up to 524288), `env:PENNY_MEM_FRACTION_STATIC`
(between 0 and 1), and `env:PENNY_PREFILL_CHUNK_SIZE` tune the Next recipes.
Tracked upstream source stays intact for its image integrity check.
The adapter also enables upstream capacity/HiCache knobs in older local bases
that hardcoded them. Recipe shape changes fail the image build for review.

The machine-local counterpart to `vllm-qwen3-8-flash-next-mixed-nvfp4-fp8`
uses the same immutable HF snapshot with a 200000-token context, five running
requests, 30 Mamba state slots, 2048-token prefill chunks and a 0.925 static
GPU memory fraction. Its shared KV pool is capped at 200000 tokens: this is a
total across requests, not five simultaneous full-length contexts. Native
FR-Spec/NEXTN uses four draft tokens; vLLM's six-token MTP setting is not copied.
The existing vLLM Python overlays and INT4 PLE cache are engine-specific and
are not mounted. SGLang uses its own FP8 RAM-backed PLE table (about 48 GiB)
and a 16 GB HiCache allocation.
It is created as `sglang-qwen3-8-flash-next-mixed-nvfp4-fp8` on host port
3304, initially in a stopped state. The actual image config loader accepts this cached
checkpoint as `Qwen4ExpForConditionalGeneration` with `compressed-tensors`
quantization and 200000-token context; no weights were loaded for that check.

Use `env:PENNY_HICACHE_SIZE_GB` to size host RAM explicitly: upstream defaults
are 32 decimal GB for Next and 96 GB for 27B. RAM-backed Flash-Next PLE adds
about 48 GiB before runtime/model-loading overhead. The parameter reference
also exposes the NIXL disk budget, GPU selection, online FP8, Flash-Next
request/state capacity, and optional prepared NVMe PLE overlay.

## Lifecycle and persistence

Per-service compiler caches and NIXL storage are mounted at:

```text
~/.cache/llm-dock/sglang/<service-name>/compiler -> /cache
~/.cache/llm-dock/sglang/<service-name>/nixl     -> /nixl
```

They survive stop/recreate/delete. A rename selects a new directory; migrate
the old cache explicitly if needed. The adapter runs as root to use Docker's
automatically created bind directories without changing host ownership.
The upstream engine computes representation-specific namespaces beneath the
NIXL root. The template reserves all GPUs, while the upstream single-GPU
recipe selects GPU 0 by default; use `env:CUDA_VISIBLE_DEVICES` for a different
device. HiCache/NIXL needs 16 GB shared memory, unlimited memlock and
`seccomp=unconfined` for io_uring. The container is not privileged.

Startup may take many minutes for model hashing, loading, compilation and
graph capture. The inherited Docker `/health` check has a 20-minute start
period. The service's OpenAI endpoint is `http://<host>:<host-port>/v1`.
Open WebUI registration uses the same internal port. Request inspection and
API-key rotation use the standard LLM-Dock flows.

The adapter appends the dashboard's API key and alias to the final recipe
command. Chat sends the alias in its `model` field. Optional declared
reasoning levels map to `reasoning_effort`; `off` maps to `none`. Accepted
effort names remain a property of the chosen template, so declare only those
you use. Per-conversation sampling controls and llama-bench are not enabled
for this engine.

## Metrics

The unchanged recipes enable `/metrics`. The dashboard scrapes it with the
service key and displays running/waiting requests, KV usage, prompt/output
token counters, prefix-cache hit rate, speculative acceptance and retractions.
Cache hit and speculative acceptance are direct upstream gauges, rather than
fabricated lifetime counters. There is no SGLang `/slots` request.

Live prompt/decode rates use `realtime_tokens_total`, selecting only
`prefill_compute` and `decode` modes; cached prefill tokens are not counted as
compute. Request totals aggregate streaming and non-streaming labels, and
remain separate from scheduler counters because request totals update on
completion. Older engines without scheduler counters fall back to their
generation-throughput gauge while active. A change of counter source resets
the rate baseline. Engines without a retraction counter display “—”.

The SGLang details cards report KV capacity/active/prefix-cached/free tokens,
Mamba capacity/active/cached/free state slots, host KV cache used/capacity,
target-weight and KV allocations, CUDA graph memory summed across phases,
and mean tokens accepted per speculative verify. The live API scrape and a
short generation verified that scheduler counters advance before completion.

## Validation

Backend tests cover isolated service creation, template/port/image contracts,
inspection, profile validation, launcher identity/auth handoff, chat request
mapping, CUDA library selection and metric parsing. Frontend tests cover
creation and metric normalization; build/lint check the dashboard.

The local smoke build uses the pre-existing `llm-dock-pennyroyal:local`
image (source `07b6014733ad5200231a99bdffc88db1c08cbf9f`), rather than claiming
to have rebuilt the digest-pinned upstream release. Its CPU dependency and
NIXL POSIX checks pass. On the unchanged `575.57.08` host driver, CUDA 13.0
compatibility libraries
pass PyTorch GPU initialization/matmul, Triton JIT and FlashInfer BF16 attention.
CUDA 13.3 compatibility libraries failed device initialization with error 803,
which is why the adapter uses the CUDA 13.0 package matching its Torch wheels.
The user subsequently started the mixed NVFP4/FP8 service. Its first startup
took approximately 10 minutes 35 seconds, including checkpoint hashing,
target/MTP weight loading, target/draft CUDA graph capture and HiCache/NIXL
initialization. The built-in structured-output and chat warmups completed;
`/health` and authenticated `/v1/models` returned 200, unauthenticated
`/v1/models` returned 401, and Docker reported healthy. Observed GPU usage
was 88176 MiB. This validates startup and short warmup generation, not
long-context quality or throughput. Startup warnings include missing FP8 KV
scaling factors (defaults to 1.0), a TileLang data-race diagnostic during a
kernel compile that completed, and default untuned draft MoE kernels.
NIXL cleaned initial cache files because filesystem usage was 89.4%, above
its default cleanup threshold. The host toolkit is still CUDA 12.9.
