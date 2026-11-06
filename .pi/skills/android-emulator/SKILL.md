---
name: android-emulator
description: Interact with the reserved LLM-Dock Android emulator using Compose tags, bounded waits and screenshots. Use for Android UI verification, tapping controls, or collecting device evidence.
---
# Android emulator

Reserve the emulator with the PO first. These helpers refuse physical-device targets. Do not
reset, reboot, wipe, change global font scale, or install over another developer's device run.

Use the existing `../../../android/scripts/dev.sh` for screenshots, hierarchy and logs.
Use `scripts/ui.py` instead of writing another UI XML/coordinate parser:

```bash
python3 scripts/ui.py --device emulator-5554 wait nav_tab_pi
python3 scripts/ui.py --device emulator-5554 tap nav_tab_pi
python3 scripts/ui.py --device emulator-5554 bounds pi_sessions_screen
python3 scripts/ui.py --device emulator-5554 absent needs_answer_fixture-a
```

Use actual tags from source/hierarchy; example indicator tags are not API guarantees.
`wait`/`tap` use bounded retries for presence. `absent` checks the current hierarchy once, so first
wait for the containing screen; absence alone is not proof that the correct screen loaded.
Errors report resource IDs only, never input values or the full hierarchy.

The helper uses exact resource-id or the package-qualified `:id/` suffix, not substring matching.
Compose tags must be exposed as resource IDs by the app. If a tag is missing, inspect the existing
hierarchy/source rather than falling back to brittle guessed coordinates.

Build through the testing skill, then install the existing APK without another Gradle invocation:

```bash
$HOME/Android/Sdk/platform-tools/adb -s emulator-5554 install -r <checkout>/android/src/app/build/outputs/apk/debug/app-debug.apk
$HOME/Android/Sdk/platform-tools/adb -s emulator-5554 shell am start -n com.hpz.llmdockchat/.MainActivity
DEVICE=emulator-5554 <checkout>/android/scripts/dev.sh shot issue-N-state
```

## Example: navigate without guessed delays

Good — the helper waits for the actual tagged control before tapping:

```bash
python3 scripts/ui.py --device emulator-5554 tap nav_tab_pi
python3 scripts/ui.py --device emulator-5554 wait pi_session_fixture-live_fixture-instance
```

Bad — the delay is unrelated to readiness, and guessed coordinates may hit another control:

```bash
sleep 5
adb shell input tap 680 2200
```

If `wait` times out, inspect the screen/hierarchy and report why the expected tag was missing.
Do not simply increase a sleep. Use `bounds <actual-row-tag>` for row measurements rather than
writing another regex/XML parser.

Use `../android-fixtures/SKILL.md` for deterministic session-list states. Restore the prior
connection/configuration and remove only your own adb reverse mapping when done. Do not print
real credentials.
