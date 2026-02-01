#!/bin/bash
#
# LLM-Dock Service Installer
# Generates and installs a systemd service for the current user/location
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="llm-dock"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# Detect current user (not root)
if [ "$SUDO_USER" ]; then
    INSTALL_USER="$SUDO_USER"
else
    INSTALL_USER="$(whoami)"
fi

if [ "$INSTALL_USER" = "root" ]; then
    echo "Error: Don't run this as root. Use: sudo ./install-service.sh"
    exit 1
fi

if [ "$EUID" -ne 0 ]; then
    echo "This script requires sudo to install the systemd service."
    echo "Run: sudo ./install-service.sh"
    exit 1
fi

echo "Installing LLM-Dock service..."
echo "  User: $INSTALL_USER"
echo "  Directory: $SCRIPT_DIR"

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=LLM-Dock Dashboard
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=${INSTALL_USER}
WorkingDirectory=${SCRIPT_DIR}/dashboard
ExecStartPre=/usr/bin/docker compose -f ${SCRIPT_DIR}/docker-compose.yml up -d open-webui
ExecStart=${SCRIPT_DIR}/dashboard/venv/bin/python ${SCRIPT_DIR}/dashboard/app.py
ExecStop=/usr/bin/docker compose -f ${SCRIPT_DIR}/docker-compose.yml down
Restart=on-failure
RestartSec=10
Environment=PATH=/usr/local/bin:/usr/bin:/bin
EnvironmentFile=${SCRIPT_DIR}/dashboard/.env

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

echo ""
echo "Service installed and enabled!"
echo ""
echo "Commands:"
echo "  sudo systemctl start $SERVICE_NAME   # Start now"
echo "  sudo systemctl status $SERVICE_NAME  # Check status"
echo "  sudo systemctl stop $SERVICE_NAME    # Stop"
echo "  sudo systemctl disable $SERVICE_NAME # Disable auto-start"
