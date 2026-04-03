#!/usr/bin/env bash
set -euo pipefail

echo "=== Uninstalling Teams Notifications ==="

systemctl --user stop teams-notifications.service 2>/dev/null || true
systemctl --user disable teams-notifications.service 2>/dev/null || true
rm -f ~/.config/systemd/user/teams-notifications.service
systemctl --user daemon-reload

rm -f ~/.config/autostart/teams-notifications.desktop
rm -f ~/.local/share/applications/teams-notifications.desktop
rm -f ~/.config/google-chrome/NativeMessagingHosts/com.teams_notifications.host.json

echo "Config preserved at ~/.config/teams-notifications/"
echo "To remove config too: rm -rf ~/.config/teams-notifications/"
echo ""
echo "=== Uninstall complete ==="
echo "Remember to remove the extension from chrome://extensions"
