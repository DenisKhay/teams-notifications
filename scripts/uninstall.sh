#!/usr/bin/env bash
set -euo pipefail

echo "=== Uninstalling Teams Notifications ==="

systemctl --user stop teams-notifications.service 2>/dev/null || true
systemctl --user disable teams-notifications.service 2>/dev/null || true
rm -f ~/.config/systemd/user/teams-notifications.service
systemctl --user daemon-reload
rm -f ~/.config/autostart/teams-notifications.desktop

echo "Config preserved at ~/.config/teams-notifications/"
echo "=== Uninstall complete ==="
