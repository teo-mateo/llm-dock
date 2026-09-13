# Reasoning-level sweep

Measures how much a model actually *thinks* at each of pi's thinking levels,
and whether the level knob changes anything. Two tools:

- **`sweep.py`** — the main sweep. Drives the `pi` CLI headlessly
  (`pi -p --model <m> --thinking <level> --no-tools ...`) at each level on a
  set of fixed reasoning tasks, parses the pi session JSONL of every run, and
  records reasoning length, final answer, token usage and latency.
- **`api_control.py`** — a control that bypasses pi and POSTs the same tasks
  straight to the OpenAI-compatible server with the exact
  `chat_template_kwargs` pi would send per level. This separates
  *"pi isn't passing the level"* from *"the model/server ignores the
  graded effort"*.

## Why this exists

For local OpenAI-compatible models (llama.cpp), pi's thinking levels are
delivered as `chat_template_kwargs` (`thinkingFormat: "chat-template"`).
The `enable_thinking` boolean is a real on/off toggle, but the graded
`reasoning_effort` string (`low`/`medium`/`xhigh`) only matters if the
model's Jinja chat template reads it — and then only in whatever way the
template chooses. Qwen3.8's template, for example, turns it into a
*system-prompt sentence* and recognizes only three states. So the question
is empirical: *do reasoning lengths move with the level?* This sweep answers
it with per-cell data.

## Findings (2026-09-09, Qwen3.8-27B on llama.cpp)

Full write-up: [`docs/reasoning-level-sweep-qwen3.8-27b.md`](../../docs/reasoning-level-sweep-qwen3.8-27b.md).

- `off` → **0 reasoning chars in every run** (toggle is perfect).
- The graded knob is **not a budget**: pi's 6 levels collapse to
  `off` + three template states — `low` instruction, `medium` (no
  instruction), `xhigh` instruction. `high`/`xhigh`/`max` are the *same*
  request.
- Effect is **inverted and task-dependent** (e.g. on a fixed prompt `low`
  thought 400 chars vs `xhigh` 202, p = 0.0011), and correctness never
  changed. `high` vs `xhigh` — identical requests — is the noise-floor
  control (p = 0.67).
- Practical: use `off`/`low`; for a hard cap use llama.cpp's
  `--reasoning-budget`, not `reasoning_effort`.

## Tasks

| id | task | expected |
|---|---|---|
| `a` | 12-step arithmetic chain | 76 |
| `b` | flawed derivation `f(x)=x², f(a)=16 ⇒ a=4` | flaw: a = ±4 |
| `d` | "what colour is the sky on a clear day" (overthinking check) | blue |
| `e` | trailing zeros of 2026! (harder, Legendre) | 505 |
| `single` | "17 sheep, all but 9 run away…" (short API probe) | 9 |
| `hard` | smallest `n` with ≥1000 trailing zeros in `n!` | 4005 |
| `large` | count/sum/largest of the primes in a 1500-integer list (regenerate: `make_large_task.py`) | `tasks/large.expected.json` |

## Metrics

| Metric | Source | Notes |
|---|---|---|
| `thinking_chars` | session JSONL, sum of all `thinking` content blocks | **primary metric** — length of the model's hidden reasoning |
| `thinking_blocks` | session JSONL | >1 means multi-turn reasoning |
| `answer_chars` / `answer_full` | session JSONL, last assistant message text | the visible answer |
| `out_tokens` / `prompt_tokens` | session JSONL `usage` | llama.cpp reports no reasoning-token split, so char length is the length metric |
| `latency_s` | wall clock around the pi run | includes pi startup (~1–2 s) |
| `recorded_level` / `recorded_model` / `level_ok` / `model_ok` | session JSONL `thinking_level_change` / `model_change` entries | sanity checks that pi applied the requested level/model |

## Usage

