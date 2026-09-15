# GLM-5.3-Flash UD-Q2_K_XL — llama.cpp settings sweep

Probe behind the `llamacpp-glm-5.3-flash-q2kxl` service config (port 3336).
The sweep ran on image `llm-dock-llamacpp:glm5next-lru` = ggml-org PR #27754
glm5next + PR #27861 MoE expert LRU cache, commit `ffe1bae08`; both
`llamacpp-glm-5.3-flash-q2kxl` (3336) and `llamacpp-glm-5.3-flash-q2kxl-lru`
(3339) now run `llm-dock-llamacpp:glm5next-0910-lru` — the newer base the last
section of this document landed — with the final config below.

Objective: highest prefill (PP) and generation (TG) throughput on the host
below, for a 101.25 GiB model on a 97,887 MiB GPU.

## Host

- RTX PRO 6000 Blackwell WS, 97,887 MiB, PCIe Gen4 x16 (~26-28 GB/s under load)
- Ryzen 9 5900X, 12c/24t, dual-channel DDR4 (~40-45 GB/s), 125 GiB RAM
- Model loaded `--no-mmap`; reload ~40-90 s

## Method

Per config: PUT params -> rebuild compose -> force-recreate -> wait `/health`
-> `scripts/bench/llamacpp/bench.py <svc> --sizes 2048,8192,32768[,65536]
--runs 5`. Metrics: PP per prompt size, TG median/warm over 5x128-token
generations at 512 ctx, and TG over the 64 tokens following each long prefill
("TG at depth", a cold-cache figure). All runs kept `-lv 4` so each load log
carries the buffer-size breakdown.

## Model facts measured from the load logs

- 45 decoder layers: blk.0-2 dense MLP, 42 MoE (288 experts, top-8), 11 MLA
  layers (blk.3,7..43), 34 KDA layers (`n_head_kv = 0`).
- `-ncmoe N` expands to per-block expert regexes for `blk.0..N-1`; blk.0-2 have
  no expert tensors, so host-resident MoE layers = N-3, at 2,331.8 MiB each.
- blk.45 (MTP/nextn head, 29 tensors, 2.60 GiB) is skipped as "unused" while
  `--spec-type none`. Not in VRAM or RAM.
- mmproj is not configured: the 1.05 GiB F16 projector in the HF repo is not
  loaded (image requests return 500 "provide the mmproj").
- MoE expert cache costs 7.766 MiB per slot per host layer; decode-only
  (`n_tokens == 1`); preallocated for every host-resident expert layer.
- At `-c 262144`, `-ub 512`: KV 1,496 (MLA q8_0) + 2,112 (indexer f16) +
  145.6 (KDA state); CUDA0 compute 2,437; CUDA_Host compute 913.
- Candidate buffer model: compute ~= 1497 + f(ub, n_ctx); c 131072 halves KV
  to 1,804 and compute (ub 1024) to 2,251.
- Flash attention is forced on by the quantized V cache.

## Baseline (as found)

`ncmoe16 cache152/1 ub512 b2048 c262144 tb24 t12` — PP 357/326/301, TG 59.0
median (62.1 warm), TG at depth 36-39, VRAM 94.5 GiB.

## Results

