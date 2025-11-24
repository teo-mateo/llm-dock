#!/bin/bash
#
# LLM-Dock - llama.cpp Docker Image Builder
# Builds a custom llama.cpp image optimized for your GPU architecture.
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo "=========================================="
echo "  llama.cpp Docker Image Builder"
echo "=========================================="
echo ""

# Detect GPU if possible
DETECTED_ARCH=""
if command -v nvidia-smi &> /dev/null; then
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
    echo -e "Detected GPU: ${GREEN}$GPU_NAME${NC}"
    echo ""

    # Map GPU to CUDA architecture
    case "$GPU_NAME" in
        *"RTX 50"*|*"Blackwell"*)
            DETECTED_ARCH="120"
            ;;
        *"RTX 40"*|*"RTX 4090"*|*"RTX 4080"*|*"RTX 4070"*|*"RTX 4060"*|*"Ada"*)
            DETECTED_ARCH="89"
            ;;
        *"RTX 30"*|*"RTX 3090"*|*"RTX 3080"*|*"RTX 3070"*|*"RTX 3060"*|*"A100"*|*"A10"*|*"A30"*)
            DETECTED_ARCH="86"
            ;;
        *"RTX 20"*|*"RTX 2080"*|*"RTX 2070"*|*"RTX 2060"*|*"T4"*|*"Turing"*)
            DETECTED_ARCH="75"
            ;;
        *"GTX 10"*|*"GTX 1080"*|*"GTX 1070"*|*"GTX 1060"*|*"P100"*|*"Pascal"*)
            DETECTED_ARCH="61"
            ;;
        *"V100"*)
            DETECTED_ARCH="70"
            ;;
        *"H100"*|*"H200"*|*"Hopper"*)
            DETECTED_ARCH="90"
            ;;
    esac
fi

echo "CUDA Compute Capability Reference:"
echo "─────────────────────────────────────────"
echo "  ${CYAN}120${NC} - RTX 50 series (Blackwell)"
echo "  ${CYAN}90${NC}  - H100, H200 (Hopper)"
echo "  ${CYAN}89${NC}  - RTX 40 series (Ada Lovelace)"
echo "  ${CYAN}86${NC}  - RTX 30 series, A100, A10, A30 (Ampere)"
echo "  ${CYAN}80${NC}  - A100 (Ampere - datacenter)"
echo "  ${CYAN}75${NC}  - RTX 20 series, T4 (Turing)"
echo "  ${CYAN}70${NC}  - V100 (Volta)"
echo "  ${CYAN}61${NC}  - GTX 10 series, P40 (Pascal)"
echo "  ${CYAN}60${NC}  - P100 (Pascal)"
echo ""
echo "Find your GPU's compute capability at:"
echo "https://developer.nvidia.com/cuda-gpus"
echo ""

# Prompt for architecture
if [ -n "$DETECTED_ARCH" ]; then
    echo -e "Suggested architecture for your GPU: ${GREEN}$DETECTED_ARCH${NC}"
    read -p "Enter CUDA compute capability [$DETECTED_ARCH]: " CUDA_ARCH
    CUDA_ARCH=${CUDA_ARCH:-$DETECTED_ARCH}
else
    read -p "Enter CUDA compute capability (e.g., 89 for RTX 40 series): " CUDA_ARCH
fi

if [ -z "$CUDA_ARCH" ]; then
    echo -e "${RED}ERROR: CUDA architecture is required${NC}"
    exit 1
fi

# Validate input
if ! [[ "$CUDA_ARCH" =~ ^[0-9]+$ ]]; then
    echo -e "${RED}ERROR: Invalid architecture. Must be a number (e.g., 89)${NC}"
    exit 1
fi

echo ""
echo "Building llama.cpp with CUDA architecture: $CUDA_ARCH"
echo "This may take 10-15 minutes..."
echo ""

# Update Dockerfile with selected architecture
DOCKERFILE_PATH="$(dirname "$0")/llama.cpp/Dockerfile"

# Create a temporary Dockerfile with the correct architecture
sed "s/CMAKE_CUDA_ARCHITECTURES=[0-9]*/CMAKE_CUDA_ARCHITECTURES=$CUDA_ARCH/" "$DOCKERFILE_PATH" > "$DOCKERFILE_PATH.tmp"
mv "$DOCKERFILE_PATH.tmp" "$DOCKERFILE_PATH"

# Build the image
cd "$(dirname "$0")"
docker build -t my-llamacpp ./llama.cpp/

echo ""
echo -e "${GREEN}=========================================="
echo "  Build Complete!"
echo "==========================================${NC}"
echo ""
echo "The 'my-llamacpp' image is now ready."
echo "You can now create llama.cpp services through the dashboard."
echo ""
