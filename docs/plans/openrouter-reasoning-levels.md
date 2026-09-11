# OpenRouter reasoning levels — plan

Add per-model reasoning ladders to the curated OpenRouter model list, using
OpenAI-style `reasoning.effort` only. Ladders are fetched from OpenRouter's own
capability metadata when a model is added to the shortlist and stored on the
entry, so at request time the ladder is static config — the same status a local
service's `reasoning_levels` has today.

**Revised 2026-09-11 after independent review** (`dev-verifier`, read-only, against
`5367504`). Five corrections came from source the first draft asserted without
reading, and are marked *corrected* where they reverse an earlier claim. The
reviewer's own figure for `default_enabled` (146) was wrong; re-derived: **123**.

## 1. Goal and scope

**Decided by the user.** Two constraints came from the request rather than from this
analysis, and are treated as fixed:

- The ladder is captured **at add-time** and **persisted on the shortlist entry**.
- **OpenAI-style only**: send `reasoning.effort`. No `enabled`, no `max_tokens`,
  no `exclude`, no Anthropic budget dialect.

| ID | Requirement | Acceptance |
|---|---|---|
| R1 | Adding a model to the shortlist records the ladder OpenRouter publishes for it | After `PUT /api/chat/settings/openrouter-models`, `GET` returns `reasoning_levels` on that entry, matching upstream `supported_efforts` (translated) |
| R2 | The chat reasoning-level control offers exactly that ladder for an `openrouter:` conversation | Composer shows the stored levels; a model with no ladder shows no control |
| R3 | A chosen level reaches the wire as `reasoning.effort`, nothing else | Outgoing payload asserts `reasoning.effort` present, `reasoning.enabled`/`reasoning.max_tokens`/`reasoning.exclude` absent, no `reasoning_effort` key |
| R4 | A level the stored ladder does not offer is never sent | Conversation write rejected 400 `code:"invalid_reasoning_level"`; a run whose ladder lost the level proceeds with `reasoning_level_note` |
| R5 | Local services are provably unchanged | Local payload assertions in `tests/test_reasoning_level_payload.py` pass unmodified (its OpenRouter cases are new, not edited); no local payload gains a `reasoning` key |
| R6 | Stored ladders survive shortlist edits made by clients that do not know the field | PUT carrying plain `{id,label}` for an id that already has a ladder preserves the ladder |
| R7 | `off` is offered only where OpenRouter says reasoning can be switched off | Ladder contains `off` iff upstream listed `none` and `mandatory` is not true; `off` goes out as `effort:"none"` |
| R8 | A stored ladder can be re-derived without re-adding the model | `POST …/openrouter-models/refresh` with `{ids}` updates those entries only, and a save is not required to pick it up |

**Non-goals.** Token budgets (`reasoning.max_tokens`), `reasoning.exclude`,
per-provider ladder selection, persisting `reasoning_details` for round-trip (§6),
Android UI (excluded with evidence below), annotating all 20 built-in
`DEFAULT_MODELS`, and any change to how local engines map levels.

## 2. Verified current behavior

Baseline: `feat/android-reasoning-level-f15` @ `5367504`, clean tree, 2026-09-11.
Probes run against live OpenRouter with the key in `dashboard/.env`. Baseline suites
were run green by the reviewer: `test_reasoning_levels`, `test_settings_store`,
`test_openrouter_catalog`, `test_reasoning_level_payload` → 132 passed;
`test_openrouter_routes`, `test_service_reasoning_levels`,
`test_chat_reasoning_levels` → 108 passed; `vitest ReasoningLevelSelect.test.jsx
OpenRouterModelsPicker.test.jsx` → 66 passed.

