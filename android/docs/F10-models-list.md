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
