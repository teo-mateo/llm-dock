# Android app — Claude guide

Native Android client for llm-dock. This file covers the toolchain and
**driving the emulator from a shell** — how Claude sees the screen, taps
things, reads logs, and reaches the dashboard running on the host.

## Read first

| What | Where |
|---|---|
| **Software requirements** — the spec being built | `docs/Plan_TOC.md`, then the `F00`–`F13` files beside it |
| **Technical foundation** — architecture, verified deps, test strategy | `docs/Architecture.md` |
| Features deliberately excluded, and why | `docs/Dropped-Features.md` |
| Validated screen designs (16 screens) | `../docs/android/chat-app-mockups.html` |
| Screen → endpoint map | `../docs/android/README.md` — **carries a wrong login endpoint**; `docs/F01-connection-and-auth.md` corrects it |

`docs/Plan_TOC.md` is the entry point: scope, ground rules, the endpoint
surface the app may call, and the feature index.

## How work proceeds

- **Serialized.** One feature at a time, in the `F00 → F13` dependency
  order. No parallel implementation — the emulator is a single shared
  device and two agents installing the same package will stomp each
  other.
- **One commit per completed feature.** A feature is complete when its
  Must requirements are implemented and their acceptance criteria have
  been verified on the device.
- **Mark `[DONE]`** in the Status column of the feature index in
  `docs/Plan_TOC.md` — there and nowhere else.
- If implementation forces a deviation, edit the requirement in its
  feature file and record why in that file's *Deviations* section. Never
  leave the plan describing something the app doesn't do.
- Subagents are for research and review, not for parallel implementation.

## The project

The Gradle root is **`android/src/`** — not `android/`. Open that path in
Studio; anything above it has no `settings.gradle.kts`.

| | |
|---|---|
| Root project | `LLM-DockChat` |
| Package / applicationId | `com.hpz.llmdockchat` |
| minSdk / target / compile | 26 / 37 / 37 |
| AGP | 9.3.1 · Gradle 9.5.1 · Java 17 |
| UI | Compose (BOM 2026.06.01) |
| Studio | Quail 2, build 261.25134.95, at `/opt/android-studio` |

Building from a shell needs the Studio JBR — **system `java` is 11, too
old for AGP 9**:

```bash
cd android/src
export JAVA_HOME=/opt/android-studio/jbr
./gradlew assembleDebug        # APK → app/build/outputs/apk/debug/
./gradlew installDebug         # build + push to the running emulator
```

### AGP 9 differences that break old snippets

Most Android build advice online predates AGP 9. In this project:

- **There is no `org.jetbrains.kotlin.android` plugin.** Kotlin support is
  built into AGP 9; applying the plugin is a hard error. Only
  `com.android.application` and `org.jetbrains.kotlin.plugin.compose` are
  applied.
- **`kotlinOptions { }` does not exist.** Kotlin's JVM target follows
  `compileOptions`. If it ever needs to differ, use a top-level
  `kotlin { compilerOptions { … } }` block, not the old `android {}` one.
- **Gradle 9 uses three-part versions** — the distribution is
  `gradle-9.5.1-bin.zip`; `gradle-9.5-bin.zip` is a 404.
- AGP 9 caps at API 37, and `androidx.core` 1.19 / `lifecycle` 2.11
  *require* both AGP 9.1+ and compileSdk 37 — the trio moves together.

## scripts/dev.sh — the loop

`android/scripts/dev.sh` wraps everything below that gets run more than
once. Prefer it over retyping raw `adb` incantations; it sets `PATH`,
`JAVA_HOME` and the package name itself.

```bash
./scripts/dev.sh emu              # start an emulator if none is running, wait for boot
./scripts/dev.sh run              # build + install + launch
./scripts/dev.sh build|install|stop
./scripts/dev.sh clear            # wipe THIS app's data — re-test Connect from cold
./scripts/dev.sh shot [name]      # screenshot -> $SHOT_DIR, prints the path
./scripts/dev.sh ui               # view hierarchy (exact bounds + resource ids)
./scripts/dev.sh logs [-f]        # logcat, this app only
./scripts/dev.sh token            # dashboard session token for curl work
```

