#!/bin/bash
#
# LLM-Dock - Basalt Docker Image Builder
# Builds jesdga95/basalt with its own upstream Dockerfile, from one pinned commit.
#
#   ./build-basalt.sh                          # the pinned commit
#   BASALT_COMMIT=<sha|tag> ./build-basalt.sh  # another upstream commit
#   BASALT_IMAGE=llm-dock-basalt-next ./build-basalt.sh   # a separate image
#
# Env: BASALT_COMMIT, BASALT_IMAGE (default llm-dock-basalt), CUDA_TAG (default
# 13.0.2: the release archives' CUDA, whose Linux driver floor is 580.95.05;
# upstream's Dockerfile default is newer than that floor).
#

set -e

GREEN='\033[0;32m'
NC='\033[0m'

BASALT_REPO="https://github.com/jesdga95/basalt.git"
BASALT_COMMIT="${BASALT_COMMIT:-ff0b978d2ee9ff195d113b6feb80961b2d2f99ef}"
BASALT_IMAGE="${BASALT_IMAGE:-llm-dock-basalt}"
CUDA_TAG="${CUDA_TAG:-13.0.2}"

CACHE="${HOME}/.cache/llm-dock-basalt-build"
SRC="${CACHE}/src"

echo "=========================================="
echo "  Basalt Docker Image Builder"
echo "=========================================="
echo ""
echo "  Basalt commit: ${BASALT_COMMIT}"
echo "  CUDA:          ${CUDA_TAG}"
echo "  Image:         ${BASALT_IMAGE}"
echo ""

if [ ! -d "$SRC/.git" ]; then
    mkdir -p "$CACHE"
    git clone --filter=blob:none "$BASALT_REPO" "$SRC"
fi
git -C "$SRC" fetch --tags origin
RESOLVED="$(git -C "$SRC" rev-parse "${BASALT_COMMIT}^{commit}")"
CTX="${CACHE}/${RESOLVED}"
if [ ! -f "$CTX/.complete" ]; then
    mkdir -p "$CTX"
    git -C "$SRC" archive --format=tar "$RESOLVED" | tar -x -C "$CTX"
    touch "$CTX/.complete"
fi
BASALT_VERSION="$(git -C "$SRC" describe --tags --always "$RESOLVED")"

BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
BUILD_COMMIT=$(git -C "$(dirname "$0")" rev-parse HEAD 2>/dev/null || echo "unknown")

docker build \
    --build-arg CUDA_TAG="$CUDA_TAG" \
    --label "llm-dock.build-date=${BUILD_DATE}" \
    --label "llm-dock.build-commit=${BUILD_COMMIT}" \
    --label "llm-dock.basalt-commit=${RESOLVED}" \
    --label "llm-dock.basalt-version=${BASALT_VERSION}" \
    --label "llm-dock.cuda=${CUDA_TAG}" \
    -t "$BASALT_IMAGE" "$CTX"

echo ""
echo -e "${GREEN}=========================================="
echo "  Build Complete!"
echo "==========================================${NC}"
echo ""
echo "The '${BASALT_IMAGE}' image (${BASALT_VERSION}) is now ready."
echo ""