| # | config (delta from baseline) | PP2k | PP8k | PP32k | PP64k | TG med | TG warm | TG@depth | VRAM MiB |
|---|---|---|---|---|---|---|---|---|---|
| 0 | baseline | 357 | 326 | 301 | - | 59.0 | 62.1 | 36-39 | 94,471 |
| 1 | `cache 0` | 399 | 356 | 333 | - | 25.8 | 26.3 | 25-26 | 78,634 |
| 2 | `cache 0 ub1024` | 587 | 597 | 557 | - | 21.3 | 27.3 | 25-26 | 79,697 |
| 3 | `cache 0 ub2048` | crash | | | | | | | |
| 4 | `cache 0 ub1024 ncmoe10` | 840 | 830 | 753 | - | 35.5 | 35.8 | 34-35 | 93,981 |
| 5 | `cache96 ub1024 ncmoe10 c131k` | 838 | 831 | 748 | - | 57.8 | 59.5 | 37-42 | 96,392 |
| 6 | + `tb12` | 858 | 836 | 765 | - | 58.8 | 60.8 | 39-43 | 96,370 |
| 7 | + `t24` / `inserts2` / affinity+poll | 836-862 | 823-839 | 744-750 | - | 54.6-57.1 | - | 37-43 | 96,3xx |
| 8 | cache96 ncmoe10 ub1024 tb12 c131k | 857 | 839 | 756 | 652 | 61.7 | 61.8 | 36-45 | 96,533 |
| 9 | cache0 ncmoe8 ub1024 tb12 c131k | 990 | 961 | 840 | - | 41.8 | 41.8 | 37-41 | 96,101 |
| 10 | cache64 ncmoe10 ub1024 tb12 c131k | 852 | 839 | 756 | - | 56.6 | 56.6 | 37-42 | 95,222 |
| **11** | **final: cache48 ncmoe10 ub1024 tb12 c131k** | **837** | **820** | **751** | **-** | **51.6** | **51.6** | **35-39** | **94,350** |

## Levers, ranked by what they bought

1. **Expert cache off (VRAM reclaimed)** — frees 15.9 GiB, which is the only
   way to put more layers on the GPU. Costs 2.4x on warm TG by itself.
2. **`-ncmoe 16 -> 10`** — six expert layers (13.99 GiB) back on the GPU.
   PP +41%, TG +31%, sublinear (~+5.6% PP/layer) because the CPU stream is no
   longer the sole bottleneck. Host expert bytes 30.3 -> 16.3 GiB.
3. **`-ub 512 -> 1024`** — prefill is CPU-stream bound and each ubatch touches
   all 288 experts, so bigger ubatch amortizes the same RAM traffic over more
   tokens: PP +60%. Plateau reached at 1024 (1536 gave 0%, ub 2048 crashes,
   see below).
4. **Cache 96 slots on the reduced host set** — 5.2 GiB buys back ~all TG
   (35.8 -> 58.8 warm) with **no measurable PP cost** at this VRAM level.
5. **`-c 262144 -> 131072`** — frees 1.8 GiB KV + 1.1 GiB compute, which is
   what lets the cache and 10-layer offload coexist inside 96 GiB.
6. **`-tb 24 -> 12`** (physical cores) — +2-5% on both PP and TG; SMT siblings
   hurt the memory-bound CPU expert GEMMs.

## Rejected

- `-ub 2048`: reproducible `CUDA illegal memory access` on the first full
  prefill, at both c262144 and c131072 (independent of context, matches
  upstream sm_120 GLM-5.3 reports). `-ub 1536` runs but gains nothing over 1024.
- `--moe-expert-cache-inserts 2`, `-t 24`, `--cpu-range-batch 0-11`
  `--poll-batch 1`: neutral to worse than the final config.
- MTP speculative decoding (`--spec-type draft-mtp`, +2.60 GiB): verification
  batches bypass the decode-only expert cache, and CPU `mul_mat_id` traffic
  scales with tokens per batch, so drafts multiply exactly the host-RAM
  traffic that bounds decode. Not tested on-GPU.
- Vision (`--mmproj`, +1.05 GiB + encode buffer): never enabled; no room at the
  final config without trading cache size or a GPU layer.

## VRAM margin and the cache-size knob

The first final config (cache 96) left 1,186 MiB free at load and 169 MiB
system-wide once the server and the desktop had settled — unusable. Two things
consume the headroom, and neither is the model: the llama-server process grows
~0.3-1.5 GiB over its load-time buffers during long-prompt runs, and the
desktop (Xorg + gnome-shell + Firefox) holds ~1.3-1.5 GiB that fluctuates.

At ncmoe 10 / c131072 / ub 1024 the only free knob is the expert cache, and
the measured cost curve is shallow:

| cache slots | PP 8k/32k | TG warm | TG at depth | free at load | free live |
|---|---|---|---|---|---|
| 96 | 839/756 | 58.8-61.7 | 40-45 | 1,186 | 169 |
| 64 | 839/756 | 56.6 | 37-42 | 2,328 | ~2,000 |
| 48 | 820/751 | 51.6 | 35-39 | 3,188 | 2,870 |
| 0 (ncmoe 9) | ~895/~790 (est) | ~38 (est) | - | ~4,700 (est) | - |