| Claim | Evidence |
|---|---|
| An `openrouter:` resolution carries no engine and no ladder | `chat/openrouter.py:resolve` returns `{base_url, api_key, model, extra_headers}`; asserted **field-for-field** by `tests/test_openrouter_routes.py:470-477` |
| Therefore no reasoning field is ever added | `chat/llm_proxy.py:342-345` → `request_fields(level, svc.get("template_type"))` with `template_type` absent → `reasoning_levels.py:request_fields` falls through to `{}` |
| The payload re-checks the ladder, so **both** fields are needed | `llm_proxy.py:343` `find_level(svc.get("reasoning_levels"), reasoning_level)` — a `template_type` with no ladder still yields `{}`. This is the failure AGENTS records ("template_type must stay on the service payload") |
| Enforcement point 1 refuses OR outright | `chat/routes.py:_service_reasoning_levels` returns `[]` for any OR name before the lookup (`:91-101`) |
| Enforcement point 2 is ladder-driven, needs no change | `chat/routes.py:_effective_reasoning_level` (`:136`) + `routes.py:746` |
| **A new entry key is dropped on write** | `chat/settings_store.py:178-182` `_normalize_openrouter_models` rebuilds every entry as `{id, label}` — reproduced live: raw store shows `{id,label}` only |
| A stored list is **not** invalidated by the extra key | *corrected.* `_valid_openrouter_models` (`:158-175`) checks only that `id` is a non-blank string, `label` is a string when present, and ids are unique. An entry carrying `reasoning_levels` returns `True`. The drop is the whole problem; the silent fallback to built-in is reachable only through a *malformed* value, which step 3 prevents |
| PUT replaces the whole list | `chat/routes.py:271-283`; `useOpenRouterModels.save` passes the editor's draft straight through |
| **`reasoning` is already a catalogue field — a boolean** | *corrected.* `chat/openrouter_catalog.py:235` emits `"reasoning": "reasoning" in params` beside `tools`/`structured_outputs`; asserted at `tests/test_openrouter_catalog.py:331`; rendered as a tag at `OpenRouterModelsPicker.jsx:232`. `supported_parameters` is consumed into these flags, not kept |
| Streaming needs **no** adapter | `chat/llm_proxy.py:396` already reads `delta.get("reasoning_content") or delta.get("reasoning")` |
| Android tolerates the new key | `android/.../core/net/ApiJson.kt:10` `ignoreUnknownKeys = true`; `OpenRouterModelDto` carries `id`/`label` only |
| `settings_store` already imports `openrouter` | `settings_store.py:33` `from .openrouter import DEFAULT_MODELS …` at module level, so the reverse import must be deferred |
| The picker's draft cannot carry a new field | *found in review.* `OpenRouterModelsPicker.jsx:88` `clone = models => models.map(m => ({id, label}))`; `dirty` (`:340`) compares `modelsToJson(draft)` against a baseline built from `data.current` (`:345`) |

### Upstream facts (probe run 2026-09-11, `GET /api/v1/models`, `POST /chat/completions`)

Accepted efforts: `max | xhigh | high | medium | low | minimal | none`.

```
openai/gpt-5.5             supported_efforts ["xhigh","high","medium","low","none"] default "medium" mandatory false
anthropic/claude-sonnet-5  supported_efforts ["max","xhigh","high","medium","low"]  default "high"   mandatory false
google/gemini-3.5-flash    supported_efforts ["high","medium","low","minimal"]      default "medium" mandatory TRUE
anthropic/claude-haiku-4.5 {"mandatory":false}                    ← no effort selection exposed
```

309 entries carry `reasoning`; 166 publish `supported_efforts`; 103 are `mandatory`;
**123** have `default_enabled: true`. All 6 `openrouter/*` pseudo-router rows carry no
`reasoning` object. Failure is loud and informative:

| probe | result |
|---|---|
| `effort:"xhigh-ish"` | 400 `reasoning.effort: Invalid option: expected one of "max"\|"xhigh"\|…` |
| `effort:"none"` on mandatory `gemini-3.5-flash` | 400 `Reasoning is mandatory for this endpoint and cannot be disabled.` |
| `effort:"low"` on `claude-sonnet-5`, `effort:"high"` on `claude-opus-4.8` | 200 — one wire format covers all vendors |
| `effort:"xhigh"` on `openai/gpt-5.5` | 200, `usage.completion_tokens_details.reasoning_tokens: 14` |
| `effort:"off"` on `x-ai/grok-4.5` | 400 — the stored id `off` must be translated, never forwarded |

Grammar headroom, measured against today's catalogue: longest ladder 6 tokens vs
`MAX_LEVELS` 8, longest joined 33 chars vs 120, every token matches `LEVEL_NAME_RE`,
and no upstream token is `off`, so no duplicate collision. The mapping is safe today
and needs a fallback for tomorrow (§3.2).

**Unknown (not established by any probe):** whether an endpoint whose per-provider
`supported_parameters` omits `reasoning` rejects the field.

## 3. Design and contracts

### 3.1 Representation

One field on the shortlist entry, in the grammar services.json already uses:

