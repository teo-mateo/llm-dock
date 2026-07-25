#!/usr/bin/env bash
# Dev loop for the llm-dock Android client.
#
#   ./dev.sh emu            start the emulator if none is running, wait for boot
#   ./dev.sh build          assemble the debug APK
#   ./dev.sh install        build + install on the device
#   ./dev.sh run            install + launch
#   ./dev.sh stop           force-stop the app
#   ./dev.sh clear          wipe THIS app's data (re-test the Connect screen)
#   ./dev.sh shot [name]    screenshot -> $SHOT_DIR, prints the path
#   ./dev.sh ui             dump the view hierarchy (bounds + resource ids)
#   ./dev.sh logs [-f]      logcat for this app only
#   ./dev.sh token          get a dashboard session token for curl testing
#   ./dev.sh theme dark|light
#   ./dev.sh fontscale <n>  e.g. 1.0, 1.5
#   ./dev.sh net on|off     airplane mode, for offline testing
#
# Never wipes or factory-resets an emulator. `clear` touches only our package.
#
# DEVICE TARGETING. Every adb call here is pinned to one device, chosen in
# this order:
#
#   1. $DEVICE, if set        e.g. DEVICE=204010d2 ./dev.sh shot
#   2. the only attached device, if there is exactly one
#   3. the emulator, if one is attached
#
# A physical device is NEVER selected automatically while an emulator is
# present, and commands that write to a device (install/run/clear/net/…)
# refuse to touch a physical one unless you named it in $DEVICE. Bare adb
# picks whatever it likes, which on this project put a build on the
# owner's phone mid-session and would have taken its network down with
# `net off`.
set -euo pipefail

SDK="${ANDROID_SDK_ROOT:-$HOME/Android/Sdk}"
export PATH="$PATH:$SDK/platform-tools:$SDK/emulator"
export JAVA_HOME="${JAVA_HOME:-/opt/android-studio/jbr}"

PKG="com.hpz.llmdockchat"
AVD="${AVD:-Medium_Phone_API_36.1}"
SHOT_DIR="${SHOT_DIR:-/tmp/llm-dock-android}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../src" && pwd)"
DASH="${DASH:-http://localhost:3399}"

mkdir -p "$SHOT_DIR"
cmd="${1:-}"; shift || true

# --- device targeting -------------------------------------------------

attached() { adb devices | awk '$2 == "device" { print $1 }'; }

resolve_device() {
  if [ -n "${DEVICE:-}" ]; then echo "$DEVICE"; return; fi
  local all count emu
  all="$(attached)"
  count="$(printf '%s\n' "$all" | grep -c . || true)"
  [ "$count" -eq 0 ] && { echo "no device attached" >&2; exit 1; }
  [ "$count" -eq 1 ] && { printf '%s\n' "$all"; return; }
  emu="$(printf '%s\n' "$all" | grep '^emulator-' | head -1 || true)"
  if [ -n "$emu" ]; then
    echo "note: $count devices attached, using $emu (set DEVICE= to override)" >&2
    echo "$emu"; return
  fi
  echo "$count devices attached and none is an emulator — set DEVICE=<serial>" >&2
  printf '  %s\n' $all >&2
  exit 1
}

# Refuse to write to a physical device unless it was named explicitly.
require_writable() {
  case "$TARGET" in
    emulator-*) return ;;
  esac
  [ -n "${DEVICE:-}" ] && return
  echo "refusing to run '$cmd' against physical device $TARGET." >&2
  echo "That may be the owner's phone: 'clear' destroys its stored credential" >&2
  echo "and 'net off' takes its network down. Re-run with DEVICE=$TARGET if" >&2
  echo "you really mean it." >&2
  exit 1
}

if [ "$cmd" != "emu" ] && [ "$cmd" != "token" ] && [ "$cmd" != "build" ] && [ -n "$cmd" ]; then
  TARGET="$(resolve_device)"
fi
adb_() { adb -s "$TARGET" "$@"; }

case "$cmd" in

emu)
  if adb devices | grep -q "device$"; then
    echo "already running: $(adb devices | grep 'device$' | head -1)"; exit 0
  fi
  # NOTE: a second instance of the same AVD only works if EVERY instance was
  # started -read-only. A Studio-launched emulator holds the write lock, so
  # this can only start one when none is running.
  emulator -avd "$AVD" -no-audio -no-boot-anim -no-snapshot-save \
    > "$SHOT_DIR/emulator.log" 2>&1 &
  echo "booting $AVD (log: $SHOT_DIR/emulator.log)"
  adb wait-for-device
  until [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; do
    sleep 2
  done
  echo "booted: $(adb devices | grep 'device$')"
  ;;

build)   cd "$ROOT" && ./gradlew assembleDebug ;;

install)
  # NOT ./gradlew installDebug — that installs to EVERY attached device.
  require_writable
  cd "$ROOT" && ./gradlew assembleDebug
  adb_ install -r app/build/outputs/apk/debug/app-debug.apk
  echo "installed on $TARGET"
  ;;

run)
  require_writable
  cd "$ROOT" && ./gradlew assembleDebug
  adb_ install -r app/build/outputs/apk/debug/app-debug.apk
  adb_ shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null
  echo "launched $PKG on $TARGET"
  ;;

stop)  require_writable; adb_ shell am force-stop "$PKG"; echo "stopped $PKG on $TARGET" ;;

clear)
  require_writable
  adb_ shell pm clear "$PKG" >/dev/null
  echo "cleared data for $PKG on $TARGET (server state untouched)"
  ;;

shot)
  name="${1:-shot}"
  out="$SHOT_DIR/${name}-$(date +%H%M%S).png"
  adb_ exec-out screencap -p > "$out"
  echo "$out"
  ;;

ui)
  adb_ shell uiautomator dump /sdcard/ui.xml >/dev/null
  adb_ shell cat /sdcard/ui.xml
  ;;

logs)
  pid="$(adb_ shell pidof -s "$PKG" 2>/dev/null | tr -d '\r' || true)"
  if [ -z "$pid" ]; then echo "not running: $PKG on $TARGET" >&2; exit 1; fi
  if [ "${1:-}" = "-f" ]; then adb_ logcat --pid="$pid"; else adb_ logcat -d --pid="$pid"; fi
  ;;

token)
  # Exchange the dashboard password (DASHBOARD_TOKEN in .env, what the login
  # page calls a password) for a short-lived session token. Prints only the
  # session token, never the password.
  env_file="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../dashboard" && pwd)/.env"
  pw="$(grep '^DASHBOARD_TOKEN=' "$env_file" | cut -d= -f2- | tr -d '"'"'"'')"
  curl -s -X POST "$DASH/api/auth/session" -H "Authorization: Bearer $pw" \
    | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])'
  ;;

theme)
  require_writable
  case "${1:-}" in
    dark)  adb_ shell cmd uimode night yes ;;
    light) adb_ shell cmd uimode night no ;;
    *) echo "usage: dev.sh theme dark|light" >&2; exit 1 ;;
  esac
  ;;

fontscale)
  require_writable
  adb_ shell settings put system font_scale "${1:?usage: dev.sh fontscale 1.5}"
  ;;

net)
  require_writable
  case "${1:-}" in
    off) adb_ shell svc wifi disable; adb_ shell svc data disable; echo "network off on $TARGET" ;;
    on)  adb_ shell svc wifi enable;  adb_ shell svc data enable;  echo "network on on $TARGET"  ;;
    *) echo "usage: dev.sh net on|off" >&2; exit 1 ;;
  esac
  ;;

*)
  sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit 1
  ;;
esac