Four subcommands exist to exercise specific acceptance criteria:

```bash
./scripts/dev.sh theme dark|light   # F00-R7  follow the system theme
./scripts/dev.sh fontscale 1.5      # F00-R8  text scaling
./scripts/dev.sh net off|on         # F09-R4  offline behaviour
./scripts/dev.sh clear              # F01     login from a clean install
```

Screenshots land in `$SHOT_DIR` (default `/tmp/llm-dock-android`), never
in the repo.

## Talking to the dashboard

The app is a client of the **dashboard** on `:3399` — not of a model
server. Conversations, runs, cancellation and the services list all live
there.

- From the emulator the host is `10.0.2.2`, so the base URL is
  `http://10.0.2.2:3399`. No setup needed.
- **`api.ai.heapzilla.eu` is not the dashboard.** It fronts a model and
  answers `/api/health` with an OpenAI-shaped
  `{"error":{"message":"Invalid API Key"}}`. The dashboard answers
  `/api/health` unauthenticated with `{"status":"healthy",…}`.

### Authentication

Two ways in, both returning `{token, expires_in: 28800}`:

```bash
# password — DASHBOARD_TOKEN from dashboard/.env, what the login page calls a password
curl -X POST $DASH/api/auth/session -H "Authorization: Bearer $PASSWORD"

# TOTP
curl -X POST $DASH/api/auth/login -H "X-TOTP-Code: 123456"
```

`./scripts/dev.sh token` does the first and prints only the session
token. Then send `Authorization: Bearer totp-…` on every other call.

- **`POST /api/totp/verify` is NOT login.** It is TOTP enrollment and
  requires an existing token. The mockup README gets this wrong.
- Sessions are held in a **process-memory dict** — restarting the
  dashboard invalidates every token. Expiry slides 8 h on each request.

### Test fixtures

- Chat-capable model for testing: **`llamacpp-gemma-4-26b-a4b-it-q8`**,
  running on `:3301`, `kind=chat` — it passes the F07-R1 picker filter.
- **Creating and deleting conversations is fine.** They share `chat.db`
  with the web UI, so prefix test threads to make them identifiable and
  clean up afterwards.
- Do **not** start or stop LLM containers to make room without asking.

## SDK layout on this machine

| Thing | Path |
|-------|------|
| SDK root | `~/Android/Sdk` |
| `adb` | `~/Android/Sdk/platform-tools/adb` (1.0.41 / 36.0.0) |
| `emulator` | `~/Android/Sdk/emulator/emulator` |
| AVD | `Medium_Phone_API_36.1` |

Neither directory is on `PATH` by default. Prefix every shell block with:

```bash
export PATH=$PATH:~/Android/Sdk/platform-tools:~/Android/Sdk/emulator
```

## The device

`Medium_Phone_API_36.1` running Android 16, serial `emulator-5554`:

```
1080 x 2400 px, density 420  →  411 x 914 dp
```

Check what's attached before assuming:

```bash
adb devices -l                       # serial + product/model
adb shell wm size; adb shell wm density
adb shell getprop ro.build.version.release
```

With more than one device attached, target explicitly: `adb -s emulator-5554 …`.

### Starting and stopping it

**The emulator is Claude's to start.** `./scripts/dev.sh emu` starts one
and blocks until `sys.boot_completed`, or reports the running one and
exits. Using an emulator the user already has open is fine.

Raw equivalent:

```bash
emulator -avd Medium_Phone_API_36.1 -no-snapshot-load &     # cold boot
adb wait-for-device shell 'while [ "$(getprop sys.boot_completed)" != 1 ]; do sleep 1; done'
```

**Only one instance of an AVD can run at a time** unless *every* instance
was started with `-read-only`. A Studio-launched emulator holds the write
lock, so a second one fails with *"Another emulator instance is running"*
even if the second passes `-read-only` itself. There is one device;
serialize against it.

**Don't kill, reboot, wipe or factory-reset a running emulator without
asking** — the user may have unsaved state or a debug session attached to
it. Same rule as the LLM containers. Starting one is fine; destroying one
is not. `dev.sh clear` is safe: it wipes only this app's data.

