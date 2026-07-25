# F07 · Model selection

**Mockup:** screen 07a · Model picker · **Depends on:** F01 · **Blocks:** F03

Which model a thread talks to, chosen at creation and changeable mid-thread.

---

## F07-R1 · The list of local models (Must)

From `GET /api/services` (snapshot) and `/api/services/stream` (live).
The picker shows what can actually answer right now.

The web UI's filter, which the phone matches exactly (R-B):

- `status === "running"`, and
- the name starts with `llamacpp-`, `vllm-` or `ds4-`, and
- `kind` is `chat` — embedding services (`--runner pooling`,
  `--embedding`) cannot serve `/v1/chat/completions` and must never
  appear. Treat a missing `kind` as `chat`.

Each entry shows the service name, its engine (from the name prefix) and
its port.

**Acceptance criteria**

- [ ] Only running chat-capable services are selectable.
- [ ] An embedding service never appears, running or not.
- [ ] Starting a container elsewhere makes it appear in an open picker
      without a manual refresh.
- [ ] With nothing running, the picker shows exactly
      `No LLM-Dock models are running at this time.`

## F07-R2 · Stopped models are not shown at all (Must) — *revised*

Stopped containers do **not** appear in the picker. Only what can answer
right now is listed.

This reverses the original requirement, at the owner's direction on
2026-07-25, after using the picker on a real rig: *"only show running
models. don't show grayed out models — that is just noise."* This rig
carries far more stopped services than running ones (typically one
running against half a dozen stopped), so the greyed rows dominated the
sheet while none of them could be tapped.

The original rationale — that a greyed row explains why a favourite is
missing, rather than it just being absent — did not survive contact with
that ratio. Seeing every stopped model is the **Models tab**'s job
(F10/F11), which is where starting one belongs anyway.

Absent is also strictly safer than disabled: an unselectable row cannot
be mis-tapped if it does not exist.

**Acceptance criteria**

- [ ] A stopped service (`exited` or `not-created`) never appears in the
      picker.
- [ ] Filtering is in the picker UI only — `ServicesStreamRepository`,
      `ServiceSummary` and the stream parser still carry stopped services,
      because F10's Models tab needs them.

## F07-R3 · OpenRouter models (Should)

From `GET /api/chat/settings/openrouter-models`, which returns
`{configured, current: [{id, label}], builtin, customized}`. They are
addressed as `openrouter:<model-id>` in `main_service`.

`configured` is false when the server has no `OPENROUTER_API_KEY`. When
false, the group is hidden — exactly as the web picker does.

The list is a picker convenience, not an allowlist: a thread already
using an OpenRouter model that has since been removed from the list keeps
working.

**Acceptance criteria**

- [ ] With a key configured, the curated models appear in their own group.
- [ ] With no key configured, the group is absent — not shown empty or
      erroring.
- [ ] A thread whose `main_service` is an OpenRouter model no longer in
      the curated list still opens, and its model chip shows the id.
- [ ] The app never writes to this endpoint (F00-R10).

## F07-R4 · Switch model mid-thread (Must)

From the thread's overflow menu, the same picker. Selecting a different
model writes `PUT /api/chat/conversations/<id>` with the new
`main_service`. The next turn goes to the new model; existing messages
are untouched and keep their own `model_service`.

**Acceptance criteria**

- [ ] After switching, the next answer comes from the new model and the
      thread header reflects it.
- [ ] Earlier messages still show which model produced them.
- [ ] Switching is unavailable while a run is active.
- [ ] The change is visible in the web UI on that thread.

## F07-R5 · Favourites and ordering (Should)

The services payload carries a `favorite` flag, set on the dashboard.
Favourites sort first in the picker. The phone reads the flag and never
writes it.

**Acceptance criteria**

- [ ] Services flagged favourite on the dashboard appear at the top.
- [ ] No code path calls `/api/services/<name>/favorite`.

## F07-R6 · Never display secrets (Must)

The services payload includes each service's `api_key`. It must never be
rendered anywhere in the app, or written to logs.

