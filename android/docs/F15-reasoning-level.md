# F15 · Per-conversation reasoning level

**Mockup:** none (post-mockup feature) · **Depends on:** F03, F04, F07

A thread whose model declares reasoning levels shows which one it is using,
and lets the user pick another or hand the decision back to the model.

The ladder is the **operator's declaration about one model**, not an LLM-Dock
notion of "how much to think": what a level token means is a property of that
model's chat template, and an undeclared token can make llama.cpp answer HTTP
500 (`docs/reasoning-level-sweep-qwen3.8-27b.md`). So the app never invents,
reorders, renames or completes a ladder — it shows exactly what the server
reports for the thread's service. Nothing here is a token budget either; the
server rejects `name:budget` syntax outright.

The backend shipped in PR #128. This feature is client-only.

---

## F15-R1 · The ladder comes from the server, verbatim (Must)

`GET /api/services` reports `reasoning_levels` per service as
`[{"id": "low", "effort": "low"}, …]`, in declaration order, `[]` when the
service declares none. The phone keeps that order and adds nothing; only `id`
is used (`effort` is the request-side token, set equal to `id` server-side).

The ladder is read off the **service payload**, never off
`GET /api/services/<name>`'s raw config string: that would mean a Kotlin copy
of the server's grammar, which can then disagree with the point where the level
is actually enforced. The server already collapses an invalid declaration to
`[]`, so the client needs no parser.

It is keyed by service name (`laddersByService`) and resolved against the
thread's current `main_service` rather than copied once at load: switching
models refetches the conversation, not the services, so a copied value would
keep describing the service the user just left.

**Acceptance criteria**

- [x] The options offered are exactly the server's list, in its order, for a
      service whose declaration is e.g. `off,low,medium,xhigh`.
- [x] Nothing is inserted because a neighbour exists: no "high" on a model that
      declares `off,low,medium,xhigh`.
- [ ] A service that is stopped still shows its ladder (the server resolves the
      declaration regardless of container state).
- [x] Switching the thread's model re-resolves the ladder with no second
      `GET /api/services`.

## F15-R2 · One control, showing the current level and every option (Must)

A chip in the thread header's model row shows the current level id, or
`default`. Tapping it opens a sheet: **"Model default"** first (clears the
choice, so nothing is said to the model), then each declared level in order.
Selecting "Model default" sends `null`, not `"off"` — those are different
instructions. The sheet dismisses on **write success**, not on tap, so
choosing and then immediately sending cannot use the old level.

**Acceptance criteria**

- [x] Option rows are "Model default" + the declared levels, in declaration
      order, with the current value checked.
- [x] Picking a level, then reopening the sheet, shows it selected.
- [x] Picking "Model default" on a thread that had a level leaves the chip
      reading `default` after a reload — i.e. the clear really reached the
      server, and was not a 200-no-op.
- [x] The chip is dimmed while the write is in flight and the sheet stays open
      until it lands.

## F15-R3 · No ladder means no control; a stranded level means a visible one (Must)

No ladder and nothing stored → the chip is not composed at all. A stored level
whose service no longer declares it → the chip **shows**, in the warning colour,
labelled "not offered by this model" in the sheet, where the only thing it can
be used for is clearing itself or picking something else. A stored level must
never become invisible, because invisible state that the server still holds is
the failure this feature can least afford.

**Acceptance criteria**

- [x] A thread on a service with no ladder shows no chip.
- [x] A thread whose level was removed from its service's ladder shows a
      warning-coloured chip, and the sheet labels that row "not offered by this
      model".
- [x] Clearing it returns the chip to `default`.
- [x] The server never receives a level it does not offer, so the stranded
      value is inert (R6 reports it on the turn).

## F15-R4 · The choice is server state (Must)

Written with `PUT /api/chat/conversations/<id>` `{"reasoning_level": <id>}`,
cleared with an explicit `{"reasoning_level": null}`. Because this client's JSON
encoder omits nulls, the clear cannot go through a serialized data class — the
body is built as a `JsonObject` so the null is actually on the wire. Visible in
the web UI on the same thread, survives app restart and thread re-open.

**Acceptance criteria**

- [x] Choose a level on the phone, open the same thread in the web UI: the
      composer's level control shows the same value.
- [x] Force-stop and relaunch the app on the same thread: the chip still reads
      the chosen level.
- [x] The clear case sends `"reasoning_level":null` on the wire (pinned by an
      exact-body test, since a missing key answers 200 and changes nothing).

## F15-R5 · A ladder edit reaches an open thread (Must)

No permanent `GET /api/services/stream` subscription for a thread's lifetime (see
*Deviations*). Two cheap refreshes cover it: the ladder snapshot is refetched
when the level sheet opens, and the model picker's live stream — which the
thread already holds while that sheet is up — updates it too. Any thread reload
or re-open lands a fresh snapshot as well.