```json
{ "id": "openai/gpt-5.5", "label": "GPT-5.5", "reasoning_levels": "off,low,medium,high,xhigh" }
```

Derived from the §2 row above: reverse upstream's descending order, translate
`none`→`off`, and **place `off` first**, matching the local declaration order AGENTS
already shows (`"off,low,medium,xhigh"`) so the sheet reads least→most in both cases.

Chosen over a separate `openrouter_reasoning` map because it keeps one concept in one
place and lets `parse_levels` / `find_level` / `format_levels` be reused with no new
grammar.

| Case | Meaning |
|---|---|
| key absent | No effort selection published, capture failed, or added before this feature → **no control**, nothing on the wire (today's behavior) |
| `""` | Same as absent. There is no distinct "cleared" state, because the field is server-owned (§3.2) and cannot be authored by a client |
| non-conforming upstream token | Dropped at derivation with a warning log; never stored, never a failed save |
| ordering | `off` first, then ascending effort |
| `off` | llm-dock's reserved id, stored, mapped to `effort:"none"` at the wire. Never stored as `none` |
| `mandatory: true` | `off` withheld (R7). `NULL` still means "send nothing", which such models answer by reasoning anyway |

### 3.2 Capability source, and who owns the value

`openrouter_catalog.py` already parses the upstream entry into flags. **It must gain a
second, distinct key** — proposed `reasoning_meta` — holding the raw upstream object,
because `reasoning` is taken (`:235`, boolean, green-tested, rendered) and step 1 must
not change its type or the tag's meaning on the 7 ids where the flag and the object
disagree (`openrouter/auto-beta`, `rekaai/reka-edge`, `openrouter/free`,
`qwen/qwen3-max`, `qwen/qwen3-coder-plus`, … measured). A pure
`ladder_from_reasoning(meta) -> str` derives the declaration.

**The field is server-owned.** The PUT body cannot set it, for three reasons that
came out of review: the picker's `clone` cannot carry it (so a body value would be
client-fabricated), an accepted body value contradicts any claim that clients cannot
forge a ladder, and grammar rejection of an authored string would fail an unrelated
shortlist save. So:

- `routes.put_openrouter_models_setting` **derives** for an id in the body that is not
  already stored, by looking the model up in the catalogue payload and passing
  `ladder_from_reasoning(...)` down. It is the only reader of the catalogue on this
  path, so an outage degrades to "no ladder" rather than to a failed save (R1, §6).
- `routes.refresh_openrouter_ladders` (new, R8) re-derives named ids on demand —
  the only way an already-customized list ever acquires or updates ladders, since
  derivation fires for new ids only and the merge preserves existing ones.
- `settings_store.set_openrouter_models` **merges** and does no catalogue or network
  read: an id already stored keeps its `reasoning_levels` unless the caller (server
  code, not a client) supplies one. Clients cannot clobber (R6).
- `ladder_from_reasoning` drops tokens failing `LEVEL_NAME_RE` or exceeding
  `MAX_LEVELS` rather than raising, so an upstream vocabulary change cannot make the
  shortlist unsaveable. `validate_levels` stays strict on the operator-authored
  `services.json` path, untouched.

`is_openrouter_models_customized` must compare **ids only**. It compares against
`DEFAULT_OPENROUTER_MODELS` wholesale today, so once entries carry a derived field a
list identical to the built-in would read as "customized" forever.

One reader for both enforcement points — `ladder_for_model(model_id)` in
`chat/openrouter.py`, called by `routes._service_reasoning_levels` and by
`llm_proxy.resolve_service` — because the invariant that makes today's design safe
("the ladder offered and the ladder enforced cannot drift", `routes.py:91`) is
mechanical only if both read the same function. It imports `settings_store`
**deferred inside the function** (`settings_store.py:33` already imports `openrouter`
at module level; a module-level back-import is a circular ImportError in either
order — reproduced), matching the existing pattern at `llm_proxy.py:92,95`.
`openrouter.resolve()` stays a bare connection dict; `resolve_service` decorates it.

### 3.3 Wire mapping

```python
ENGINE_OPENROUTER = "openrouter"
if engine == ENGINE_OPENROUTER:
    return {"reasoning": {"effort": "none" if level_id == OFF_LEVEL else level_id}}
```

