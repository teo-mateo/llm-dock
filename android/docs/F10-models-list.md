# F10 · Models tab — list and GPU header

**Mockup:** screen 10a · Models · **Depends on:** F01 · **Blocks:** F11, F12

The second tab. See what is loaded, and what the GPU is doing. This tab
is deliberately not a dashboard: it can start, stop and observe, never
create or edit.

---

## F10-R1 · The service list (Must)

`GET /api/services` for the snapshot, `GET /api/services/stream` to keep
it live. The stream sends a `snapshot` frame on connect and then `delta`
frames as Docker events occur, so the list stays current without polling
(F00-R12).

Each row shows the service name, engine (from the name prefix:
`llamacpp-`, `vllm-`, `ds4-`), host port, model size, and status.

Statuses seen in the payload: `running`, `exited` (with `exit_code`),
`not-created`, and Docker's other container states.

**Acceptance criteria**

- [ ] The list matches the dashboard's service list, same services, same
      statuses.
- [ ] Starting or stopping a container anywhere updates the list within a
      few seconds with no user action.
- [ ] An `exited` service shows that it exited and its exit code.
- [ ] A `not-created` service is distinguishable from a stopped one.
- [ ] Losing the stream falls back to a snapshot fetch and shows a stale
      indicator rather than freezing.

## F10-R2 · Running / stopped split (Must)

Running services are grouped above stopped ones. Within a group, order is
stable — the payload arrives sorted by host port.

**Acceptance criteria**

- [ ] Running services appear first, visually distinct.
- [ ] A service that stops moves to the stopped group without the list
      reordering unpredictably around it.

## F10-R3 · GPU header (Must)

A card at the top, live from `GET /api/gpu/stream` (default 3 s
interval, clamped 0.5–10 s). Available per GPU: total and used memory in
MiB, GPU utilisation percent, temperature, power draw and limit, clocks,
fan and performance state.

Show: VRAM used of total, GPU utilisation, temperature, power draw.

**Acceptance criteria**

- [ ] The header updates continuously while the tab is open.
- [ ] Values match `nvidia-smi` on the host.
- [ ] Closing the tab stops the stream — verified in the dashboard log.
- [ ] With no GPU present or `nvidia-smi` failing, the header shows an
      unavailable state and the service list still works.

## F10-R4 · Per-container VRAM attribution (Should — see caveat)

Screen 10a draws the VRAM bar split into per-container segments.

**The API does not provide this.** `GET /api/gpu` returns whole-device
memory only — the `nvidia-smi` query used carries no per-process
breakdown, and the services payload has no resident-memory field. The
only per-service number available is `model_size` / `model_size_str`,
which is the size of the weights on disk, not resident VRAM.

Two honest options: draw the segments from `model_size` of running
services and label them as estimates, or draw a single total bar. Either
is acceptable; presenting an estimate as measured VRAM is not.

**Acceptance criteria**

- [ ] Whatever is drawn, the screen never implies a measured per-container
      VRAM figure that the API did not supply.
- [ ] The total used/total figure is the real one from `/api/gpu`.

## F10-R5 · Row actions (Must)

Start and stop directly from a row, per F11 — including its confirms and
the VRAM guard. Tapping the row body opens model detail (F11).

**Acceptance criteria**

- [ ] Start and stop are reachable from the row without opening detail.
- [ ] Both go through the same confirmation path as the detail screen.
- [ ] The row shows a pending state while a start or stop is in flight.

## F10-R6 · New chat from a model (Should)

An action on a running service that opens the chat tab with that service
preselected in the new-chat sheet — how this tab actually gets used.

**Acceptance criteria**

- [ ] The action is offered only for running, chat-capable services
      (`kind === "chat"`).
- [ ] It lands on the new-chat sheet with that model already chosen.

## F10-R7 · No secrets, no configuration (Must)

The services payload contains each service's `api_key`. It is never
displayed or logged (F07-R6). Nothing on this tab creates, edits,
renames, deletes or reconfigures a service.

**Acceptance criteria**

- [ ] No API key appears anywhere on the tab.
- [ ] The only mutating calls the tab makes are `.../start` and
      `.../stop`.

---

## Endpoints used

| Method | Path |
|---|---|
| GET | `/api/services` |
| GET | `/api/services/stream` |
| GET | `/api/gpu` |
| GET | `/api/gpu/stream?interval=N` |

## Deviations from the mockup

- **Per-container VRAM segments** — F10-R4 above. Not available from the
  API.
- **Uptime.** Screen 10a shows per-service uptime. The payload carries
  the container's `created` timestamp, not a start time, so "uptime" is
  really "created ago" and will be wrong for a container that was
  restarted. Show created-ago, labelled honestly, or omit it.

## Out of scope

- Benchmarks, metrics panels, Open WebUI registration, key rotation,
  compose rebuilds. All exist on the dashboard; none belong here.

## Verification notes

All Must criteria verified; R5 was deferred to F11 by design (it depends
on F11's start/stop path).

**The stream teardown was a real bug, found and fixed during F10.** Both
the services and GPU streams were launched in `viewModelScope`, and
Navigation Compose's tab-switch idiom (`popUpTo … saveState` +
`restoreState`) keeps the ViewModel alive across a switch — so both SSE
connections survived leaving the tab, confirmed as `ESTAB` in `ss -tnp`.
A leaked GPU stream polls the host every 3 s forever. They are now
collected by `LaunchedEffect`s in `ModelsScreen`, which Compose disposes
when the destination stops being current; independently re-verified in
review (both sockets to `:3399` reach `FIN-WAIT-2` and vanish within ~3 s
of switching to Chats).

To see those sockets, filter `ss -tnp` on the **`qemu-system-x86`**
process — the emulator's host-side connections are NAT'd through it.

**Added beyond the spec, at the owner's request:** favourites sort first
within each group, and a name/port filter appears once there are 8 or
more services. The spec described a list, not a searchable one, which is
why neither was there. Favouriting itself stays on the dashboard —
F10-R7 forbids this tab any mutating call but start/stop.

### Known issue — GPU header can stick on "unavailable" after a blip

After a network drop and restore while the Models tab is open, the GPU
card can stay on "GPU stats unavailable" indefinitely even though
`/api/gpu/stream` is healthy. Leaving the tab and returning fixes it.

The services list recovers from the same blip, so this is specific to the
GPU stream. Likely cause: the SSE client uses `readTimeout(0)` — correct
for a long-lived stream, but it means a half-open socket left by the drop
can hang inside `transport.open()` rather than throwing, so the reconnect
loop never runs and the backoff never gets a chance to retry.

Not a criterion failure — R3's "unavailable state" criterion is about a
missing GPU or a failing `nvidia-smi`, not this — and remounting recovers
it. Recorded rather than fixed: the honest fix is a read timeout slightly
longer than the stream's own tick interval, which is a change to shared
SSE plumbing that every feature uses, and F09 already documented why
touching that plumbing casually is risky.
