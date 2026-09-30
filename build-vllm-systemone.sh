#!/bin/bash
#
# LLM-Dock - vLLM + SystemOne Docker Image Builder
# Layers the OpenJev /v1/systemone helper onto a vLLM image.
#

set -e

GREEN='\033[0;32m'
NC='\033[0m'

BASE="${VLLM_SYSTEMONE_BASE:-llm-dock-vllm:cu129-580}"
BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
BUILD_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "unknown")

echo "Building llm-dock-vllm-systemone on $BASE"
echo "  Date: $BUILD_DATE"
echo "  Commit: $BUILD_COMMIT"

cd "$(dirname "$0")"
docker build \
    --build-arg VLLM_SYSTEMONE_BASE="$BASE" \
    --build-arg BUILD_DATE="$BUILD_DATE" \
    --build-arg BUILD_COMMIT="$BUILD_COMMIT" \
    -t llm-dock-vllm-systemone ./vllm-systemone/

echo -e "${GREEN}The 'llm-dock-vllm-systemone' image is now ready.${NC}"
