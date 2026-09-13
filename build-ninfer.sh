#!/bin/bash
#
# LLM-Dock - NInfer Docker Image Builder
# Builds Neroued's NInfer engine from source, with the CUDA 12.9 port patch
# carried in ninfer/ninfer-cu129-port.patch (see ninfer/Dockerfile).
#

set -e

# Colors
GREEN='\033[0;32m'
NC='\033[0m'

# NInfer commit the port patch is cut against. Override to try a newer upstream
# tree, but the patch has to apply to it or the build fails at `git apply`.
NINFER_COMMIT="${NINFER_COMMIT:-d49296868dcc17bd478ec185f0d3a801bcc0bf56}"

echo "=========================================="
echo "  NInfer Docker Image Builder"
echo "=========================================="
echo ""
echo "Building NInfer from source (CUDA 12.9 + port patch)..."
echo "  NInfer commit: ${NINFER_COMMIT}"
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
    --build-arg NINFER_COMMIT="$NINFER_COMMIT" \
    -t llm-dock-ninfer ./ninfer/

echo ""
echo -e "${GREEN}=========================================="
echo "  Build Complete!"
echo "==========================================${NC}"
echo ""
echo "The 'llm-dock-ninfer' image is now ready."
echo ""
