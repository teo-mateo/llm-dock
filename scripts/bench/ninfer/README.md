# NInfer service benchmark

Benchmarks a **running** ninfer service from `services.json` — no model reload.
Timings come from NInfer itself: every Chat Completions response carries an
engine-side `timings` object (prefill ms/tokens, decode ms/tokens, draft stats),
so the numbers are not HTTP round-trip measurements.

Designed for config iteration, like the llama.cpp benchmark: every run is
appended to `results/<service>.jsonl` with the container's actual CLI args and
the image's NInfer commit, and a comparison table of all runs prints at the end.

## Usage

```bash
scripts/bench/ninfer/bench.py ninfer-qwen38-27b-nvfp4 --label maxctx-bf16kv
```

Options:

| Flag | Default | Meaning |
|------|---------|---------|
| `--label` | `""` | Tag for this config iteration (shows in the table) |
| `--sizes` | `2048,8192,16384,32768` | Prefill sizes in exact tokens |
| `--gen` | `128` | Tokens generated in the short-context decode test |
| `--runs` | `3` | Decode test repetitions (median reported) |
| `--depth-gen` | `64` | Tokens generated after each prefill (decode at depth) |
| `--concurrency` | `2` | Lanes for the aggregate decode test (0 disables) |
| `--repeat` | `2` | Measurements per prefill size, best kept — the first one after an idle gap runs at unboosted SM clocks and reads ~4x low |

## Metrics

- **decode_tps** — short-context generation speed, median of `--runs`; the
  **accept** column is the DFlash/MTP draft acceptance over those runs
- **pp_tps / pp_ms** — prefill speed per prompt size; `pp_ms` is also the
  time to first token, since NInfer prefills before it samples
- **tg@\<size\>** — generation speed immediately after that prefill (KV-depth
  degradation)
