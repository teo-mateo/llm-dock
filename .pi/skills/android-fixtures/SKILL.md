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

## Coverage boundary

The synthetic token is not a dashboard credential. The fixture does not contact real services,
read .env, or store submitted auth bodies. Unsupported API paths return 404, not fake success.
For other screens/scenarios, extend this shared kit deliberately rather than copy it into /tmp.
Run `python3 -m unittest discover -s tests -v` from this skill directory after changing it.
