#!/bin/bash
#
# LLM-Dock - Project Maya Docker Image Builder
# Compiles Maya's engines (maya-ds4 for DeepSeek-V4.1-Flash, maya for
# GLM-5.3-Flash) from a local Maya checkout at one commit (see maya/Dockerfile).
#
#   ./build-maya.sh                         # MAYA_SRC's HEAD
#   MAYA_COMMIT=<sha> ./build-maya.sh       # a specific commit of MAYA_SRC
#   MAYA_TARGETS=maya-ds4 ./build-maya.sh   # DeepSeek engine only (faster)
#
# Env: MAYA_SRC (default /github/mw00/project-maya), MAYA_COMMIT (default its
# HEAD), CUDA_ARCH (default 120), MAYA_TARGETS, MAYA_JOBS (default nproc/2).
#

set -e

GREEN='\033[0;32m'
NC='\033[0m'

MAYA_SRC="${MAYA_SRC:-/github/mw00/project-maya}"
MAYA_COMMIT="$(git -C "$MAYA_SRC" rev-parse "${MAYA_COMMIT:-HEAD}")"
MAYA_VERSION="$(git -C "$MAYA_SRC" show "$MAYA_COMMIT:VERSION" 2>/dev/null | tr -d '[:space:]' || true)"
CUDA_ARCH="${CUDA_ARCH:-120}"
MAYA_TARGETS="${MAYA_TARGETS:-maya-ds4 maya}"
MAYA_JOBS="${MAYA_JOBS:-}"

# One extracted tree per commit, reused by later builds of the same commit and
# never the checkout itself: uncommitted edits and build dirs stay out.
CTX="${HOME}/.cache/llm-dock-maya-build/${MAYA_COMMIT}"

echo "=========================================="
echo "  Project Maya Docker Image Builder"
echo "=========================================="
echo ""
echo "  Maya source:  ${MAYA_SRC}"
echo "  Maya commit:  ${MAYA_COMMIT} (${MAYA_VERSION:-no VERSION})"
echo "  CUDA arch:    sm_${CUDA_ARCH}"
echo "  Targets:      ${MAYA_TARGETS}"
echo ""

if [ ! -f "$CTX/.complete" ]; then
    mkdir -p "$CTX"
    git -C "$MAYA_SRC" archive --format=tar "$MAYA_COMMIT" | tar -x -C "$CTX"
    touch "$CTX/.complete"
fi

BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
BUILD_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "unknown")

cd "$(dirname "$0")"
docker buildx build --load \
    --build-context maya-src="$CTX" \
    --build-arg BUILD_DATE="$BUILD_DATE" \
    --build-arg BUILD_COMMIT="$BUILD_COMMIT" \
    --build-arg MAYA_COMMIT="$MAYA_COMMIT" \
    --build-arg MAYA_VERSION="$MAYA_VERSION" \
    --build-arg CUDA_ARCH="$CUDA_ARCH" \
    --build-arg MAYA_TARGETS="$MAYA_TARGETS" \
    --build-arg MAYA_JOBS="$MAYA_JOBS" \
    -t llm-dock-maya ./maya/

echo ""
echo -e "${GREEN}=========================================="
echo "  Build Complete!"
echo "==========================================${NC}"
echo ""
echo "The 'llm-dock-maya' image is now ready."
echo "  docker run --rm --entrypoint cat llm-dock-maya /opt/llm-dock.txt"
echo ""