`reasoning` is the only key added to an OR payload; `payload["model"]`
(`llm_proxy.py:323-326`) is untouched. Because `resolve_service` supplies
`reasoning_levels`, the `find_level` guard at `llm_proxy.py:343` still governs — an id
absent from the stored ladder cannot reach the wire even if a caller bypasses the
route checks.

### 3.4 State and visibility

- Selected level survives a ladder refresh until it stops being offered, then the
  existing machinery speaks: `run_started` carries `reasoning_level_note`, `ChatArea`
  renders it, `ReasoningLevelSelect` shows the value stale and clearable. Nothing new.
- Removing a model from the shortlist drops its ladder. A conversation still pinned to
  it hits the "no longer offered" path. `conversations.reasoning_level` is never
  rewritten — the documented local rule.
- Refresh is metadata-only: writes `chat_settings.json` atomically as the rest of the
  store does; builds no compose, touches no container.
- The picker's dirty check must treat the server-owned field as non-editable, or every
  enriched list reads "Unsaved" permanently (§4 step 8).

## 4. Implementation sequence

| Step | Requirements | Files and symbols | Behavior | Depends on |
|---|---|---|---|---|
| 1 | R1 | `chat/openrouter_catalog.py` normalizer, `_normalize_endpoints` untouched | Add `reasoning_meta` (sanitized upstream dict, `None` when absent/non-dict) beside the existing boolean `reasoning` at `:235`; do **not** change `reasoning`, `tools` or `structured_outputs`; extend `tests/test_openrouter_catalog.py` rather than editing `:331` | — |
| 2 | R1,R7 | `chat/openrouter.py`: `ladder_from_reasoning`, `ladder_for_model` | Pure derivation: `off` first, rest ascending, `none`→`off`, `off` withheld when unlisted or `mandatory`, `""` when no `supported_efforts`, non-conforming tokens dropped with a log. `ladder_for_model` reads the store through a **deferred** `from . import settings_store` | 1 |
| 3 | R1,R6 | `chat/settings_store.py` `_valid_openrouter_models`, `_normalize_openrouter_models`, `set_openrouter_models`, `is_openrouter_models_customized` | Carry the optional string through `normalize` instead of dropping it; keep the read tolerant (bad stored value → treated as absent, like `parse_levels`), merge by id, no catalogue access; `customized` compares ids only | 2 |
| 4 | R2,R4 | `chat/routes.py:_service_reasoning_levels` | Replace the OR `return []` with `parse_levels(ladder_for_model(...))` | 2,3 |
| 5 | R3,R5 | `chat/llm_proxy.py:resolve_service`, `dashboard/reasoning_levels.py:request_fields` | OR branch attaches `template_type="openrouter"` + `reasoning_levels`; new engine branch returns `{"reasoning":{"effort":…}}`. **Also update:** `tests/test_openrouter_routes.py:470-477` (asserts the resolution dict field-for-field), `tests/test_service_reasoning_levels.py:387` `test_openrouter_resolution_carries_no_engine_fields` (asserts the retired invariant and will pass vacuously — delete or invert), and the now-false docstrings at `llm_proxy.py:86-90` and `routes.py:96-98` | 2,3 |
| 6 | R1 | `chat/routes.py:put_openrouter_models_setting` | Derive for newly appearing ids; report per-id capture outcome in the response so the UI can badge "no ladder" | 1-3 |
| 7 | R8 | `chat/routes.py`: new `POST /api/chat/settings/openrouter-models/refresh`, body `{ids: []}` | Re-derive the named ids from the catalogue, merge, return `_openrouter_settings_payload()`. Unknown ids reported in `missing`, not fatal. Route is what makes §6's staleness mitigation real | 2,3,6 |
| 8 | R2 | React `hooks/useOpenRouterModels.js`, `components/chat/ReasoningLevelSelect.jsx:66` | Offer the OR list as a second ladder source beside `useServicesSSE`. Expose the ladder **parsed** (`[{id, effort}]`) in `_openrouter_settings_payload` so one component handles one shape instead of branching on string-vs-list | 4 |
| 9 | R1,R8,R6 | React `components/settings/OpenRouterModelsPicker.jsx` | Carry the field through `clone` (`:88`) so the draft round-trips and `dirty` (`:340`) stays honest; show the ladder per row; badge "no ladder"; per-row **Refresh ladder** calling step 7; update the stale comment at `:22-24` | 6,7,8 |
| 10 | R1-R8 | `AGENTS.md`, this file | Document the third engine, the storage field and its server-ownership, the refresh endpoint, the `off` rule | 1-9 |

