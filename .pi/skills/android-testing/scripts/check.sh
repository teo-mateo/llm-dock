#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
export JAVA_HOME="${JAVA_HOME:-/opt/android-studio/jbr}"
export ANDROID_HOME="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Android/Sdk}}"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
usage() { echo 'usage: check.sh doctor | build | test <class-pattern...|--all>'; }
case "${1:-}" in
  --help|-h) usage; exit 0 ;;
  doctor)
    [ "$#" -eq 1 ] || { usage >&2; exit 2; }
    test -x "$JAVA_HOME/bin/java" || { echo "JDK missing: $JAVA_HOME" >&2; exit 1; }
    test -d "$ANDROID_HOME/platforms" || { echo "SDK platforms missing: $ANDROID_HOME" >&2; exit 1; }
    "$JAVA_HOME/bin/java" -version
    echo "SDK=$ANDROID_HOME checkout=$ROOT"
    ;;
  build)
    [ "$#" -eq 1 ] || { usage >&2; exit 2; }
    exec bash "$ROOT/android/scripts/dev.sh" build
    ;;
  test)
    shift
    [ "$#" -gt 0 ] || { usage >&2; exit 2; }
    args=()
    if [ "$1" = --all ]; then
      [ "$#" -eq 1 ] || { usage >&2; exit 2; }
    else
      for pattern in "$@"; do args+=(--tests "$pattern"); done
    fi
    cd "$ROOT/android/src"
    exec ./gradlew :app:testDebugUnitTest "${args[@]}"
    ;;
  *) usage >&2; exit 2 ;;
esac
