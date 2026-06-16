#!/bin/bash
#
# LLM-Dock - ds4 (DwarfStar 4) Docker Image Builder
# Builds antirez's DeepSeek-V4 inference engine from source into a CUDA image.
#

set -e

# Colors
GREEN='\033[0;32m'
NC='\033[0m'

# Target GPU arch — override for non-Blackwell GPUs, e.g. CUDA_ARCH=sm_90 ./build-ds4.sh
CUDA_ARCH="${CUDA_ARCH:-sm_120}"

echo "=========================================="
echo "  ds4 (DwarfStar 4) Docker Image Builder"
echo "=========================================="
echo ""
echo "Building ds4 from source with CUDA (${CUDA_ARCH})..."
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
    --build-arg CUDA_ARCH="$CUDA_ARCH" \
    -t llm-dock-ds4 ./ds4/

echo ""
echo -e "${GREEN}=========================================="
echo "  Build Complete!"
echo "==========================================${NC}"
echo ""
echo "The 'llm-dock-ds4' image is now ready."
echo ""
