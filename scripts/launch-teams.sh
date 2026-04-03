#!/usr/bin/env bash
# Ensure daemon is running, then launch Teams with extension
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

systemctl --user restart teams-notifications
sleep 1

google-chrome --app=https://teams.microsoft.com \
    --load-extension="$PROJECT_DIR/chrome-extension" &
