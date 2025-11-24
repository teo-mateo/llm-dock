#!/bin/bash
#
# LLM-Dock Setup Script
# Initializes the dashboard environment and starts infrastructure services.
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "  LLM-Dock Setup"
echo "=========================================="
echo ""

# Check prerequisites
echo "Checking prerequisites..."

# Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}ERROR: Docker is not installed${NC}"
    echo "Please install Docker: https://docs.docker.com/get-docker/"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} Docker"

# Docker Compose v2
if ! docker compose version &> /dev/null; then
    echo -e "${RED}ERROR: Docker Compose v2 is not available${NC}"
    echo "Please ensure you have Docker Compose v2 (docker compose, not docker-compose)"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} Docker Compose v2"

# Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}ERROR: Python 3 is not installed${NC}"
    exit 1
fi
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "  ${GREEN}✓${NC} Python $PYTHON_VERSION"

# nvidia-smi (optional but recommended)
if command -v nvidia-smi &> /dev/null; then
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
    echo -e "  ${GREEN}✓${NC} NVIDIA GPU: $GPU_NAME"
else
    echo -e "  ${YELLOW}!${NC} nvidia-smi not found (GPU monitoring won't work)"
fi

# nvidia-container-toolkit
if docker info 2>/dev/null | grep -q "nvidia"; then
    echo -e "  ${GREEN}✓${NC} nvidia-container-toolkit"
else
    echo -e "  ${YELLOW}!${NC} nvidia-container-toolkit not detected (GPU containers may not work)"
fi

echo ""

# Setup dashboard environment
cd "$(dirname "$0")/dashboard"

# Create .env if not exists
if [ ! -f .env ]; then
    echo "Creating .env file..."

    # Generate secure token
    TOKEN=$(python3 -c "import secrets; print(secrets.token_hex(32))")

    # Copy template and replace token
    cp .env.example .env
    sed -i "s/your-secret-token-here/$TOKEN/" .env

    echo -e "  ${GREEN}✓${NC} Created .env with generated token"
    echo ""
    echo -e "  ${YELLOW}Your dashboard token:${NC}"
    echo "  $TOKEN"
    echo ""
    echo -e "  ${YELLOW}Save this token - you'll need it to access the API!${NC}"
    echo ""
else
    echo -e "  ${GREEN}✓${NC} .env already exists"
fi

# Create virtual environment
if [ ! -d venv ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
    echo -e "  ${GREEN}✓${NC} Created venv"
fi

# Activate and install dependencies
echo "Installing Python dependencies..."
source venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo -e "  ${GREEN}✓${NC} Dependencies installed"

cd ..

# Start Open WebUI
echo ""
echo "Starting Open WebUI..."
docker compose up -d open-webui

# Wait for it to be healthy
echo "Waiting for Open WebUI to start..."
sleep 5

if docker ps | grep -q open-webui; then
    echo -e "  ${GREEN}✓${NC} Open WebUI running at http://localhost:3300"
else
    echo -e "  ${YELLOW}!${NC} Open WebUI may still be starting..."
fi

echo ""
echo "=========================================="
echo "  Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Build the llama.cpp Docker image (if using GGUF models):"
echo "   ./build-llamacpp.sh"
echo ""
echo "2. Start the dashboard:"
echo "   cd dashboard"
echo "   source venv/bin/activate"
echo "   python app.py"
echo ""
echo "3. Access the dashboard at http://localhost:3399"
echo "   (Use the token shown above for API authentication)"
echo ""
echo "4. Access Open WebUI at http://localhost:3300"
echo ""