```bash
cd scripts/reasoning-sweep

# One question, all levels, 2 runs each
python3 sweep.py run \
  --model llm-dock-qwen3-8-27b-q8kxl/llamacpp-qwen3-8-27b-q8kxl \
  --tasks tasks/a.txt \
  --levels off,low,medium,high,xhigh,max \
  --runs 2 --out results/a

# Merge several output dirs into one combined report
python3 sweep.py merge results/a results/b results/d --out results/merged

# Direct-API control (what the server itself does with the kwargs)
API_KEY=key-... python3 api_control.py \
  --base-url http://localhost:3329/v1 \
  --model llamacpp-qwen3-8-27b-q8kxl \
  --task tasks/a.txt \
  --variants none,low,medium,high,xhigh --runs 3 --out results/api-control
```

Output per `--out` dir: `results.csv`, `results.json` (full answers),
`summary.md`, `answers/*.txt`, and `sessions/<task>__<level>__r<n>/*.jsonl`
(raw pi session logs, kept so any number can be re-derived independently).

Re-running with the same `--out` **resumes**: completed ok cells are skipped.

### Notes

- The sweep strips all `PI_*` env vars before spawning pi, so a child pi
  can never inherit a parent agent's model/level/session, and passes
  `stdin=DEVNULL` (an inherited open stdin makes pi block forever).
- Before any cell runs, `pi --list-models <model>` is probed; an unknown
  model id fails fast with exit code 2 instead of 12 identical failed cells.
- Runs use a fixed minimal system prompt (`--system-prompt` to override)
  and `--no-tools`, so the measurement is isolated from the coding-agent
  system prompt and tool calls.
- Per-run timeout (`--timeout`, default 900 s) turns a hung run into a
  failed cell row instead of a stuck sweep.
- `minimal` is not in the default level list: this model's
  `thinkingLevelMap` marks it unsupported (`null`).
- Resume aborts (exit 2) if the previous `results.json` was produced with a
  different model, and skips only cells already recorded `ok`.

## What each level actually sends

For `llm-dock-qwen3-8-27b-q8kxl` (from `~/.pi/agent/models.json`; the entry
now declares only the model's four real tiers — `off`, `low`, `medium`,
`xhigh` — and pi clamps `minimal`→`low`, `high`/`max`→`xhigh`):

| pi level | `reasoning_effort` sent | template state |
|---|---|---|
| `off` | `none` + `enable_thinking:false` | forced empty `<think></think>` |
| `low` | `low` | "keep your thinking brief…" system line |
| `medium` | `medium` | **no instruction** |
| `xhigh` | `xhigh` | "think carefully…" system line |

`minimal`, `high` and `max` are no longer offered; if requested they clamp
up to `low` / `xhigh` / `xhigh` respectively (same wire values as before).

To see the rendered prompt for any level without generating anything:

```bash
curl -s -X POST http://localhost:3329/apply-template \
  -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"hi"}],
       "chat_template_kwargs":{"enable_thinking":true,"reasoning_effort":"low"}}'
```

## Interpreting results

- **off ≈ 0 thinking, on-levels similar to each other** → the server honors
  the on/off toggle; the graded effort is a prompt nudge, not a budget. Check
  the template (section above) before calling the levels an illusion — Qwen3.8
  *does* change the prompt, the effect is just small and non-monotone.
- **Monotone rise with level** → real effort control (not the case here).
- **off produces long thinking** → the toggle isn't reaching the server
  (check `api_control.py`: if the API-level `none` variant also thinks, the
  template ignores `enable_thinking: false`).
- **high/xhigh/max differing from each other** → measurement noise, not a
  level effect: those three are the same request. Their spread is your
  noise floor.
- **Trivial task (d) with long thinking at high levels** → overthinking.
- `level_ok: false` rows mean pi did not record the requested level —
  investigate before trusting that cell.

## Tests

```bash
cd scripts/reasoning-sweep && python3 -m pytest test_sweep.py -q   # 30 tests
```

Covers: session JSONL parsing (multi-block, multi-turn, truncated lines,
non-numeric usage), env sanitization, pi command shape, model preflight,
`stdin=DEVNULL`, fake-pi end-to-end runs (success, failure, timeout, empty
session), stale-session cleanup, resume skip/abort, merge, summary
rendering, and api_control variant mapping + HTTP server behaviour
(including `finish_reason: length`).
