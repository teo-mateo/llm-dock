#!/bin/bash
#
# LLM-Dock Start Script
# Starts the Docker services and dashboard
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "Starting LLM-Dock..."

# Start Docker Compose services
echo "Starting Docker containers..."
docker compose up -d

# Start the dashboard
echo "Starting dashboard..."
cd dashboard
source venv/bin/activate
exec python app.py