Steps 1-5 are the complete backend and ship dark: after 5 an `openrouter:`
conversation with a stored ladder sends the field, and the composer has no control
until 8. Note that steps 3+6 alone give ladders to **newly added** models only —
step 7 is what lets an existing shortlist ever get them, so 7 is not optional polish.

## 5. Verification

**Checks already run** (2026-09-11): the catalogue counts, per-model ladders and the
five completion probes in §2 (reviewer reproduced the counts and ladders
independently); the store's drop-on-write behaviour; the circular-import claim; the
four baseline suites above. Nothing below is a re-run of those.

| # | Requirement | Test | Observable expectation |
|---|---|---|---|
| T1 | R1,R7 | `tests/test_reasoning_levels.py` (extend) | `ladder_from_reasoning`: the four §2 rows produce exactly `"off,low,medium,high,xhigh"`, `"low,medium,high,xhigh"`(sonnet-5, no `off`), `"low,medium,minimal,high"`→ ordered per rule with no `off` (mandatory), `""`; non-dict → `""`; unknown token dropped not stored; >8 tokens truncated not raised |
| T2 | R1,R6 | `tests/test_settings_store.py` | `set→get` keeps the key; an entry without it preserves the stored ladder; a body-supplied value for an existing id is ignored; a *malformed stored* value degrades to absent on read without invalidating the list; `customized` stays false when only the derived field differs from built-in |
| T3 | R1 | `tests/test_openrouter_settings.py` | PUT of a new id whose catalogue row has `supported_efforts` returns that entry with `reasoning_levels`; a catalogue outage returns the entry without it and the save still succeeds |
| T4 | R8 | same file | `POST …/refresh {ids:[one known, one unknown]}` → known id's ladder re-derived, unknown named in `missing`, other entries byte-identical, `dirty`-free payload returned |
| T5 | R2 | `tests/test_chat_reasoning_levels.py` | Create conversation with an offered level → ok; with an unoffered one → 400 + `code:"invalid_reasoning_level"`; ladder absent → same 400 |
| T6 | R4 | same file | Level stored, ladder later re-derived without it → run proceeds, `run_started` carries `reasoning_level_note`, no reasoning field in the sent payload |
| T7 | R3,R5 | `tests/test_reasoning_level_payload.py` (extend) | Build through the **real** `resolve_service` for `openrouter:openai/gpt-5.5` + `low`: `payload["reasoning"]["effort"]=="low"`, no `reasoning_effort`, no `enabled`/`max_tokens`/`exclude`; `off` → `"none"`. Assert a local llama.cpp payload is byte-identical to before. Must **not** monkeypatch `resolve_service` — `:147-155` does, which is exactly the hand-written-dict blind spot AGENTS records |
| T8 | R3 | `tests/test_openrouter_routes.py` | A stored ladder naming an effort OpenRouter rejects surfaces the 400 rather than dropping silently |
| T9 | R2 | `ReasoningLevelSelect.test.jsx` | OR conversation shows stored levels; non-OR unaffected; a model without a ladder renders nothing |
| T10 | R1,R6 | `OpenRouterModelsPicker.test.jsx` | Row shows the ladder and refresh; after a refresh the picker is **not** dirty; unsaved edits survive a refresh; a reordered save keeps ladders |
| P0 | §6 limitation | bounded live probe, manual | Two-turn tool-using call on `openai/gpt-5.5` at `xhigh`, second turn omitting `reasoning_details`. **Paid**, ~2 calls. Diagnostic only — not a release gate (§6) |

## 6. Rollout and risks

Enablement is per-model and implicit: a model with no `reasoning_levels` behaves
exactly as it does today, so steps 1-5 ship dark. Roll back by reverting the
`request_fields` branch — a stored key nothing reads is inert, older code drops it on
write, so there is no destructive migration and no data-recovery plan to write.

