#!/usr/bin/env bash
# Ensure daemon is running, then launch Teams with extension
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Start daemon if not running (try systemctl first, fallback to direct)
if ! systemctl --user is-active --quiet teams-notifications 2>/dev/null; then
    systemctl --user restart teams-notifications 2>/dev/null || \
        nohup "$PROJECT_DIR/daemon/.venv/bin/python" -m teams_notifications.main \
            > /dev/null 2>&1 &
    sleep 1
fi

google-chrome --app=https://teams.microsoft.com \
    --load-extension="$PROJECT_DIR/chrome-extension" &
