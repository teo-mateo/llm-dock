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
Qwen3.8-27B NVFP4:

| Config | short decode | accept | pp @8k | pp @262k | tg @32k | C=2 agg | VRAM |
|---|---|---|---|---|---|---|---|
| fp8 KV, DFlash2 K=7, 32k ctx | 133.4 t/s | 36% | 5,545 t/s | — | 119.3 t/s | 186.3 t/s | 27.4 GiB |
| bf16 KV, DFlash2 K=3, 262k ctx | 122.4 t/s | 70% | 5,509 t/s | 1,695 t/s (154.6 s) | 92.7 t/s | 175.7 t/s | 42.8 GiB |

Reading: prefill is unchanged by the draft and KV config; unquantized KV costs
~20% of decode at depth (double the KV bytes to read) while DFlash2 K=3 buys the
acceptance back (70% vs 36% at K=7) — the two effects roughly cancel at short
context and K=3 wins per speculative round on long ones.
