#!/bin/bash
#
# LLM-Dock - vLLM Docker Image Builder
# Builds a custom vLLM image with upgraded transformers.
#

set -e

# Colors
GREEN='\033[0;32m'
NC='\033[0m'

echo "=========================================="
echo "  vLLM Docker Image Builder"
echo "=========================================="
echo ""
echo "Building vLLM with upgraded transformers..."
echo ""

# Capture build metadata
BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
BUILD_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "unknown")

echo "Build metadata:"
echo "  Date: $BUILD_DATE"
echo "  Commit: $BUILD_COMMIT"
echo ""

cd "$(dirname "$0")"
docker build \
    --build-arg BUILD_DATE="$BUILD_DATE" \
    --build-arg BUILD_COMMIT="$BUILD_COMMIT" \
    -t llm-dock-vllm ./vllm/

echo ""
echo -e "${GREEN}=========================================="
echo "  Build Complete!"
echo "==========================================${NC}"
echo ""
echo "The 'llm-dock-vllm' image is now ready."
echo ""