**Acceptance criteria**

- [ ] No screen shows an API key.
- [ ] No log line contains one.

---

## Endpoints used

| Method | Path |
|---|---|
| GET | `/api/services` |
| GET | `/api/services/stream` |
| GET | `/api/chat/settings/openrouter-models` |
| PUT | `/api/chat/conversations/<id>` |

## Deviations from the mockup

- **No stopped-models section.** Screen 07a draws stopped services as
  greyed rows beneath the running ones. They are not rendered at all —
  see the revised F07-R2 for why. The mockup is otherwise followed.

## Out of scope

- Editing the curated OpenRouter list (dashboard only).
- Typing an arbitrary `openrouter:` model id by hand. The picker is the
  only path in v1, even though the server would accept any id.

## Verification notes

**Two R1 criteria are outstanding, both needing a container transition
this project's agents are forbidden to make.** Everything else in R1,
R4 and R6 is verified on device; R3 and R5 are verified apart from the
sub-criteria named below.

R2's original criteria were verified on device *before* the requirement
was revised — stopped services did render greyed, inert and with `exited`
distinguishable from `not created`. That evidence is now obsolete: the
revised R2 asserts the opposite, that they do not render at all.

| Outstanding | Why it could not be closed |
|---|---|
| R1 · live add on start elsewhere | No agent may start or stop a container. JVM evidence only: `ServicesStreamRepositoryTest` (merge + reconnect) and `NewChatViewModelTest`'s delta-updates-the-list test. |
| R1 · empty state on screen | `llamacpp-mimo-v2-5-q4` is the rig's only running chat-capable service and cannot be stopped to force the branch. The **string** is unit-tested; how the branch *looks* is not, and cannot be — this project has no Compose UI test infrastructure. |
| R3 · group hidden when unconfigured | Needs a dashboard with no `OPENROUTER_API_KEY`. |

**The empty state matters more since R2 was revised.** With stopped
models no longer listed, a picker with nothing running is now completely
empty apart from the OpenRouter group — so that one string is the entire
local half of the screen. It was a rare corner when stopped rows filled
the sheet; it is the normal appearance of an idle rig now.

**One owner action closes both R1 items:** open the model picker, stop
`llamacpp-mimo-v2-5-q4`, watch the row grey out and the empty state
appear, then start it again and watch it return — all without touching
refresh.

**The engine-prefix filter is load-bearing, not redundant with `kind`.**
`open-webui` is genuinely `running` with `kind: "chat"` on this rig, so
`kind` alone would put Open WebUI in the model picker. `isChatCapable` is
`engine != Engine.UNKNOWN && (kind.isBlank() || kind == "chat")`; the
`Engine.UNKNOWN` half is what excludes it. Verified end to end on device,
and pinned by a named unit test. Do not "simplify" it away.

**`kind` is defaulted, not required.** `isChatCapable` treats blank as
chat, matching the web's `(kind || 'chat') === 'chat'` in
`useRunningServices.js`. An earlier stricter `kind == "chat"` rejected
services whose `kind` the dashboard omits.

**`mergeServiceEvent` ignores a delta naming a service not already in the
list.** Accepted, not a bug: a stopped or `not-created` service is
already in the snapshot, so start/stop deltas update it in place. Only a
service added to `services.json` *after* the snapshot is missed, and the
delta frame carries no `kind`/`host_port`, so a new row could not be
built from it without a refetch. It resolves on the next reconnect.

**The delta frame shape is flat, and `favorite` is nested.**
`dashboard/routes/services.py:services_stream` emits
`{"type":"delta","service_name","status","action","container_id","timestamp"}`
with `favorite` only ever inside an optional `metadata` object — not a
top-level field. Keepalives are `: keepalive` SSE comments, already
dropped by `SseFrameParser`.

**The port field is `host_port`.** `GET /api/services` has no `port` key;
reading one yields null. `services.json` is the opposite shape. See
`android/CLAUDE.md`.
