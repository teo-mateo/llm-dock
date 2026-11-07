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
python3 scripts/ui.py --device emulator-5554 tags pi_
python3 scripts/ui.py --device emulator-5554 bounds pi_session_fixture-live_fixture-instance
python3 scripts/ui.py --device emulator-5554 absent pi_needs_answer_fixture-ended_fixture-instance
python3 scripts/ui.py --device emulator-5554 wait-text "Connected"
```

Use actual tags from source/hierarchy; example indicator tags are not API guarantees.
`tags <substring>` lists the resource IDs currently on screen, which is how you find the real tag
instead of guessing one. Do not write inline XML regexes for discovery or measurement: `tags` and
`bounds` cover both.
`wait`/`tap` use bounded retries for presence. `absent` checks the current hierarchy once, so first
wait for the containing screen; absence alone is not proof that the correct screen loaded.
Errors report resource IDs only, never input values or the full hierarchy. `wait-text` observes
an exact display label without tapping; Markdown syntax in source text may not be the rendered
label. Timings around these commands include adb/tag lookup and hierarchy-dump overhead, not
just app rendering.

**Compose tags inside a `Dialog` window never reach `uiautomator`** — the dump shows only
`android:id/content`, however the dialog is tagged. Address dialog buttons by their exact label
instead: `ui.py tap-text "Sign out"` / `absent-text "Sign out"`. Do not conclude a dialog is
untagged in source, and do not add tags hoping they appear.

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

A dump that comes back empty or wedged is retried inside the budget, so a single `wait` failure
means the tag really is absent for the whole timeout. If `wait` times out, inspect the screen and
report why the expected tag was missing.
Do not simply increase a sleep. Use `bounds <actual-row-tag>` for row measurements rather than
writing another regex/XML parser.

## Example: point the app at a URL

Good — one tag-driven command, password from the environment, bounded waits:

```bash
LLMDOCK_TEST_PASSWORD=fixture python3 scripts/connect.py --device emulator-5554 --url http://127.0.0.1:3999
```

Bad — hand-repeating sign-out, field clearing and submit in ad-hoc shell, with sleeps between taps.
That sequence was re-derived four times in one session; the helper exists so it is not.

## Example: read a measurement instead of parsing XML

Good: `python3 scripts/ui.py --device emulator-5554 bounds pi_session_fixture-live_fixture-instance`
prints `bounds: <tag> (x1, y1, x2, y2)`; subtract y values for a row height.

Bad: an inline `python3 - <<EOF` block that dumps `uiautomator` and regexes `<node>` tags. Use
`tags` to discover IDs and `bounds` to measure; report the number, not the parser.

Use `../android-fixtures/SKILL.md` for deterministic session-list states. Restore the prior
connection/configuration and remove only your own adb reverse mapping when done. Do not print
real credentials.
