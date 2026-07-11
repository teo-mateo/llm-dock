# Qwen3.5-397B-A17B IQ4_XS — baseline benchmarks (2026-07-08)

Service: `llamacpp-qwen3-5-397b-a17b-iq4xs` (port 3306)
Image: `llm-dock-llamacpp` built 2026-07-05, llama.cpp fork commit `a410713`, CUDA 12.9
Model: AesSedai/Qwen3.5-397B-A17B-GGUF IQ4_XS (190 GB; experts IQ3_S/IQ4_XS mix, attn/shexp Q8_0; **no MTP tensors**)

## Config at time of measurement (BEFORE 2026-07-08 param changes)

```
-b 4096 -c 120000 -fa 1 -ngl 999 -ub 3072 -ctk q8_0 -ctv q8_0 --no-mmap
-ot "blk\.(2[5-9]|[3-5][0-9])\.ffn_(up|gate|down)_exps=CPU"   # layers 25-59 experts on CPU (35 layers)
-t 12 -tb 24
--temp 0.6 --top-p 0.95 --top-k 20
--spec-type ngram-map-k4v                                      # defaults: size-n 12, size-m 48, min-hits 1
# n_slots = 4 (default), unified KV
```

VRAM at idle-serving: 87,962 / 97,887 MiB (RTX PRO 6000 Blackwell 96 GB, also drives display).

## Results — /tmp/bench_qwen3-5-397b.py (PP=1024 exact tokens, TG=512, ignore_eos, cache_prompt=false)

| Run | Wall | PP | TG | Spec decode |
|---|---|---|---|---|
| v1: repetitive filler, temp 0 (**invalid** — ngram drafter got 100% acceptance, mean len 47.6) | 15.24 s | 332 t/s | 44.1 t/s | 498/498 |
| v2: varied prose, served sampler — **contended** with a user request | 22.58 s | 290.6 t/s | 27.2 t/s | 407/407, mean len 46 |
| v2 rerun — believed clean, actually contended with story gen (task 2240) | 17.37 s | 374.2 t/s | 35.1 t/s | 419/419, mean len 47.6 |

## Real-world reference (from server logs, same session)

- Creative generation ("long story about a short cat", task 2240), solo: **~15.5–16 t/s TG**;
  draft acceptance **0.161** (31/192, mean len 8.75) — ngram spec-decode near-useless on novel text.
- Same request while a benchmark ran concurrently: tg_3s dropped to ~5–8 t/s per request.
- Full-request average over 1111 tokens with two contention episodes: 10.38 t/s.
- Benchmark-style "restate the input" text: 100% draft acceptance, mean len ~47 → TG ~35 t/s.
- PP at 1024 tokens: ~290–374 t/s depending on contention (~374 believed near-uncontended-prefill).

## Interpretation

- TG floor (novel text) ≈ 15.5–16 t/s; TG ceiling (copy-heavy text) ≈ 35 t/s. Decode gated by
  CPU-resident routed experts (35 layers offloaded).
- ngram-map-k4v with defaults (min-hits 1, size-m 48) loses money on novel text: 48-token drafts
  at 16% acceptance, each miss burns a wide MoE verify pass through CPU experts.
- 4 LRU slots caused surprise full re-prefills of chat history (slot without the conversation's KV).

## Changes applied 2026-07-08 (in services.json, to compare against this baseline)

- `-ot` → `blk\.(2[7-9]|[3-5][0-9])...` — layers 25–26 experts back on GPU (~5.8 GB), 33 CPU layers.
- `--parallel 1` — KV/prefix-cache locality, no interleaving.
- `--spec-ngram-map-k4v-min-hits 2`, `--spec-ngram-map-k4v-size-m 16`.

Benchmark script: `/tmp/bench_qwen3-5-397b.py` (session-temporary; PP=1024/TG=512 vs
`http://127.0.0.1:3306/completion`, exact-token prompt via /tokenize, reports server timings
incl. draft acceptance).

## AFTER results (same script, -n 3, new config, uncontended, 2026-07-08)

VRAM after load: 92,975 / 97,887 MiB (~4.9 GB free; the two expert layers took ~5 GB as predicted).

| Run | Wall | PP | TG | Spec decode |
|---|---|---|---|---|
| 1 | 35.01 s | 414.6 t/s | 15.9 t/s | 0/0 (map hasn't seen patterns 2x yet) |
| 2 | 34.44 s | 412.1 t/s | 16.0 t/s | 0/0 |
| 3 | 22.27 s | 424.2 t/s | 25.8 t/s | 433/433 (map learned the repeated run) |

vs baseline:

- **PP: 374 → ~415–424 t/s (+11%)** — expert layers 25–26 back on GPU.
- **TG novel-text floor: ~16 t/s, now with zero wasted drafts** (min-hits 2 keeps the drafter
  silent on first-seen text instead of betting 48 tokens at 16% odds). Baseline floor was
  15.5–16 with wasteful drafting, so pure decode gained slightly and the failed-draft tax is gone.
- Run 3 shows min-hits 2 working as designed: once a pattern repeats, drafting kicks in fully.
- First real-world request on new config (4.8k-token task): draft acceptance 0.397 (was 0.161),
  TG 14.4 t/s at that context depth.
- `--parallel 1` KV-cache-locality benefit not measurable by this script (needs a multi-turn chat).
