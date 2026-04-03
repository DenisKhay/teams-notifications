#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DAEMON_DIR="$PROJECT_DIR/daemon"
EXT_DIR="$PROJECT_DIR/chrome-extension"

echo "=== Teams Notifications Installer ==="
echo ""

# 1. Python venv + dependencies
echo ">>> Setting up Python environment..."
cd "$DAEMON_DIR"
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]" --quiet
echo "    Done."

# 2. Default config (if not exists)
CONFIG_DIR="$HOME/.config/teams-notifications"
if [ ! -f "$CONFIG_DIR/config.toml" ]; then
    echo ">>> Creating default config..."
    mkdir -p "$CONFIG_DIR"
    python -c "
from teams_notifications.config import Config, DEFAULT_CONFIG_PATH
Config().save(DEFAULT_CONFIG_PATH)
"
    echo "    Config: $CONFIG_DIR/config.toml"
fi

# 3. systemd user service
echo ">>> Installing systemd service..."
mkdir -p ~/.config/systemd/user
sed "s|%h|$HOME|g" "$PROJECT_DIR/systemd/teams-notifications.service" \
    > ~/.config/systemd/user/teams-notifications.service
systemctl --user daemon-reload
systemctl --user enable teams-notifications.service
echo "    Done."

# 4. Native messaging host for Chrome
echo ">>> Registering Chrome native messaging host..."
mkdir -p ~/.config/google-chrome/NativeMessagingHosts
chmod +x "$PROJECT_DIR/scripts/native-host.sh"
ln -sf "$EXT_DIR/com.teams_notifications.host.json" \
    ~/.config/google-chrome/NativeMessagingHosts/com.teams_notifications.host.json
echo "    Done."

# 5. KDE autostart (daemon starts on login)
echo ">>> Creating KDE autostart entry..."
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/teams-notifications.desktop << DESKTOP_EOF
[Desktop Entry]
Type=Application
Name=Teams Notifications Daemon
Exec=systemctl --user start teams-notifications
Icon=teams
X-KDE-autostart-phase=2
X-KDE-autostart-after=panel
Hidden=false
DESKTOP_EOF
echo "    Done."

# 6. Application launcher entry (launches Teams with extension)
echo ">>> Creating application launcher..."
mkdir -p ~/.local/share/applications
cat > ~/.local/share/applications/teams-notifications.desktop << DESKTOP_EOF
[Desktop Entry]
Type=Application
Name=Microsoft Teams
Comment=Teams with notification bridge
Exec=bash $PROJECT_DIR/scripts/launch-teams.sh
Terminal=false
Icon=$EXT_DIR/icons/icon128.png
Categories=Network;InstantMessaging;Chat;
StartupWMClass=teams.microsoft.com
DESKTOP_EOF
echo "    Done."

# 7. Start the daemon now
echo ">>> Starting daemon..."
systemctl --user restart teams-notifications
echo "    Done."

echo ""
echo "=== Installation complete ==="
echo ""
echo "How to use:"
echo "  - Search 'Microsoft Teams' in your app launcher to open Teams"
echo "  - The tray icon daemon starts automatically on login"
echo "  - Right-click tray icon for settings"
echo "  - Config file: $CONFIG_DIR/config.toml"
echo ""
echo "To uninstall: ./scripts/uninstall.sh"