- **C agg t/s** — aggregate decode across `--concurrency` simultaneous requests
  (the service's `--max-concurrency` lanes decide whether they batch or queue)
- **vram MiB** — GPU memory in use at the end of the run

## Sizing and cache discipline

Prompt sizes are exact: the filler is sized through `/v1/messages/count_tokens`,
not estimated from characters. Every measurement appends a unique suffix, and the
response's `cached_tokens` is recorded beside each prefill — the service keeps
prefix-reuse checkpoints on by default, and a cache hit would otherwise report a
prefill that never ran (the script prints `[CACHE HIT]` when that happens).

## Recorded results

`results/ninfer-qwen38-27b-nvfp4.jsonl` — RTX PRO 6000 Blackwell (96 GiB),
Qwen3.8-27B NVFP4 (official artifact, recipe v2). **Power limit matters as much as
the flags here**: the 300 W rows were measured with the card capped, the 600 W
rows uncapped, and they are not comparable. Every record stores
`gpu_power_limit_w` / `gpu_power_default_limit_w` (the comparison table prints
the limit).

| Config | Power | short decode | accept | pp @2k | pp @8k | pp @32k | pp @131k | pp @262k | tg @32k | tg @262k | C=2 agg | VRAM |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| fp8 KV, DFlash2 K=7, 32k ctx | 300 W | 133.4 | 36% | 5,168 | 5,545 | 4,743 | — | — | 119.3 | — | 186.3 | 27.4 GiB |
| bf16 KV, DFlash2 K=3, 262k ctx | 300 W | 122.4 | 70% | 5,190 | 5,509 | 4,632 | 2,685 | 1,695 | 92.7 | 67.9 | 175.7 | 42.8 GiB |
| bf16 KV, DFlash2 K=3, 262k ctx, single-shot | 600 W | 165.5 | 68% | 1,249 * | 5,810 | 7,502 | 4,202 | 2,550 | 127.6 | 92.2 | 222.1 | 42.9 GiB |
| bf16 KV, DFlash2 K=3, 262k ctx, steady | 600 W | 169.5 | 68% | 8,276 | 8,904 | 7,396 | 4,158 | 2,568 | 140.0 | 99.5 | 153.6 | 42.9 GiB |

\* measured before the per-size clock discipline below; that point read ~4x low
because the card was still at idle clocks. The steady row re-measures each size
twice and keeps the second, recording `clocks_sm_mhz` per point: its two
attempts agree within ±3% (8,190/8,276, 8,904/8,687, 7,396/7,185, 4,158/4,029,
2,568/2,547).

The **C=2 aggregate is a single 128-token burst and is noisy by construction**:
five bursts across these runs gave 186, 176, 222, 106 and 154 t/s, with per-lane
rates ranging 83–170 t/s. Which lane's prefill lands first decides whether the
two overlap in a decode round, so read it as "~150–220 t/s aggregate with 2
lanes", not as a point estimate.

Reading: prefill is unchanged by the draft and KV config (it does not use the
draft), unquantized KV costs ~20% of decode at depth (double the KV bytes to
read) while DFlash2 K=3 buys acceptance back (70% vs 36% at K=7). Lifting the
300 W cap raises every row (decode ~+35%, prefill ~+30% short-context, ~+50% at
full context) — which is why the cap is recorded per run. The card is
power-limited at 600 W under load, not thermally throttled (driver reports `HW
Thermal Slowdown: Not Active` at 87 C, `SW Thermal Slowdown` 516 ms cumulative).

Note on workload: these prompts are prose filler, which is the *pessimistic* end
for draft acceptance. The DGX Spark measurements below find DFlash2 prose
decode at roughly **1/3** of code-editing decode on the same box
(24.6–27.6 vs 74.0 tok/s) — so a code-shaped workload would raise these decode
numbers, not lower them.

## How this compares to public numbers

Different GPUs, engines, artifacts and measurement styles, so this is context,
not a scoreboard. Client-side "tg t/s" figures include prefill amortised over a
short generation and therefore sag with depth; server-side decode rates do not.

| Source | Hardware | Engine / config | Prefill | Decode |
|---|---|---|---|---|
| this README (steady row) | RTX PRO 6000 96 GB, 600 W | NInfer, NVFP4, bf16 KV, DFlash2 K=3 | 8,904 @8k; 2,568 @262k (102 s) | 169.5 short; 140 @32k; 99.5 @262k |
| [bittide/Reddit](https://bittide.aicompass.dev/article/a11f1683-44b6-45e9-882b-03f878b41791) | RTX 5090 32 GB, 600 W | vLLM 0.27.1, NVFP4 modelopt, fp8 KV, **no spec** | 7,005 @8k (TTFT 1.17 s); 2,781 @131k; 1,578 @262k (166 s) | 77.2 @1k; 64.7 @131k |
| [gist: vLLM vs NInfer](https://gist.github.com/PierpaoloPernici/f1d1382f8e357b4faffb1a9f584cc1df) | RTX 5090 32 GB | **NInfer**, NVFP4, int8 KV, MTP3 | ~3.0–3.3k cold (groupwise-int run) | 105–150 (MTP 2.0–2.8 tok/round, 43–61% accept) |
| same gist | RTX 5090 32 GB | vLLM, NVFP4, fp8 KV, MTP@3 | 6–18k | 117.3 @0 ctx; ~153 on code (α 92%) |
| [Tom's Hardware](https://www.tomshardware.com/tech-industry/artificial-intelligence/benchmarking-qwen-3-8-27b-on-rtx-5090-and-beyond-vram-capacity-alone-cant-overcome-severe-software-and-inference-engine-bottlenecks) | RTX 5090 x1 | vLLM recipe (32k ctx cap, no MTP) | — | ~20 |
| same article | RTX 5090 x2 | vLLM, MTP | — | 70–80, then 100–110 with MTP |
| same article | RTX 5090 x1 | llama.cpp, 262k ctx | TTFT ~30 min (not viable) | far below expectations |
| [salient-data/spark-qwen38-27b-nvfp4](https://github.com/salient-data/spark-qwen38-27b-nvfp4) | DGX Spark GB10, 121 GB unified | sglang, NVFP4, **DFlash2** | — | 74.0 code-edit; 24.6–27.6 prose; 218–231 @N=16 |
| [HF discussion](https://huggingface.co/Qwen/Qwen3.8-27B-FP8/discussions/9) | RTX PRO 6000 | vLLM, FP8, no spec | — | 23 (report by a user) |

What lines up and what does not:

- **Prefill is where a 96 GB card with a purpose-built engine shows**: 8.9k t/s at
  8k and 2.6k at full 262k context, versus 7.0k/1.6k for a 5090 running vLLM on
  the same model — and versus the 5090 + llama.cpp result where a 262k prefill
  does not finish in any usable time.
- **Decode is spec-decode plus bandwidth**: 169 t/s on prose filler against the
  5090's 77 t/s without speculation (2.2x, of which the DFlash2 drafter accounts
  for roughly half — its own acceptance is 68%) and against 105–150 t/s for
  NInfer+MTP3 on a 5090.
- **The DGX Spark numbers are the interesting cross-check**: same drafter
  (DFlash2), 6x less memory bandwidth, and their prose decode lands at ~1/6 of
  ours (27 vs 169), i.e. decode here is bandwidth-bound as expected — while their
  aggregate @N=16 (218–231) is close to our C=2 burst because our service caps at
  2 lanes.
- **Nobody else is publishing full-262k-context prefill/decode on a
  96 GB card**; the 32 GB owners cap context (Tom's: 32k recipe; gist: 128k with
  MTP3) or give up on long context entirely.