Dropping 96 -> 48 costs ~7 t/s of steady-state TG (12% vs the original
baseline's 59) and buys ~2.7 GiB of margin; PP is unchanged. The no-cache
route buys PP instead: cache 0 at ncmoe 8 is +15% PP over cache 96 (961 vs 839
at 8k) but costs ~17 t/s of TG and, because the extra GPU layers eat the freed
cache bytes, leaves no more margin than the cache-96 config.

## New-base comparison (PR #27754 head d94f44e79, 2026-09-10)

Upstream main cannot run this model: as of `8ea290247` it registers only
`glm4`/`glm4moe`/`glm-dsa`, and `llama_model_load` fails with
`unknown model architecture: 'glm5next'` (verified against the `:latest`
image). PR #27754's head, however, is 43 commits ahead of the Aug 28 base our
image was built from and rebased onto recent main; PR #27861 (LRU cache)
cherry-picks onto it cleanly. Two images were built and A/B'd against the
originating one with byte-identical configs:

- `llm-dock-llamacpp:glm5next-0910` — PR head only (no cache)
- `llm-dock-llamacpp:glm5next-0910-lru` — PR head + LRU cherry-pick

One flag rename is required on the new base: `--no-mmap` (deprecated alias) is
no longer accepted; use `--load-mode none`.

Identical config, no cache (`cache0 c131072 ub1024 ncmoe10 tb12`):

| base | PP2k | PP8k | PP32k | TG warm | TG@2k | TG@8k | TG@32k |
|---|---|---|---|---|---|---|---|
| old `glm5next-lru` | 853 | 831 | 751 | 36.2 | 35.7 | 34.9 | 29.2 |
| new `glm5next-0910` | 861 | 858 | 772 | 37.7 | 37.6 | 35.3 | 34.0 |

Identical config, cache 48 (`cache48 c131072 ub1024 ncmoe10 tb12`):

| base | PP2k | PP8k | PP32k | TG warm | TG@2k | TG@8k | TG@32k |
|---|---|---|---|---|---|---|---|
| old `glm5next-lru` (s14) | 837 | 820 | 751 | 51.6 | 35.3 | 39.0 | 35.9 |
| new `glm5next-0910-lru` | 860 | 848 | 771 | 52.4 | 39.3 | 39.2 | 36.3 |

Verdict: the newer base is ~3% faster on prefill and marginally faster on
decode, consistently in both cache states, at identical VRAM. Not a step
change, but a free one.

## Final config (applied)

```
-ngl 999 -c 131072 -fa auto -b 2048 -ub 1024 -t 12 -tb 12
--load-mode none --parallel 1 --fit off --spec-type none
-ncmoe 10 --moe-expert-cache 48 --moe-expert-cache-inserts 1
-ctk q8_0 -ctv q8_0 -lv 4
```

As applied today, on `glm5next-0910-lru`. It was measured on the old base as
`--no-mmap`, which that base takes and the new one rejects (see the flag
rename above). Perf-relevant flags only — both services also carry `--jinja`,
`--temp 1.0` and `--top-p 0.95`.

vs baseline: **PP 2.5x** (301 -> 751 t/s at 32k; 820 at 8k), **TG parity at
depth** (35-39 vs 36-38 cold-cache; 59 -> 51.6 t/s steady-state, -12%),
and ~2.9 GiB free instead of 169 MiB. Context traded 256k -> 128k.

The cache size is the one remaining knob: 64 slots gives back ~5 t/s of TG at
~2.0 GiB free, 96 gives the original 59-62 t/s but no margin. For a PP-tilted
alternative, cache 0 + ncmoe 9 should land near 895 t/s at 8k with ~4.5 GiB
free (six GPU-hosted expert layers, no cache; not yet measured at that
setting).

Raw rows: `scripts/bench/llamacpp/results/llamacpp-glm-5.3-flash-q2kxl.jsonl`.
Load logs with full buffer breakdown: `/tmp/sweep/logs/*.log` (machine-local).
