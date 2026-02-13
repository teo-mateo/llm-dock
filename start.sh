#!/bin/bash
#
# LLM-Dock Start Script
# Starts the Docker services and dashboard
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Start the dashboard
echo "Starting LLM-Dock dashboard..."
cd dashboard
source venv/bin/activate
exec python app.py
