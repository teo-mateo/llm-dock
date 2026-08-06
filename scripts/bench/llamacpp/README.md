# llama.cpp service benchmark

Benchmarks a **running** llamacpp service from `services.json` — no model
reload, timings come from llama-server itself (`/completion` with
`cache_prompt: false`). Designed for config iteration: every run is appended
to `results/<service>.jsonl` with the container's actual CLI args and
VRAM/RAM usage, and a comparison table of all runs prints at the end.

## Usage

```bash
scripts/bench/llamacpp/bench.py llamacpp-deepseek-v4-flash-q8 --label baseline-ncmoe22
```

Options:

| Flag | Default | Meaning |
|------|---------|---------|
| `--label` | `""` | Tag for this config iteration (shows in the table) |
| `--sizes` | `2048,8192,32768` | Prefill sizes in exact tokens |
| `--gen` | `128` | Tokens generated in the short-context decode test |
| `--runs` | `3` | Decode test repetitions (median reported) |
| `--depth-gen` | `64` | Tokens generated after each prefill (decode at depth) |

## Metrics

- **decode_tps** — generation speed at 512-token context, median of `--runs`
- **pp_tps / pp_ms** — prefill speed per prompt size
- **tg_at_depth_tps** — generation speed immediately after each long prefill
  (shows KV-depth degradation)

## Iteration loop

1. Edit the service's `params` in `services.json`, rebuild compose, recreate
   the container (see CLAUDE.md "Adding a new vLLM service from the CLI",
   steps 3–5 — same flow for llamacpp).
2. Wait for the server to be up, then run the bench with a `--label` naming
   the change (e.g. `ncmoe20-ub4096`).
3. Compare the printed table; keep or revert.

The corpus (War and Peace, ~850K tokens) downloads to `data/` on first run.
`data/` and `results/` are gitignored.
