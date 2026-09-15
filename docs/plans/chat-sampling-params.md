# Per-conversation sampling parameters

Implements #199 for the two engines whose sampling surface was verified on this
host: **vLLM** and **llama.cpp**. Everything else is deliberately unmapped — an
unverified field changes behaviour invisibly instead of failing, which is the rule
the reasoning-level feature runs on (`docs/plans/service-reasoning-levels.md`).

## Build identity

Everything below was measured on this host, 2026-09-15, against these builds:

| Engine | Identity |
|---|---|
| vLLM | image `vllm/vllm-openai:qwen38-flash-next` (`bd995759b5b8`), `vllm.__version__ == 0.1.dev20073+g8e685d198` |
| llama.cpp | image `llm-dock-llamacpp:latest` (`4e9495854d69`), upstream `6a1a922` (`metal : fix memory leak in early return (#28399)`) |

**vLLM identity caveat.** `llm-dock-vllm` is not built on this host and the pinned
base `vllm/vllm-openai:v0.24.0-cu129` is not pulled, so every vLLM observation is
from the image the running service actually uses (a dev build). The issue asked for
the pinned base; that could not be done without a ~20 GB pull. The field *names*
come from `ChatCompletionRequest` and the ranges from `SamplingParams.verify`, both
of which are stable across that range of versions, but a pinned-base re-run is the
one piece of this matrix still outstanding.

**No `llm-dock-ds4`/`llm-dock-ninfer` probes were run** and neither engine is
mapped; see *Engines left out*.

## The matrix

Verdicts, with the command that produced each. `ACCEPTS` means the engine reads the
field under that name and the value reaches the sampler; `IGNORES` means a 200 with
no effect, which is the outcome that makes a wrong name invisible.

### llama.cpp — `/v1/chat/completions`, live probe

Own container (`--name prflow199-llamacpp`, `llm-dock-llamacpp:latest`, `-ngl 0`,
`-c 4096`, `--jinja`, model `GLM-OCR.Q8_0`), CPU-only, port 8099, removed after.

| field | verdict | evidence |
|---|---|---|
| `temperature` | ACCEPTS | `"temperature":"abc"` → 400 `Field 'temperature': ... type must be number`; `-1` → 200 (**clamped**, not rejected) |
| `top_p` | ACCEPTS | `"top_p":"abc"` → 400; `1.5` → 200 clamped. Schema: `field_num("top_p").set_limits(0.0f, 1.0f)` (`tools/server/server-schema.cpp:93`) |
| `top_k` | ACCEPTS | `"top_k":"abc"` → 400; `-5` → 200 clamped. `set_limits(0, INT32_MAX)` (`:89`) |
| `min_p` | ACCEPTS | `"min_p":"abc"` → 400; `1.5` → 200 clamped. `set_limits(0.0f, 1.0f)` (`:97`) |
| `max_tokens` | ACCEPTS | `max_tokens=1` → `finish_reason=length`, `completion_tokens=1`; baseline `finish_reason=stop`, 3 tokens. `n_predict` with `->add_alias("max_tokens")` (`:44-47`) |
| `stop` | ACCEPTS | `stop=["ell"]` on "Say the word hello." → content `'H'`, `finish_reason=stop`; `stop="hello"` (string form) also accepted — `field_json("stop")` handles string and array (`:483`) |
| `seed` | ACCEPTS | `seed=42` twice → identical output (`peach word`); `seed=123` twice → identical (`banana`); `seed=7` → different (`apple`). `field_num("seed")` with a uint32 handler (`:176`) |
| `repetition_penalty` | **IGNORES** | `"repetition_penalty":"abc"` → 200, no error. The accepted name is **`repeat_penalty`**: `"repeat_penalty":"abc"` → 400 `Field 'repeat_penalty'` |
| `presence_penalty` | ACCEPTS | `"presence_penalty":"abc"` → 400. No `set_limits` declared (`:136`) |
| `frequency_penalty` | ACCEPTS | `"frequency_penalty":"abc"` → 400. No `set_limits` declared (`:133`) |
| any unknown key | IGNORES | `"toop_kl":5` → 200. `oaicompat_chat_params_parse` copies every unclaimed body key into the internal params (`tools/server/server-common.cpp:1391-1398`) |