A stale ladder is never dangerous, only briefly inaccurate: the server
re-checks the level at run creation (R6), which is the backstop that makes this
trade-off acceptable.

**Acceptance criteria**

- [x] Edit the ladder on the dashboard, reopen the sheet on an already-open
      thread: the new ladder, without an app update.
- [x] With the model picker open, a ladder edit lands without closing and
      reopening anything.

## F15-R6 · A dropped level is reported (Must)

A level the server drops for a run — the ladder lost it between the write and
the turn — arrives as `reasoning_level_note` on the `run_started` frame, and is
shown above the composer rather than looking like a model that declined to
think. The note exists only on the send path; a reattaching client gets a plain
`run_started` (`chat/run_manager.py:observe`), and the F09 accumulator is rebuilt
per attempt, so it is lost across a reconnect. The always-available equivalent
is R3's stale chip, which is why that state is a requirement and not polish.

**Acceptance criteria**

- [x] Send with a level the service no longer offers: a one-line notice appears
      above the composer naming the level and saying it was ignored.
- [x] A `run_started` frame with no note shows nothing (and an unknown extra key
      on the frame still parses).

## F15-R7 · A failed write is shown and undone (Must)

Optimistic like the prompt and tool rows, with F00-R4's rule that nothing may
fail silently. Writes are ordered by one mutex — the same discipline as
`toolsWriteLock` — and only the **newest** write's failure reverts, so a
superseded write coming back late cannot overwrite the choice that replaced it.

**Acceptance criteria**

- [x] With the write failing, the chip returns to the server's value and an
      error surfaces.
- [x] Two taps in quick succession, the first one failing, leave the second
      choice in place.
- [x] Choosing a level while a run is active is refused client-side, no request
      sent — the turn in flight already read the previous value (same rule as
      `canSwitchModel`/`canToggleTools`).

## F15-R8 · OpenRouter and ladder-less services are provably untouched (Must)

OpenRouter threads never show the control — the server resolves no ladder for an
`openrouter:` service and rejects any level written to one, so an OpenRouter
conversation can never hold one either. And the app never sends a reasoning
field anywhere: the level lives on the conversation, and mapping it into the
model request is server-side per engine (`dashboard/reasoning_levels.py`), which
is why `ik_llamacpp`, `tabbyapi`, `ds4` and OpenRouter send nothing.

**Acceptance criteria**

- [x] No chip on an OpenRouter thread, whatever the payload contains.
- [ ] One turn on a no-ladder service, with the request observed at the model:
      no `reasoning_effort`, no `chat_template_kwargs`. Absence is the point —
      90 % of services must see a byte-identical request to before this feature.

---

## Deviations

- **Placement: the thread header, not the composer.** The web client puts the
  selector in the composer's control rail (`ReasoningLevelSelect.jsx`). The
  phone's composer row already holds attach + field + send on a 411 dp screen,
  and a fourth element competes with the text field at exactly the viewport that
  can least afford it. The header already carries the other fact that jointly
  determines an answer — the model name, kept visible for the whole turn per
  F04-R3 — so the two sit side by side, and the control stays one tap instead of
  three. Parity with web is behavioural (same options, same meaning, same
  staleness rules), not positional.
- **Not in the settings sheet.** That sheet holds durable per-thread settings
  (prompt, tools, text size); which rung the *next answer* uses is turn-adjacent
  state, and duplicating the control would give one value two sources of truth.
- **`GET /api/services` is fetched per thread load and per sheet open** rather
  than kept on a live subscription for the thread's lifetime — a departure from
  F00-R12 (Should), taken because a thread screen stays open indefinitely and one
  rarely-read field does not justify a held connection. The model picker already
  sets the precedent of scoping that stream to a sheet's visible lifetime
  (`ThreadViewModel.openModelPicker`), and R6 is the backstop.
- **No level in the new-chat sheet.** Web offers it in the empty-state composer
  and carries it onto `POST /api/chat/conversations`. The phone's new-chat sheet
  is a modal whose create path already has one follow-up PUT with its own
  failure mode (F03's tools write and "open anyway"). The cost is one extra trip;
  no data is lost. If wanted later, the clean shape is
  `CreateConversationRequestDto.reasoningLevel: String?` — omitted when null,
  which the server reads as "no level" — not a post-create PUT.

- **The ladder is stored as a whole snapshot keyed by service name, not as one
  materialised list** (`Loaded.laddersByService`, with `ladder` derived).
  F15-R1's switch criterion forces it: switching models refetches the
  conversation and nothing else, so any value materialised for one service is
  stale the moment the header reads it for another — silently, on the one
  service where levels are the difference between a thinking and a silent
  answer.
- **The dropped-level notice lives on the screen state, not on the streaming
  turn** — changed during the device pass. The first implementation put it on
  `StreamingTurn`; a turn is discarded at its terminal and refetched, which made
  the notice readable only while the answer happened to be streaming. It is now
  cleared by the next send, like the web client's `runNotice`.
- **A stale stored level appears in the sheet without the selected marker**, since
  the marker means "this request was honoured" and it wasn't. The chip carries
  the value; the row's label says it is not offered.

## Out of scope

- Editing a service's ladder from the phone (F00-R10 — the app never writes
  configuration).
