#!/usr/bin/env bash
# Ensure daemon is running, then launch Teams with extension
systemctl --user start teams-notifications 2>/dev/null || true
exec google-chrome --app=https://teams.microsoft.com \
    --load-extension="$(dirname "$(dirname "$0")")/chrome-extension"
