#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DAEMON_DIR="$(dirname "$SCRIPT_DIR")/daemon"

echo "=== Azure AD App Setup ==="
echo ""
echo "1. Open: https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade"
echo "2. Click 'New registration', name: Teams Notifications"
echo "3. Redirect URI: Public client/native — http://localhost"
echo "4. Authentication > Allow public client flows > Yes"
echo "5. API permissions: Chat.Read, ChannelMessage.Read.All, User.Read, Presence.Read, Team.ReadBasic.All, Channel.ReadBasic.All"
echo ""

read -rp "Application (client) ID: " CLIENT_ID
read -rp "Directory (tenant) ID: " TENANT_ID

cd "$DAEMON_DIR"
source .venv/bin/activate

python3 -c "
from teams_notifications.config import Config, DEFAULT_CONFIG_PATH
config = Config.from_file(DEFAULT_CONFIG_PATH)
config.client_id = '${CLIENT_ID}'
config.tenant_id = '${TENANT_ID}'
config.save(DEFAULT_CONFIG_PATH)
print('Config saved.')
"

echo ""
echo "Authenticating..."
python3 -c "
import asyncio
from teams_notifications.config import Config, DEFAULT_CONFIG_PATH
from teams_notifications.graph_api import GraphClient

async def do_auth():
    config = Config.from_file(DEFAULT_CONFIG_PATH)
    client = GraphClient(config)
    token = await client.authenticate_interactive()
    me = await client.get_my_user_id(token)
    print(f'Authenticated as user ID: {me}')
    await client.close()

asyncio.run(do_auth())
"

echo ""
echo "=== Setup complete! ==="
echo "Start: systemctl --user start teams-notifications"