- Token budgets. `validate_levels` rejects `name:budget` syntax today precisely
  so that adding it later is additive rather than silently truncating `low:512`.
- Level display in the conversation list, or in the Models tab beyond a
  read-only row on the detail screen (the plan's optional P5, not taken here).

## Verification notes

Device: `emulator-5554` (Pixel 10, API 37), `./scripts/dev.sh install`, against
the live dashboard. One service declares a ladder today —
`vllm-qwen3-8-flash-next-mixed-nvfp4-fp8` with `off,low,medium,xhigh` — and
conversations on it already carried levels from earlier web use, so this ran
against real state rather than seeded fixtures. Screenshots:
`f15-02-thread`, `f15-03-sheet`, `f15-04-chip-off`, `f15-06-stale-sheet`,
`f15-07-notice`/`f15-09-notice-after`, `f15-10-cleared`, `f15-11-no-ladder`,
`f15-12-openrouter`.

| Criterion | How verified |
|---|---|
| R1 verbatim + order | device — the sheet listed exactly `off, low, medium, xhigh` in the server's order, nothing else (the thread already held `medium`, and the sheet marked it selected) |
| R1 stopped service | not exercised — see Outstanding |
| R1 switch, no second fetch | unit (`T8`: one `GET /api/services` for load + switch) |
| R2 options, select, clear, close-on-write | device — chip → sheet → tap `off` → sheet closed, chip read `off`; reopening marked it selected. Dimming while in flight is by inspection (`writePending`) |
| R3 no ladder → no control | device — a `llamacpp-glm-5.3-flash-q2kxl` thread has no `thread_reasoning_chip` node at all |
| R3 stale → warning + label | device — with the dashboard ladder edited down mid-session, the chip went amber and the sheet showed the shortened ladder with `xhigh` last, labelled "not offered by this model" |
| R4 phone → server, survives relaunch | device — after each tap the conversation's `reasoning_level` read back from the API matched the chip exactly (which is what the web picker renders), and after `am force-stop` + relaunch the chip still read `xhigh`. The explicit null is unit (`T4`) — a regression there is silent and looks like a working clear |
| R5 ladder edit reaches an open thread | device for the sheet-open half (no app restart, ladder shortened from the dashboard); unit (`T11`) for the `metadata-changed` delta through the mapper |
| R6 notice | device — with the level unoffered the turn ran and the row above the composer read the server's wording verbatim: "Reasoning level 'xhigh' is not offered by this model and was ignored"; a plain `run_started` shows nothing (unit, `T9`) |
| R7 revert, ordering, refusal | unit (`T10`, three cases — all red before the mutex landed) |
| R8 OpenRouter | device — an OpenRouter thread (`z-ai/glm-5.3-flash`) has no chip node |

What the pass caught, that unit tests could not have:

1. **The chip would have gone stale after a model switch.** The first pass kept
   the ladder in one list materialised at thread load, because the header read
   `state.ladder`. Switching services refetches the conversation and nothing
   else. Caught in review before device work; `laddersByService` + `T8` are the
   fix.
2. **A malformed ladder entry could have frozen the whole service snapshot, not
   just the picker.** `ServiceDto` is typed, so a `List<String>` field receiving
   `"junk"` throws at *decode* — which for a snapshot frame means the frame is
   dropped, and `ServicesStreamRepository` deliberately does not restart the
   stream on decode failure. One malformed entry on one unrelated service and
   `running` would stop updating for the whole app. The wire type is
   `JsonElement?` with tolerant parsing (`T1`), the same shape as
   `ServiceConfigDto.params`.
3. **A notice attached to the streaming turn is invisible in practice** — see
   Deviations. Capture `f15-07` showed a completed turn with no notice at all;
   hoisting it produced `f15-09`.

### Outstanding — not exercised on device

| Feature | Requirement | Why outstanding |
|---------|-------------|-----------------|
| F15 | R1's stopped-service half | Checking it means stopping a container, which this session's rules forbid; the map is keyed by service name regardless of `running`, and the server resolves the ladder for stopped services too (the web picker reads the unfiltered list for the same reason) |
| F15 | R8's wire-level absence | No proxy in place to capture the outgoing body. The client has no code path that could add a reasoning field: `SendMessageRequestDto` is untouched, and the level is only ever written to the conversation (unit) |
