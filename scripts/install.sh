#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DAEMON_DIR="$PROJECT_DIR/daemon"
EXT_DIR="$PROJECT_DIR/chrome-extension"
CONFIG_DIR="$HOME/.config/teams-notifications"

echo ""
echo "  Teams Notifications for Linux"
echo "  =============================="
echo ""

# --- Prerequisites check ---
echo "[1/7] Checking prerequisites..."
missing=()
command -v python3 >/dev/null || missing+=("python3")
command -v google-chrome >/dev/null || missing+=("google-chrome")
command -v notify-send >/dev/null || missing+=("notify-send (libnotify)")
command -v xdotool >/dev/null || missing+=("xdotool")
if [ ${#missing[@]} -gt 0 ]; then
    echo "  ERROR: Missing required tools: ${missing[*]}"
    echo "  Install them and re-run this script."
    exit 1
fi
python3 -c "import sys; assert sys.version_info >= (3, 11), f'Python 3.11+ required, got {sys.version}'" 2>/dev/null || {
    echo "  ERROR: Python 3.11+ is required."
    exit 1
}
echo "  All prerequisites met."

# --- Python venv ---
echo "[2/7] Setting up Python environment..."
cd "$DAEMON_DIR"
python3 -m venv .venv
source .venv/bin/activate
pip install -e . --quiet 2>&1 | tail -1
echo "  Done."

# --- Default config ---
echo "[3/7] Configuration..."
if [ ! -f "$CONFIG_DIR/config.toml" ]; then
    mkdir -p "$CONFIG_DIR"
    python -c "
from teams_notifications.config import Config, DEFAULT_CONFIG_PATH
Config().save(DEFAULT_CONFIG_PATH)
"
    echo "  Created default config: $CONFIG_DIR/config.toml"
else
    echo "  Config already exists, keeping it."
fi

# --- systemd user service ---
echo "[4/7] Installing systemd service..."
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/teams-notifications.service << SVCEOF
[Unit]
Description=Teams Notifications Tray Daemon
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=$DAEMON_DIR/.venv/bin/python -m teams_notifications.main
WorkingDirectory=$DAEMON_DIR
Restart=on-failure
RestartSec=5
Environment=QT_QPA_PLATFORM=xcb
PassEnvironment=DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS XDG_RUNTIME_DIR

[Install]
WantedBy=graphical-session.target
SVCEOF
systemctl --user daemon-reload
systemctl --user enable teams-notifications.service
echo "  Done."

# --- Native messaging host ---
echo "[5/7] Registering Chrome native messaging host..."
chmod +x "$PROJECT_DIR/scripts/native-host.sh"

# Generate native-host.sh with correct paths
cat > "$PROJECT_DIR/scripts/native-host.sh" << NHEOF
#!/usr/bin/env bash
cd "$DAEMON_DIR"
exec .venv/bin/python3 -m teams_notifications.native_host
NHEOF
chmod +x "$PROJECT_DIR/scripts/native-host.sh"

# Chrome extension ID is deterministic based on path
# For unpacked extensions, we use a wildcard to allow any extension ID
cat > "$EXT_DIR/com.teams_notifications.host.json" << NMEOF
{
  "name": "com.teams_notifications.host",
  "description": "Teams Notifications native messaging host",
  "path": "$PROJECT_DIR/scripts/native-host.sh",
  "type": "stdio",
  "allowed_origins": ["chrome-extension://bjmpjhfbepbckdfoalihmgknlmfgdmno/"]
}
NMEOF

mkdir -p ~/.config/google-chrome/NativeMessagingHosts
ln -sf "$EXT_DIR/com.teams_notifications.host.json" \
    ~/.config/google-chrome/NativeMessagingHosts/com.teams_notifications.host.json
echo "  Done."

# --- Desktop entries ---
echo "[6/7] Creating desktop entries..."

# App launcher entry
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

# KDE autostart (daemon on login)
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/teams-notifications.desktop << AUTOEOF
[Desktop Entry]
Type=Application
Name=Teams Notifications Daemon
Exec=systemctl --user start teams-notifications
Icon=teams
X-KDE-autostart-phase=2
X-KDE-autostart-after=panel
Hidden=false
AUTOEOF

# Refresh KDE cache
update-desktop-database ~/.local/share/applications/ 2>/dev/null || true
kbuildsycoca6 2>/dev/null || kbuildsycoca5 2>/dev/null || true
echo "  Done."

# --- Start ---
echo "[7/7] Starting daemon..."
systemctl --user restart teams-notifications
echo "  Done."

echo ""
echo "  ============================="
echo "  Installation complete!"
echo "  ============================="
echo ""
echo "  Next steps:"
echo ""
echo "  1. Load the Chrome extension:"
echo "     - Open chrome://extensions"
echo "     - Enable 'Developer mode' (top right)"
echo "     - Click 'Load unpacked' → select:"
echo "       $EXT_DIR"
echo ""
echo "  2. Launch Teams:"
echo "     - Search 'Microsoft Teams' in your app launcher"
echo "     - Or run: $PROJECT_DIR/scripts/launch-teams.sh"
echo ""
echo "  The tray icon starts automatically on login and"
echo "  whenever you launch Teams from the app menu."
echo ""
echo "  Config: $CONFIG_DIR/config.toml"
echo "  Logs:   journalctl --user -u teams-notifications -f"
echo ""