| Risk | Mitigation |
|---|---|
| Ladder goes stale as upstream changes a model | Step 7 refresh endpoint + step 9 per-row action. The 400 body names the accepted set, so a failed run can report the actual current ladder rather than guessing |
| A shortlist customized before this feature has no ladders at all | Expected, and the reason step 7 is load-bearing rather than optional: derivation fires only for new ids |
| Catalogue unavailable at add time | Entry stored without a ladder, control absent, save succeeds. A network value never blocks a save, because derivation drops non-conforming tokens instead of raising |
| Upstream adds an effort token outside `LEVEL_NAME_RE`, or a 9th level | Dropped at derivation with a log; save unaffected. Today's headroom (6/8 tokens, 33/120 chars) is measured, not assumed |
| Mandatory model, user expects "off" | `off` withheld (R7); the ladder shown is the ladder upstream gives, so the absence is visible rather than mysterious |
| Pseudo-routers | No special case needed or possible: all 6 `openrouter/*` rows carry no `reasoning` object, so derivation yields `""` on its own (verified live). `ladder_from_reasoning` receives no id and takes no flag |
| `reasoning_details` is not round-tripped | **Pre-existing, not introduced here.** llm-dock never sends it, and 123 models ship `default_enabled: true`, so multi-turn OpenRouter already exercises this path today with no ladder in play. Recorded as a known limitation; P0 characterises it. If P0 shows breakage attributable to *our* omission, the fix is a per-message column and a new phase — not an expansion of step 3 |
| An endpoint without `reasoning` in `supported_parameters` rejects the field | Unknown (§2). llm-dock pins no provider, so the gateway chooses; the cached endpoints payload is where to look if a 400 appears in the field |
| Reasoning costs more, silently | Out of scope. `usage` reports `completion_tokens_details.reasoning_tokens`; the ladder row is the natural place for a cost hint later |
| Android client | Excluded and proven harmless: `ApiJson.kt:10` ignores unknown keys. The phone will not show OR levels until F15's plumbing learns about the settings endpoint — deliberate, the app's chat scope is documented as local-model-centric |

## 7. Readiness

**Ready for implementation.** Contracts, owners and paths are specified; no step
depends on a later step's helper or storage shape; steps 1-5 are shippable and dark;
R8's endpoint is now an owned step rather than a UI affordance pointing at nothing.

Two labeled recommendations a reviewer may wish to overrule, neither blocking: keep
the field server-owned (§3.2) rather than accepting client-supplied ladders, and
expose ladders parsed in the settings payload (step 8) rather than as a raw string.

P0 is a diagnostic, not a gate: the breakage it probes is already reachable on
today's code, so a failure neither blocks nor reshapes steps 1-10 — it adds a phase.

## 8. Implementation record

Shipped on `feat/openrouter-reasoning-levels` off `main` @ `51a39e9`. Steps 1-10 all
landed. Verification at commit time: pytest `1009 passed`, vitest `471 passed`,
`ruff check` clean on every changed Python file, `eslint` 0 errors.

Five places where the build differs from the steps above, each on purpose:

| Planned | Built | Why |
|---|---|---|
| Step 2: reverse upstream's descending effort list | Sort by an explicit rank table | A reversal silently mis-orders the ladder the moment upstream returns something unsorted or adds a token; a rank puts an unknown effort last instead of mid-ladder |
| Step 9: carry `reasoning_levels` through the picker's `clone` | `clone` unchanged; the dirty check and JSON panel compare the **editable projection** | Carrying the field makes a ladder a thing the editor can orphan by deleting it. Comparing only what the editor can change keeps `dirty` honest and keeps the ladder out of the JSON escape hatch, where an edit to it would be a no-op |
| Step 7/9: refresh response applied via `applyPayload` | Refresh bypasses `applyPayload`; the hook's own state update drives display | `applyPayload` overwrites the draft, so refreshing a ladder would discard an unsaved rename or reorder |
| T1 in `test_reasoning_levels.py` | T1 in `test_openrouter_settings.py` | The function lives in `chat/openrouter.py`; the file that already imports that module is its home |
| Step 9: "Refresh ladder" row button | `aria-label="Re-read reasoning levels for <id>"` | "Refresh…" collided with the header's Refresh button and broke `getByRole` in an existing test; the new wording is also more accurate |

**Not done: P0.** The two-turn probe needs paid OpenRouter calls, which were not
authorized for this work. Everything else in §7 stands, and the limitation P0
characterises is pre-existing (§6) rather than introduced here, so nothing is gated on
it — but multi-turn continuity on models returning encrypted reasoning remains
**unverified**, not verified-and-fine.

Naming: `reasoning_meta` was the proposed alternative in §3.2 and is what shipped,
after `openrouter_catalog.py:235` was confirmed to occupy `reasoning` with a boolean.
