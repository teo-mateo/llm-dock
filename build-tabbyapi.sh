#!/bin/bash
#
# LLM-Dock - TabbyAPI (ExLlamaV3) Docker Image Builder
#
# Wraps the upstream TabbyAPI image (digest-pinned in tabbyapi/Dockerfile) so the
# runner shows up in llm-dock's image-metadata endpoint and check-upstream flow.
# Nothing is compiled here — the base image already carries torch and a
# prebuilt exllamav3 CUDA extension. First pull is ~12 GB.
#

set -e

# Colors
GREEN='\033[0;32m'
NC='\033[0m'

# If the build dies with `failed to fetch oauth token: denied: denied`, a stored
# ghcr.io credential in ~/.docker/config.json is being rejected (ghcr answers
# `denied` rather than falling back to anonymous). The image is public, so pull
# anonymously:  DOCKER_CONFIG=/path/to/empty-config ./build-tabbyapi.sh
# (or `docker logout ghcr.io` if the stored token is dead).

# Base image reference. Leave empty to use the digest pinned in the Dockerfile.
# Set to a cu13 digest for CUDA 13 hosts, e.g.
#   TABBYAPI_REF=ghcr.io/theroyallab/tabbyapi@sha256:... ./build-tabbyapi.sh
TABBYAPI_REF="${TABBYAPI_REF:-}"

echo "=========================================="
echo "  TabbyAPI (ExLlamaV3) Docker Image Builder"
echo "=========================================="
echo ""

# Capture build metadata
BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
BUILD_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "unknown")

echo "Build metadata:"
echo "  Date: $BUILD_DATE"
echo "  Commit: $BUILD_COMMIT"
echo "  Base:   ${TABBYAPI_REF:-pinned digest in tabbyapi/Dockerfile}"
echo ""

BUILD_ARGS=(
    --build-arg BUILD_DATE="$BUILD_DATE"
    --build-arg BUILD_COMMIT="$BUILD_COMMIT"
)
if [ -n "$TABBYAPI_REF" ]; then
    BUILD_ARGS+=(--build-arg "TABBYAPI_REF=$TABBYAPI_REF")
fi

cd "$(dirname "$0")"
docker build "${BUILD_ARGS[@]}" -t llm-dock-tabbyapi ./tabbyapi/

echo ""
echo -e "${GREEN}=========================================="
echo "  Build Complete!"
echo "==========================================${NC}"
echo ""
echo "The 'llm-dock-tabbyapi' image is now ready."
echo ""
echo "What's actually in it:"
docker run --rm --entrypoint cat llm-dock-tabbyapi /opt/llm-dock.txt
echo ""
echo "Runtime notes (see docs/plans/exllamav3-integration.md):"
echo "  - EXL3 models are directories, not files. Mount a flat dir of them"
echo "    read-only at /app/models and pass --model-dir /app/models --model-name <folder>."
echo "    The HF cache layout is NOT a valid model_dir."
echo "  - Needs --shm-size 8g (upstream default compose uses 8g)."
echo "  - Auth reads /app/api_tokens.yml; if absent TabbyAPI generates its own keys,"
echo "    which will not match the api_key llm-dock stores in services.json."
echo ""
echo "Smoke test on this GPU:"
echo "  docker run --rm --gpus all --entrypoint python3 llm-dock-tabbyapi \\"
echo "      -c 'import torch; print(torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0))'"
echo ""
