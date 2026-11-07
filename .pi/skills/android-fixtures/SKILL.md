---
name: android-fixtures
description: Exercise Android Pi session-list states with a reusable local dashboard fixture and controllable SSE updates. Use when pending-question, empty, offline, or backward-compatibility UI checks need deterministic data rather than live services.
---
# Android fixtures

This fixture covers Pi session lists and a controlled cache-transcript scenario, not inference
or answer endpoints. It serves mock health/auth, snapshots/updates and transcript replay.
Never claim its evidence is live validation.
Use it when the deployed backend lacks the feature or a reproducible state is needed.

## Run

Reserve the emulator. Start via the process tool (not shell backgrounding):

```bash
python3 scripts/server.py --port 3999
```

Readiness is `Android Pi fixture ready`. Before touching login, run the preflight:

```bash
python3 scripts/setup.py --device emulator-5554 --reserved
```

The server binds only 127.0.0.1. This command checks the expected fixture is reachable, confirms
the emulator is authorized, establishes and verifies adb reverse forwarding, and prints the app
URL. It refuses physical devices and a conflicting existing mapping. `--reserved` confirms you
already hold the reservation; it does not acquire one. Stop on failure instead of retrying login.
The output says whether the mapping was created or reused; remove only a mapping you created.

Record the app's prior dashboard URL without exposing its credential. In the emulator app only,
sign out and connect to `http://127.0.0.1:3999` with the dummy password `fixture`.
Use the emulator skill for tag-based navigation and screenshots.

## Select deterministic scenarios

```bash
python3 scripts/scenario.py waiting
python3 scripts/scenario.py empty
python3 scripts/scenario.py absent
python3 scripts/scenario.py offline
python3 scripts/scenario.py stress
```

Every change updates both GET and already-connected sessions SSE clients. `waiting` has one live
question and one ended session with a retained question (a live-only indicator must ignore the latter).
`empty` closes the live question; `absent` omits the prompts key for older-server compatibility;
`offline` marks all sessions ended; `stress` keeps that live/ended pair and adds a working session
whose name, `cwd` and model are all long with an open question, plus a short-named live session and a
long-path ended one, for layout checks at a narrow width.
Start with `empty`, switch to `waiting`, then `empty` to prove
stream-driven indicator appearance/disappearance without navigating away. Wait for UI conditions,
not fixed delays. Restore the app's prior real-dashboard connection before hand-back, using the
existing credential workflow without printing secrets.

Stop the fixture via its process ID, remove only your tcp:3999 reverse mapping, and release the
emulator reservation. Port busy means stop and identify the owner; never kill an unknown process.

## Example: prove a stream-driven badge transition

With the fixture app already on its Pi list, run these from the repository root. The badge tag
below is the real #392 tag, not a guessed coordinate:

```bash
python3 .pi/skills/android-fixtures/scripts/scenario.py empty
python3 .pi/skills/android-emulator/scripts/ui.py --device emulator-5554 wait pi_session_fixture-live_fixture-instance
python3 .pi/skills/android-emulator/scripts/ui.py --device emulator-5554 absent pi_needs_answer_fixture-live_fixture-instance
python3 .pi/skills/android-fixtures/scripts/scenario.py waiting
python3 .pi/skills/android-emulator/scripts/ui.py --device emulator-5554 wait pi_needs_answer_fixture-live_fixture-instance
DEVICE=emulator-5554 android/scripts/dev.sh shot issue-394-fixture-waiting
```

Stay on the same screen throughout: re-opening it would not prove the existing SSE connection
updated. For the close transition select `empty`, then verify badge disappearance after the UI
has consumed the update; a single immediate `absent` assertion can race the SSE delivery.
Label the screenshot **fixture-driven**. Do not describe it as a real pi prompt reaching the phone.
Do not write another timed fixture server to reproduce these existing scenarios.

## Example: diagnose connection failure before credentials

Good: start `server.py`, run `setup.py --device emulator-5554 --reserved`, then use its printed
URL and dummy password. If setup says the server is unavailable, inspect the fixture process;
if it reports an adb problem, fix device authorization/forwarding before returning to login.

Bad: host curl succeeds, but the app says connection failed, so repeatedly change passwords or
try TOTP. Host reachability does not imply emulator reachability. The setup helper verifies the
forwarding prerequisite; it does not claim a real app request succeeded.

## Cache transcript verification

`scenario.py cache` selects one deterministic session (`fixture-cache` / `fixture-instance`):
16,000 events, 8,347,855 event-JSON bytes, including long assistant/thinking text, source/tool
outputs and test results. The production checkpoint is about 5.46 MB decompressed (below 8 MiB).
The default replay pages at 500 events and follows replay with a `session` summary.

```bash
python3 scripts/scenario.py cache
python3 scripts/cache.py stats
python3 scripts/cache.py gate --gate replay
python3 scripts/cache.py gate --gate summary
python3 scripts/cache.py gate --gate open
python3 scripts/cache.py append
python3 scripts/cache.py offline
python3 scripts/cache.py online
python3 scripts/cache.py end
```

Controls are GET/POST `/__fixture/transcript`; `append` adds exactly 16 new events. `replay`
holds events and summary; `summary` permits events but withholds the post-replay boundary.
A zero-backlog cached open stays checking until summary, not catching-up. `offline` terminates
detail streams and returns 503 on retry; it does not toggle device networking or stop the list.
`end` makes the fixture eligible for the real DELETE route; `remove` publishes remote removal.
`reset` or reselecting `cache` changes firstSeen and clears counters. Request history is bounded
to 100 entries and records after/cursor ranges, sent event counts and SSE body bytes (not HTTP
chunk overhead or proof of client consumption). Unsupported paths still return 404.

After safely preserving the emulator's prior configuration, use the existing setup/connect
helpers with dummy credentials. `measure_cache.py miss|hit --device emulator-5554 --output FILE`
starts on the Pi list. It composes the shared UI helper, validates real cursor/batch counters,
and inspects only the isolated fixture checkpoint for cardinality and duplicate markers/tools.
For a suffix-hit sample, return to the list and **wait for the row before appending**, so an old
live view cannot consume/commit the suffix first. A zero-suffix hit is also supported.

Reported durations start before the tap command and include Python/adb/tag lookup/UI dump
latency; they are observer bounds, not pure first-paint latency or a physical-phone benchmark.
The gated hit's total time includes deliberate waits; compare its release-to-current separately.
See `docs/pi-remote/android-cache-emulator-evidence.md` for the measured run and restoration.

## Coverage boundary

The synthetic token is not a dashboard credential. The fixture does not contact real services,
read .env, or store submitted auth bodies. Unsupported API paths return 404, not fake success.
For other screens/scenarios, extend this shared kit deliberately rather than copy it into /tmp.
Run `python3 -m unittest discover -s tests -v` from this skill directory after changing it.
