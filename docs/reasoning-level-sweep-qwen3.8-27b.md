# Reasoning-level sweep: `llamacpp-qwen3-8-27b-q8kxl`

Does the `--thinking` knob in pi actually change how hard Qwen3.8-27B thinks?
Tested 2026-09-09 against the local llama.cpp service on port 3329, using the
reusable harness in `scripts/reasoning-sweep/`.

## TL;DR

- **The on/off switch is real and perfect.** `off` produced **0 reasoning
  characters in every single run** (54 sweep cells + 24 direct-API calls).
- **The graded knob is not a budget.** Qwen3.8's chat template converts
  `reasoning_effort` into a *system-prompt sentence*, and it only knows three
  states: `low` ("keep your thinking brief"), `xhigh` ("think carefully…",
  also used for `high`), and `medium` = **no instruction at all**. pi exposes
  six levels but only four distinct behaviors exist.
- **The effect is inverted and task-dependent.** On a fixed prompt, `low`
  thought **2× longer** than `xhigh` (400 vs 202 chars, p = 0.0011). On other
  tasks the ordering flipped. Correctness never changed.
- **The noise floor is huge.** `high`, `xhigh` and `max` are the *same wire
  request* (`reasoning_effort: "xhigh"`), yet their means differ by up to
  230 characters across tasks — as much as the "real" between-level
  differences. Treat single-run level comparisons with suspicion.
- **Practical answer:** use `off` or `low`; do not expect `--thinking` to
  give a predictable thinking budget on this stack. For a hard cap use
  llama.cpp's `--reasoning-budget` server flag, or a vLLM/SGLang stack where
  Qwen's `thinking_budget` parameter is honored.

## What was measured

| | |
|---|---|
| Model | `llm-dock-qwen3-8-27b-q8kxl` → `llamacpp-qwen3-8-27b-q8kxl` (Qwen3.8-27B UD-Q8_K_XL GGUF, unsloth) |
| Server | llama.cpp `llama-server`, port 3329, `--parallel 2`, ctx 262144, MTP speculative decoding |
| Client | pi 0.84.1, `-p --mode text --no-tools --no-extensions --no-skills --no-prompt-templates --no-context-files --offline` |
| Levels | `off, low, medium, high, xhigh, max` (all six pi exposes except `minimal`, which the model marks unsupported) |
| Metric | character length of the model's private reasoning, summed over `thinking` blocks in pi's session JSONL (llama.cpp reports no reasoning-token split, so length is the available proxy) |
| Isolation | fixed minimal system prompt (151–175 prompt tokens), one pi process per cell, all `PI_*` env vars stripped, `stdin=DEVNULL` |
| Execution | **strictly sequential**, one cell at a time on a free GPU (an earlier 4-lane parallel pass was discarded for latency purposes; its character counts agreed) |

Tasks: **a** 12-step arithmetic (answer 76), **b** flawed derivation
`f(x)=x², f(a)=16 ⇒ a=4` (flaw: a = ±4), **d** "what colour is the sky"
(overthinking check), **e** trailing zeros of 2026! (answer 505, harder).
API-level control calls bypass pi entirely and send the exact
`chat_template_kwargs` pi would send for each level.

## The mechanism, verified at the wire

`~/.pi/agent/models.json` defines this provider as:

```json
"compat": {
  "thinkingFormat": "chat-template",
  "chatTemplateKwargs": {
    "enable_thinking": {"$var": "thinking.enabled"},
    "reasoning_effort": {"$var": "thinking.effort"}
  }
},
"thinkingLevelMap": {
  "off": "none", "minimal": null, "low": "low", "medium": "medium",
  "high": null, "xhigh": "xhigh", "max": null
}
```

(The map was cleaned up to these four real tiers after the experiment.
During the sweep it still listed `high`/`max` → `"xhigh"`; pi's
`clampThinkingLevel` walks *upward* for unsupported levels, so `high` and
`max` now clamp to `xhigh` — byte-identical requests to the ones measured
here, which is why the data still applies.)

So pi sends: off → `{enable_thinking: false, reasoning_effort: "none"}`;
low/medium → `{true, "low"/"medium"}`; **high, xhigh and max all →
`{true, "xhigh"}`**.

The GGUF embeds its own 9,993-char Qwen3.8 chat template (Unsloth-fixed).
Its only effort logic:

```jinja
{%- set resolved_reasoning_effort = reasoning_effort|default('xhigh') %}
{%- if resolved_reasoning_effort == 'high' %}{%- set resolved_reasoning_effort = 'xhigh' %}{%- endif %}
{%- if resolved_reasoning_effort not in ('xhigh', 'medium', 'low') %}
    {{- raise_exception('Unexpected reasoning effort ' ~ reasoning_effort ~ '...') }}
{%- endif %}
{%- if resolved_reasoning_effort == 'xhigh' %}
    {%- set reasoning_instructions = 'Reasoning effort is set to xhigh. Please think carefully ...' %}
{%- elif resolved_reasoning_effort == 'low' %}
    {%- set reasoning_instructions = 'Reasoning effort is set to low. Keep your thinking brief ...' %}
{%- endif %}
```

`reasoning_instructions` is prepended to the system message. `medium` sets
nothing. `enable_thinking: false` skips the block and injects an empty
`<think>\n\n</think>` into the generation prompt.

Confirmed live with `POST /apply-template` (rendering only, no generation):

| effort sent | system message injected |
|---|---|
| `none` (thinking off) | *(none; empty think block forced)* |
| `low` | "Reasoning effort is set to low. Keep your thinking brief…" |
| `medium` | **none at all** |
| `high` / `xhigh` | "Reasoning effort is set to xhigh. Please think carefully…" |
| `none`/`bogus` with thinking **on** | HTTP 500 — template `raise_exception` |

