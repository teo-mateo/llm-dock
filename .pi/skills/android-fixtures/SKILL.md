---
name: android-fixtures
description: Exercise Android Pi session-list states with a reusable local dashboard fixture and controllable SSE updates. Use when pending-question, empty, offline, or backward-compatibility UI checks need deterministic data rather than live services.
---
# Android fixtures

This fixture covers the Pi sessions list only, not transcript, inference, or answer endpoints.
It serves mock health/auth and session snapshots/updates. Never claim its evidence is live validation.
Use it when the deployed backend lacks the feature or a reproducible state is needed.

## Run

Reserve the emulator. Start via the process tool (not shell backgrounding):

```bash
python3 scripts/server.py --port 3999
```

Readiness is `Android Pi fixture ready`. The server binds only 127.0.0.1; route the reserved
emulator explicitly:

```bash
$HOME/Android/Sdk/platform-tools/adb -s emulator-5554 reverse tcp:3999 tcp:3999
```

Record the app's prior dashboard URL without exposing its credential. In the emulator app only,
sign out and connect to `http://127.0.0.1:3999` with the dummy password `fixture`.
Use the emulator skill for tag-based navigation and screenshots.

## Select deterministic scenarios

```bash
python3 scripts/scenario.py waiting
python3 scripts/scenario.py empty
python3 scripts/scenario.py absent
python3 scripts/scenario.py offline
```

Every change updates both GET and already-connected sessions SSE clients. `waiting` has one live
question and one ended session with a retained question (a live-only indicator must ignore the latter).
`offline` marks all sessions ended; `stress` is the same live/ended pair plus a working session whose
name, `cwd` and model are all long, carrying an open question, for layout stress at a narrow width.
`empty` closes the live question; `absent` omits the prompts key for older-server compatibility;
`offline` marks all sessions ended. Start with `empty`, switch to `waiting`, then `empty` to prove
stream-driven indicator appearance/disappearance without navigating away. Wait for UI conditions,
not fixed delays. Restore the app's prior real-dashboard connection before hand-back, using the
existing credential workflow without printing secrets.

Stop the fixture via its process ID, remove only your tcp:3999 reverse mapping, and release the
emulator reservation. Port busy means stop and identify the owner; never kill an unknown process.

## Coverage boundary

The synthetic token is not a dashboard credential. The fixture does not contact real services,
read .env, or store submitted auth bodies. Unsupported API paths return 404, not fake success.
For other screens/scenarios, extend this shared kit deliberately rather than copy it into /tmp.
Run `python3 -m unittest discover -s tests -v` from this skill directory after changing it.
