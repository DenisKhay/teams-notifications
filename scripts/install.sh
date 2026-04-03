#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DAEMON_DIR="$PROJECT_DIR/daemon"

echo "=== Teams Notifications Installer ==="

echo ">>> Creating Python virtual environment..."
cd "$DAEMON_DIR"
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]" --quiet

echo ">>> Installing systemd user service..."
mkdir -p ~/.config/systemd/user
sed "s|%h|$HOME|g" "$PROJECT_DIR/systemd/teams-notifications.service" \
    > ~/.config/systemd/user/teams-notifications.service
systemctl --user daemon-reload
systemctl --user enable teams-notifications.service

echo ">>> Creating KDE autostart entry..."
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/teams-notifications.desktop << DESKTOP_EOF
[Desktop Entry]
Type=Application
Name=Teams Notifications
Exec=systemctl --user start teams-notifications
Icon=teams
X-KDE-autostart-phase=2
X-KDE-autostart-after=panel
Hidden=false
DESKTOP_EOF

CONFIG_DIR="$HOME/.config/teams-notifications"
if [ ! -f "$CONFIG_DIR/config.toml" ]; then
    echo ">>> Creating default config..."
    mkdir -p "$CONFIG_DIR"
    python -c "
from teams_notifications.config import Config, DEFAULT_CONFIG_PATH
Config().save(DEFAULT_CONFIG_PATH)
"
fi

echo ""
echo "=== Installation complete ==="
echo "Next: ./scripts/setup-azure.sh"