This matches the official Qwen3.8 template structure (GitHub issue
QwenLM/Qwen3.8#217 quotes the same code and notes `medium` is "the neutral
baseline"; #216 concludes "the dial is effectively two settings plus an off
switch"). Our Unsloth copy additionally aliases `high`→`xhigh`, where the
official template raises — which is why a literal `high` works here.

## Results — pi level (sequential, 3 runs/cell, thinking chars)

**task a — 12-step arithmetic** (all answers correct = 76)

| level | thinking chars mean (min–max) | answer chars |
|---|---|---|
| off | **0** (0–0) | 838 |
| low | 357 (349–374) | 346 |
| medium | **497** (339–667) | 408 |
| high | 326 (283–400) | 139 |
| xhigh | 319 (254–359) | 115 |
| max | 437 (381–520) | 65 |

**task b — flawed derivation** (18/18 runs identified a = ±4)

| level | thinking chars mean (min–max) | answer chars |
|---|---|---|
| off | **0** (0–0) | 1225 |
| low | 521 (465–549) | 719 |
| medium | 465 (372–556) | 390 |
| high | 481 (353–595) | 271 |
| xhigh | **549** (311–704) | 340 |
| max | 317 (231–371) | 292 |

**task d — trivial question** (all answers correct = blue)

| level | thinking chars mean (min–max) | answer chars |
|---|---|---|
| off | **0** (0–0) | 1258 |
| low | 379 (290–429) | 430 |
| medium | **731** (584–948) | 473 |
| high | 169 (161–181) | 66 |
| xhigh | 154 (121–220) | 22 |
| max | 276 (147–448) | 110 |

**task e — 2026! trailing zeros, harder, 1 run/level** (all answers correct = 505)

| level | thinking chars | answer |
|---|---|---|
| off | **0** | 1450 chars of worked solution |
| low | 522 | 322 chars of worked solution |
| medium | 438 | 599 chars of worked solution |
| high | 481 | **`505`** |
| xhigh | 401 | **`505`** |
| max | 371 | **`505`** |

Two patterns hold across all four tasks:

1. **`off` is exactly 0 thinking, always** — the toggle works perfectly.
2. **No monotone ramp with level.** The three levels that are literally the
   same request (`high`/`xhigh`/`max`) spread 154–549 chars *within the same
   task*, which is as large as any between-level difference. `medium` (no
   instruction) is the most verbose in a/d; `xhigh` is the most verbose in b
   and the least in d. The label does not predict the length.
3. **The answer gets terser as the label goes up.** On task e the top three
   levels emit the bare number `505` while off/low/medium write a worked
   solution; on task a, answer length falls from 838 (off) to 65 (max).

## Results — direct API (bypassing pi)

**task a, n=3/variant** — tracks the pi-level numbers closely, confirming pi's
wiring is faithful: none 0 · low 353 · medium 480 · high 331 · xhigh 380.

**single short prompt** ("17 sheep, all but 9 run away…"), n=8/variant,
sequential:

| variant | reasoning chars mean ± sd (min–max) |
|---|---|
| none | **0** (0–0) |
| low | **400.5 ± 76** (309–558) |
| medium | 288.8 ± 69 (191–379) |
| high | 224.4 ± 93 (94–365) |
| xhigh | 202.2 ± 76 (109–318) |

Mann–Whitney U (n=8 vs 8):

| pair | U | p (2-sided) |
|---|---|---|
| low vs xhigh | 63.0 | **0.0011** |
| low vs high | 61.0 | **0.0023** |
| low vs medium | 56.5 | **0.0100** |
| medium vs xhigh | 50.0 | 0.0587 |
| medium vs high | 43.0 | 0.2480 |
| **high vs xhigh** | 36.0 | **0.6744** |

`high` vs `xhigh` is the built-in **negative control** — identical requests —
and it is correctly indistinguishable. The `low` vs `xhigh` difference is
real for this prompt: telling the model "keep your thinking brief" makes it
think *twice as long* as telling it "think carefully… prioritize … clarity in
the final answer".

## Correctness

| task | expected | correct at every level? |
|---|---|---|
| a | 76 | yes, 18/18 |
| b | flaw: a = ±4 | yes, 18/18 |
| d | blue | yes, 18/18 |
| e | 505 | yes, 6/6 |

The knob changes *style and length*, not correctness, on these tasks. Note
that even `off` solved all four correctly — reasoning here buys presentation,
not accuracy.

## External corroboration

- **Qwen docs** (docs.qwencloud.com, *Thinking*): `reasoning_effort` levels are
  `low / medium / xhigh`, default `xhigh`; a separate `thinking_budget`
  parameter (Qwen3.8 open-source series) is the real token cap; the two cannot
  be combined.
- **Simon Willison** (2026-08-16, *"Qwen 3.8 27B is excellent, but it defaults
  to wildly overthinking things"*): the default `xhigh` burned 22,276 reasoning
  tokens to produce 3,223 output tokens for one SVG; he recommends running it
  "on low or even no reasoning levels at first".
- **QwenLM/Qwen3.8#216** (~700–1,000 captured calls): at `xhigh` the model
  sometimes ends its turn with an **empty answer** (`finish_reason: "stop"`,
  HTTP 200) — 18/93 (19.4%) at xhigh vs 0/95 at low/medium; traces end
  mid-deliberation with repetition loops. Suggested fix: change the default to
  `medium`. Also notes reasoning tokens scale with input length at xhigh
  (5.5× at 6k chars, 14.7× at 48k) while low/medium stay flat.
- **QwenLM/Qwen3.8#217**: the official template rejects `reasoning_effort:
  "high"` with HTTP 500 (Claude Code's default effort), which is why some
  harnesses appear to hang against this model.

We did **not** reproduce the empty-answer failure in 54 on-level cells
(0 empty; the only ≤5-char answers were the correct bare `505` on task e at
high/xhigh/max). Differences vs #216: pi's sampling parameters, MTP
speculative decoding, and short prompts. The failure is a known risk on this
model family regardless of harness.

## Limitations

- Thinking length is a *proxy*: llama.cpp does not split reasoning tokens out
  of `usage`, so character count stands in for effort.
- n=3 per sweep cell and n=8 for the headline API comparison; within-task
  variance is large (±50–90 chars sd at 150–700-char means).
- Short prompts only (≤175 tokens). #216 found the level effect grows with
  input length at xhigh, which this sweep does not exercise.
- One model, one serving stack (llama.cpp + this GGUF template). vLLM/SGLang
  may honor `thinking_budget` and behave differently.
- Latency figures from the discarded parallel pass are meaningless; the
  sequential pass gives ~1.6–6.3 s/cell on a free GPU.

## Reproduction

```bash
cd scripts/reasoning-sweep

# full sweep, one cell at a time
python3 sweep.py --model llm-dock-qwen3-8-27b-q8kxl/llamacpp-qwen3-8-27b-q8kxl \
  --tasks tasks/a.txt --levels off,low,medium,high,xhigh,max --runs 3 \
  --out results/a-seq --timeout 900

# direct-API control (exact kwargs pi sends per level)
API_KEY=... python3 api_control.py --base-url http://localhost:3329/v1 \
  --model llamacpp-qwen3-8-27b-q8kxl --task tasks/single.txt \
  --variants none,low,medium,high,xhigh --runs 8 --out results/api-single-x8

# what the template actually renders (no generation, no GPU)
curl -s -X POST http://localhost:3329/apply-template \
  -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"hi"}],
       "chat_template_kwargs":{"enable_thinking":true,"reasoning_effort":"low"}}'

python3 -m pytest test_sweep.py -q   # 28 tests
```

## Artifacts

```
results/a-seq, results/b, results/d-seq, results/e   # pi-level sweeps + raw sessions
results/merged-seq                                   # combined summary/csv/json
results/api-a-seq, results/api-single, results/api-single-x8
results/verification.md                              # independent recomputation
```

`results/` is gitignored; `summary.md` in each directory is the human-readable
view and `sessions/` holds the raw pi JSONL used for every number above.