## Reaching the host from inside the emulator

The emulator is NAT'd; `localhost` inside it is the *device*, not your
machine. Two ways across:

- `10.0.2.2` is the host's loopback as seen from the AVD. No setup —
  `http://10.0.2.2:3399` hits the dashboard.
- `adb reverse tcp:<device-port> tcp:<host-port>` maps a device port to a
  host port, so `localhost:<port>` works inside the app. Cleaner when the
  app has a hardcoded base URL, and it survives nothing — **re-run it
  after every emulator restart**.

```bash
adb reverse tcp:3399 tcp:3399        # dashboard, reachable as localhost:3399
adb reverse --list
adb forward tcp:5037 tcp:5037        # the other direction: host → device port
```

## Seeing the screen

```bash
adb exec-out screencap -p > /tmp/claude-1000/.../scratchpad/emu.png
```

Then read the PNG with the Read tool — Claude sees it directly, so there
is no need for the user to describe what's on screen. Write screenshots
to the session scratchpad, not into the repo.

**Coordinate gotcha:** screenshots come back at the physical 1080x2400 but
are downscaled for viewing (typically to 900x2000). Multiply the
coordinates you read off the image by the ratio stated in the image
caption (1.2 at that size) before feeding them to `input tap`.

Video, for animations and transitions:

```bash
adb shell screenrecord --time-limit 20 /sdcard/rec.mp4
adb pull /sdcard/rec.mp4 /tmp/.../scratchpad/
```

## Driving the UI

```bash
adb shell input tap 540 1720                 # physical px
adb shell input swipe 540 1800 540 600 300   # x1 y1 x2 y2 duration_ms — scroll up
adb shell input text 'hello%sworld'          # %s = space; no quotes-in-quotes
adb shell input keyevent KEYCODE_BACK        # also HOME, ENTER, TAB, DEL, APP_SWITCH
```

Prefer reading the view hierarchy over eyeballing pixel positions — it
gives you exact bounds and resource ids:

```bash
adb shell uiautomator dump /sdcard/ui.xml && adb shell cat /sdcard/ui.xml
```

## Apps

```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n <pkg>/.MainActivity
adb shell am start -a android.intent.action.VIEW -d "https://example.com"
adb shell am force-stop <pkg>
adb shell pm clear <pkg>                     # wipes app data — ask first
adb uninstall <pkg>
```

Gradle does install + launch in one step from the project root:

```bash
./gradlew installDebug
```

## Logs

```bash
adb logcat -c                                # clear, then reproduce
adb logcat --pid=$(adb shell pidof -s <pkg>) # just our app
adb logcat -s OkHttp:D LlmDock:D             # by tag
adb logcat *:E                               # errors only
```

`adb logcat` never exits — always bound it (`-d` to dump and quit, or run
it as a background command).

## Gotchas

- **Chrome's first-run wizard** blocks any `VIEW` intent on a fresh AVD:
  a sign-in page ("Stay signed out") then a notifications prompt ("No
  thanks"). Tap through both once per emulator wipe.
- **A page served by `python3 -m http.server` has no charset header.**
  Without a `<meta charset="utf-8">` in the document, Chrome guesses
  windows-1252 and every em-dash becomes `â€"`.
- **Chrome uses a 980px viewport** for pages with no
  `<meta name="viewport">`, so mobile CSS breakpoints never fire and the
  desktop layout gets squeezed. Both metas are required on anything meant
  to be checked on-device.
- `adb reverse` and `adb forward` are per-device and are lost on restart.
- The AVD has no Play Store on `sdk_gphone64` system images unless the
  playstore variant was installed.
- **The device has no `curl` and no `wget`** (toybox has neither), so
  host reachability can't be probed from `adb shell`. Verify it from the
  app's own first request, or trust `10.0.2.2`.
- An `f-string` containing escaped double quotes breaks
  `python3 -c "…"` one-liners used to filter API JSON. Use a heredoc
  (`python3 - <<'EOF'`) or `%`-formatting instead.
