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
- [ ] With nothing running, the picker says so and points at the Models
      tab.

## F07-R2 · Stopped models are visible but not selectable (Must)

Stopped containers appear greyed, so it is obvious why a favourite is
missing rather than it just being absent.

Whether the picker can start one is F11 — it is the same guarded action,
reached from here.

**Acceptance criteria**

- [ ] A stopped service is listed, visibly disabled, and cannot be chosen
      as a thread's model.
- [ ] Its state (`exited`, `not-created`) is distinguishable from
      `running`.

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

None.

## Out of scope

- Editing the curated OpenRouter list (dashboard only).
- Typing an arbitrary `openrouter:` model id by hand. The picker is the
  only path in v1, even though the server would accept any id.
