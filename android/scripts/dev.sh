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
install) cd "$ROOT" && ./gradlew installDebug ;;

run)
  cd "$ROOT" && ./gradlew installDebug
  adb shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null
  echo "launched $PKG"
  ;;

stop)  adb shell am force-stop "$PKG"; echo "stopped $PKG" ;;

clear)
  adb shell pm clear "$PKG" >/dev/null
  echo "cleared data for $PKG (server state untouched)"
  ;;

shot)
  name="${1:-shot}"
  out="$SHOT_DIR/${name}-$(date +%H%M%S).png"
  adb exec-out screencap -p > "$out"
  echo "$out"
  ;;

ui)
  adb shell uiautomator dump /sdcard/ui.xml >/dev/null
  adb shell cat /sdcard/ui.xml
  ;;

logs)
  pid="$(adb shell pidof -s "$PKG" 2>/dev/null | tr -d '\r' || true)"
  if [ -z "$pid" ]; then echo "not running: $PKG" >&2; exit 1; fi
  if [ "${1:-}" = "-f" ]; then adb logcat --pid="$pid"; else adb logcat -d --pid="$pid"; fi
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
  case "${1:-}" in
    dark)  adb shell cmd uimode night yes ;;
    light) adb shell cmd uimode night no ;;
    *) echo "usage: dev.sh theme dark|light" >&2; exit 1 ;;
  esac
  ;;

fontscale) adb shell settings put system font_scale "${1:?usage: dev.sh fontscale 1.5}" ;;

net)
  case "${1:-}" in
    off) adb shell svc wifi disable; adb shell svc data disable; echo "network off" ;;
    on)  adb shell svc wifi enable;  adb shell svc data enable;  echo "network on"  ;;
    *) echo "usage: dev.sh net on|off" >&2; exit 1 ;;
  esac
  ;;

*)
  sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit 1
  ;;
esac