The 400-on-wrong-type probe is the discriminator: a field the parser does not know
is never type-checked, so a 400 proves registration while a 200 on a *malformed*
value proves a silent drop. Out-of-range numerics are clamped, so range validation
has to live in llm-dock — sending `top_p: 1.5` to llama.cpp would be silently
rewritten to 1.0.

### vLLM — `/v1/chat/completions`, live probe + offline enumeration

Offline, no GPU, no container (`docker run --rm --entrypoint python3
vllm/vllm-openai:qwen38-flash-next -c ...`):

- `SamplingParams.__struct_fields__` contains all ten candidate fields (plus
  `min_tokens`, `logit_bias`, `n`, `ignore_eos`, `thinking_token_budget`, …).
- `ChatCompletionRequest.to_sampling_params` forwards `temperature, top_p, top_k,
  min_p, max_tokens, min_tokens, repetition_penalty, presence_penalty,
  frequency_penalty, seed, stop, logit_bias, n, ignore_eos, …` — the request keys
  below are exactly that method's inputs.
- `ChatCompletionRequest.model_config.extra == "allow"`: unknown body keys are
  accepted at the protocol layer and dropped.
- The protocol layer does **not** range-check. The ranges are enforced in
  `SamplingParams` construction, which turns an out-of-range value into a per-request 400.

Live against `vllm-qwen3-8-flash-next-mixed-nvfp4-fp8` (port 3301), one field per
request, `max_tokens` capped small:

| field | verdict | evidence |
|---|---|---|
| `max_tokens` | ACCEPTS | `16` → `length`, ct=16; `1` → `length`, ct=1; `0` → 400 `max_tokens must be at least 1` |
| `temperature` | ACCEPTS | `2.5` → 400 `temperature must be in [0, 2]`; `0` → 200 |
| `top_p` | ACCEPTS | `0` → 400 `top_p must be in (0, 1]` — **0 excluded**; `0.9` → 200 |
| `top_k` | ACCEPTS | `5` → 200; `SamplingParams`: `top_k must be 0 (disable), or at least 1` |
| `min_p` | ACCEPTS with a service-level exception | `0.1` → **400 `The min_p and logit_bias sampling parameters are not yet supported with speculative decoding.`** — the service runs `--speculative-config {"method":"mtp",…}`. The field is registered and forwarded; this service refuses it. |
| `repetition_penalty` | ACCEPTS | `1.3` → 200; `SamplingParams`: `repetition_penalty must be greater than zero` |
| `presence_penalty` | ACCEPTS | `2.5` → 400 `presence_penalty must be in [-2, 2]`; `0.5` → 200 |
| `frequency_penalty` | ACCEPTS | `0.5` → 200; range check as above (same validator family) |
| `stop` | ACCEPTS | `["ALPHA"]` → `finish_reason=stop` at ct=15 where the baseline ran to `length` at ct=16. Request type is `str \| list[str]`, **max 8 entries** (9 → pydantic `List should have at most 8 items`) |
| `seed` | parsed, effect not established | forwarded by `to_sampling_params`; `SamplingParams(seed=-1)` constructs. The live reproducibility check captured no text (the checkpoint spent the probe's token cap on `reasoning_content`), so **reproducibility is unverified on this build** |
| `repeat_penalty` | **IGNORES** | `1.3` → 200, no error: the llama.cpp name is the mirror image of the vLLM one |
| any unknown key | IGNORES | `"toop_kl":5` → 200, consistent with `extra="allow"` |

Context bound: `GET /v1/models` reports `max_model_len: 262144`. llama.cpp reports
`n_ctx` at `GET /props` → `default_generation_settings.n_ctx` (4096 on the probe
container); `/props` has no top-level `n_ctx` key.

## Decisions

**1. Which engines get a mapping.** `llamacpp` and `vllm` only. Both are verified
field-by-field above; nothing else was.

**2. Silently ignored is worse than rejected.** Both engines ignore unknown names
with a 200, so the field-name table is load-bearing and lives in one module
(`dashboard/sampling_params.py`). `repetition_penalty` is stored under that name —
the name a user reads in every OpenAI-compatible doc — and mapped to `repeat_penalty`
for llama.cpp. `test_llamacpp_renames_repetition_penalty_and_keeps_the_rest` and
`test_unmapped_engine_gets_no_sampling_key_at_all` are the guards. `min_p` stays
mapped for vLLM despite the 400 on a spec-decode service: a 400 is loud and reaches
the chat error surface, and un-mapping it would cost every vLLM service a field the
engine does support. The failure is recorded here so the next reader does not
"fix" it by silently dropping the field.

**3. `max_tokens` vs context.** Not bounded from the server in this change. Both
bounds exist and are readable (`max_model_len` on vLLM `/v1/models`,
`default_generation_settings.n_ctx` on llama.cpp `/props`), so the hook for a
follow-up is named rather than guessed at; the picker bounds the value only by
`max_tokens >= 1`, and an over-large value fails loudly at the engine.

**4. The tool-turn temperature pin.** The pin is the **default**, an explicit
conversation temperature wins. The measured evidence that produced `0.3` is kept,
moved to the `TOOL_TURN_TEMPERATURE` declaration in `chat/llm_proxy.py` (the repo's
comment policy puts a constraint at a declaration, not in a function body), and the
reversed order is pinned by
`test_explicit_temperature_beats_the_tool_turn_default`. The alternative that was
rejected: keeping the pin absolute, which would make every tool-using conversation
silently ignore the operator's temperature — the same silent-drop class this
whole feature is built to avoid.

**5. Global default.** Not implemented, per the issue's Out list. The seam is
`chat/settings_store.py`, which already holds the global system prompt that
`create_conversation` copies; a default sampling set would ride the same path.

**6. OpenRouter per-field derivation.** Not implemented: OpenRouter is out of the
mapping, so nothing needs narrowing. `sampling_params.supported_fields` keeps an
optional `capabilities` argument that can only *narrow* the engine's table, so
deriving per-model support later is additive and cannot invent a knob.

## Rejected and excluded

- **No merge semantics.** `PUT` replaces the whole set; `null` and `{}` both clear,
  and the column stores `NULL` for both so one empty state exists.
- **No new columns per knob.** One `sampling_params_json` TEXT column: a new knob
  costs no migration and no `allowed`-set entry.
- **No size cap on the blob.** Every field is bounded and only `stop` carries free
  text, so the field bounds bound the column; a second cap would be unreachable and
  read as a guard. `test_per_field_bounds_alone_keep_the_column_bounded` pins the
  worst legal payload.
- **No run-row column, no critique change, no spinoff params, no Android UI** —
  the issue's Out list, unchanged. Android needs nothing to honour this: the values
  are applied where the run is built.
- **Not merged with the reasoning-level control.** A level is an instruction to the
  chat template; these are sampler numbers. vLLM's `SamplingParams` carries
  `thinking_token_budget`, which is exactly the temptation this excludes.
- **No `n`/`logit_bias`/`min_tokens`/DYNATEMP/DRY/mirostat.** Enumerable on vLLM
  and llama.cpp, but neither is in the issue's candidate set, and a knob nobody
  asked for is the same cost in picker surface and in verification duty.
- **No `top_a`, `dry_*`, `xtc_*`, `typical_p`.** llama.cpp-only names with no vLLM
  equivalent under the same name; a field must be verified per engine to be offered.

## Deviations from the issue's proposal

- `conversations.sampling_params_json` stores `NULL` for both "unset" and `{}`; the
  proposal allowed `{}` to clear, and this makes that one state rather than two.
- The capabilities endpoint is `GET /api/chat/sampling-fields?service=…` returning
  descriptors (label, kind, min, max, step) rather than bare names, so bounds live in
  one place. The Android client is not required to use it.
- `stop` is capped at 4 entries, tighter than vLLM's 8 and llama.cpp's none: it is a
  composer surface, not a completeness exercise.
- `top_p` is validated as `(0, 1]` rather than `[0, 1]`: llama.cpp accepts 0, vLLM
  400s it, and the shared picker must offer what every engine offering it accepts.
- The run-time note is a single line in the existing `runNotice` slot, joined with the
  reasoning-level note when both fire, rather than a second UI element.

## Follow-ups worth filing

1. Bound `max_tokens` from the server (`max_model_len` / `n_ctx`), per decision 3.
2. A default sampling set in `chat/settings_store.py`, per decision 5.
3. Re-run the vLLM matrix on the pinned base once `llm-dock-vllm` is built here.
4. Per-model capability narrowing for OpenRouter, if it ever enters the mapping.
5. ds4 / TabbyAPI / NInfer / ik_llamacpp: each needs its own probe before it can be
   offered anything.
