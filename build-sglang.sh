#!/usr/bin/env bash
# Adapt the digest-pinned Pennyroyal image. Never install a host toolkit/driver.
set -euo pipefail

cd "$(dirname "$0")"
build_date=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
build_commit=$(git rev-parse HEAD 2>/dev/null || echo unknown)
build_args=()
if [[ -n "${SGLANG_BASE:-}" ]]; then
    build_args+=(--build-arg "SGLANG_BASE=$SGLANG_BASE")
fi
docker build \
    "${build_args[@]}" \
    --build-arg "BUILD_DATE=$build_date" \
    --build-arg "BUILD_COMMIT=$build_commit" \
    -t llm-dock-sglang ./sglang
docker run --rm --entrypoint /usr/local/bin/pennyroyal llm-dock-sglang --check
