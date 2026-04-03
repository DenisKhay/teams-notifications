# Teams Notifications — Design Spec

## Problem

Microsoft Teams as a PWA has unreliable notifications on Linux. Messages are easy to miss — no persistent tray icon, no reminders, no way to know if Teams isn't even running.

## Solution

A three-layer notification system: Chrome Extension + Native Messaging Host + Python Daemon. Two independent data sources (Microsoft Graph API + PWA interception) ensure maximum reliability.

## Target Environment

- Linux (KDE Plasma, X11)
- Chrome browser with Teams PWA installed
- Python 3.11+
- Microsoft Entra ID account (LIFE DATA LAB, LLC tenant)

---

## Architecture

### Layer 1: Chrome Extension (Manifest V3)

**Content Script (MAIN world)** — injected into `https://teams.microsoft.com/*`:
- Monkey-patches `navigator.setAppBadge(count)` to capture unread counts in real-time
- Wraps `Notification` constructor and `ServiceWorkerRegistration.prototype.showNotification` to intercept every notification Teams creates (title, body, icon, tag)
- MutationObserver on `document.title` as fallback (Teams puts `(3)` in title for unreads)
- Forwards all events to the service worker via `chrome.runtime.sendMessage`

**Service Worker** — extension background:
- Receives events from content script
- Forwards to native messaging host via `chrome.runtime.connectNative("com.teams_notifications.host")`
- Manages extension badge icon (shows unread count on toolbar icon)
- Handles extension popup UI for configuration

**Popup UI** — configuration panel:
- Enable/disable notification sources (Graph API, PWA interception)
- Notification mode selector + filter configuration
- Reminder interval setting
- Graph API auth status + login button (triggers OAuth2 PKCE flow)

### Layer 2: Native Messaging Host

A thin Python bridge — its only job is to shuttle JSON between Chrome and the daemon.

- Registered at `~/.config/google-chrome/NativeMessagingHosts/com.teams_notifications.host.json`
- Speaks Chrome's native messaging protocol: 4-byte length prefix + JSON on stdin/stdout
- Connects to the daemon via Unix socket at `/run/user/$UID/teams-notifications.sock`
- Stateless — no logic, no config, just forwards messages both directions
- Starts on demand when extension calls `connectNative()`, dies when extension disconnects

**Message format (extension -> daemon):**
```json
{"type": "badge", "count": 5, "timestamp": 1712345678}
{"type": "notification", "title": "John Doe", "body": "Hey, are you free?", "chat_id": "...", "timestamp": 1712345678}
{"type": "title_change", "title": "(3) Microsoft Teams", "timestamp": 1712345678}
```

**Message format (daemon -> extension):**
```json
{"type": "config_update", "filters": {...}, "interval_sec": 300}
{"type": "ack"}
```

### Layer 3: Daemon (systemd user service)

Python + PyQt6, runs as `systemctl --user` service.

#### 3.1 Graph API Poller
- OAuth2 token stored in KDE Wallet via `keyring` library
- Polls `/me/chats?$expand=lastMessagePreview` and `/me/teams/{id}/channels` every 30-60s (configurable)
- Tracks unread counts per chat/channel, detects new messages since last check
- Token refresh handled automatically via MSAL library

#### 3.2 Tray Icon (PyQt6 QSystemTrayIcon)
- Green icon = no unreads
- Red icon with count badge = unread messages (dynamically rendered)
- Yellow warning icon = Teams not running
- Left-click: shows summary popup (who messaged, which channels)
- Right-click context menu: Open Teams, Snooze, Settings, Quit
- Tooltip shows summary: "5 unread — 2 DMs, 3 channels"

#### 3.3 Reminder Scheduler
- When unreads exist and aren't acknowledged, fires `notify-send` at configured interval
- Escalation tiers (all configurable):
  - Tier 1 (default): normal notification, auto-dismiss after 10s
  - Tier 2 (after N reminders): critical urgency, persistent (no auto-dismiss)
  - Tier 3 (after M reminders): adds sound via `paplay`/`pw-play`
- Resets when unread count drops to 0

#### 3.4 Process Watchdog
- Checks for Teams PWA process every 60s (configurable)
- Looks for chrome/chromium process with `--app-id` matching Teams PWA
- If Teams not detected for N consecutive checks -> fires "Teams is not running!" notification
- Same reminder/escalation system as unread notifications
- Separate configurable interval from unread reminders

#### 3.5 Socket Server
- Listens on `/run/user/$UID/teams-notifications.sock`
- Receives real-time events from native messaging host
- Merges with Graph API data (see Data Flow section)

#### 3.6 Config Manager
- TOML config file at `~/.config/teams-notifications/config.toml`
- Hot-reload on file change (inotify)
- All intervals, filters, escalation tiers, and notification preferences configurable
- Settings GUI writes to the same TOML file

---

## Configuration

### GUI Settings Window

Accessible from tray right-click -> Settings. PyQt6 dialog with tabs:

**Notifications tab:**
- Notification Mode (radio buttons):
  - "Everything" — all unreads
  - "Mentions & DMs only" — filters out channel chatter, only @mentions and direct messages
  - "DMs only" — only direct messages
- Independent filters (applied on top of mode):
  - Whitelist: always notify from these people/channels regardless of mode
  - Blacklist: never notify from these people/channels regardless of mode
  - Exclude bots toggle
- Filter priority: blacklist > whitelist > mode

**Reminders tab:**
- Slider: reminder interval (1-60 min)
- Escalation on/off + tier thresholds
- Sound picker

**Watchdog tab:**
- "Alert if Teams not running" toggle
- Check interval slider
- Grace period slider

**About tab:**
- Graph API auth status, re-login button
- PWA interception status (connected/disconnected)

### TOML Config File

Backing store at `~/.config/teams-notifications/config.toml`:

```toml
[general]
check_interval_sec = 30
reminder_interval_sec = 300
watchdog_interval_sec = 60
watchdog_grace_checks = 2

[escalation]
enabled = true
tier2_after_reminders = 3
tier3_after_reminders = 6
sound_file = "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"

[filters]
mode = "all"                     # "all", "mentions_and_dms", "dms_only"
whitelist = []                   # entries: "user:email@example.com" or "channel:ChannelName"
blacklist = []                   # same format as whitelist
exclude_bots = false

[tray]
icon_theme = "default"
show_count_badge = true

[notifications]
show_message_preview = true
max_preview_length = 100
```

---

## Data Flow & State Merging

### Two data paths

**Real-time path (PWA interception):**
- Content script fires events instantly when Teams renders a notification or updates the badge
- Daemon updates internal state immediately — tray icon changes within 1 second

**Polling path (Graph API):**
- Every 30-60s, daemon fetches full unread state from Graph API
- This is the authoritative source — catches anything PWA interception missed

### Merging rules

1. Real-time event arrives -> update state immediately, reset reminder timer for that chat
2. Graph API poll arrives -> overwrite full state with API response (it's authoritative)
3. If Graph API shows unreads that PWA didn't report -> fire notification for the new ones
4. If Graph API shows 0 unreads but PWA reported some -> trust Graph API, clear state
5. If Graph API is unreachable -> fall back to PWA-only state, show warning in tray tooltip

### Reminder timer logic

- Timer starts when unreads > 0
- Each reminder fires a notification with current unread summary
- Timer resets when: user reads messages (count drops), or user clicks "snooze" in notification
- Snooze: configurable duration (15min, 30min, 1hr, until next message)

---

## OAuth2 Authentication

### First-time setup

1. User registers an app in Microsoft Entra ID (setup script guides through it)
2. App config: redirect URI `http://localhost:8400/callback`, type "Public client/native"
3. API permissions (delegated): `Chat.Read`, `ChannelMessage.Read.All`, `User.Read`, `Presence.Read`
4. User copies Client ID + Tenant ID into settings GUI (or setup script writes to config)

### Auth flow

1. User clicks "Login" in tray settings -> daemon opens browser to Microsoft login
2. OAuth2 PKCE authorization code flow -> redirect to `localhost:8400/callback`
3. Daemon captures the code, exchanges for tokens
4. Access token + refresh token stored in KDE Wallet via `keyring` library
5. Tokens refresh automatically via MSAL — user shouldn't need to re-auth unless revoked

### Admin consent fallback

- If org admin hasn't approved required scopes, daemon detects `AADSTS65001` error
- Shows notification: "Your org admin needs to approve this app. Switch to PWA-only mode or request admin consent."
- Falls back to PWA interception gracefully

---

## Project Structure

```
teams-notifications/
├── chrome-extension/
│   ├── manifest.json
│   ├── content-script.js
│   ├── service-worker.js
│   ├── popup/
│   │   ├── popup.html
│   │   ├── popup.js
│   │   └── popup.css
│   └── icons/
│
├── daemon/
│   ├── pyproject.toml
│   ├── src/
│   │   └── teams_notifications/
│   │       ├── __init__.py
│   │       ├── main.py
│   │       ├── tray.py
│   │       ├── settings_ui.py
│   │       ├── graph_api.py
│   │       ├── state.py
│   │       ├── reminders.py
│   │       ├── watchdog.py
│   │       ├── socket_server.py
│   │       ├── config.py
│   │       └── native_host.py
│   └── resources/
│       ├── icons/
│       └── sounds/
│
├── scripts/
│   ├── install.sh
│   ├── setup-azure.sh
│   └── uninstall.sh
│
├── systemd/
│   └── teams-notifications.service
│
└── README.md
```

## Auth Token Storage

Tokens are stored in KDE Wallet via the `keyring` library, not in the TOML config file. The daemon manages the auth lifecycle internally. The TOML `[auth]` section (if present) only holds `client_id` and `tenant_id` — never tokens.

## Dependencies

- Python 3.11+
- PyQt6 (tray icon, settings UI)
- MSAL (Microsoft auth)
- httpx (async HTTP for Graph API)
- keyring (token storage in KDE Wallet)
- tomli / tomllib (config parsing)

## Install Flow

1. `./scripts/install.sh` — creates Python venv, installs deps, registers native messaging host JSON, installs + enables systemd user service
2. Load `chrome-extension/` as unpacked extension in `chrome://extensions`
3. `./scripts/setup-azure.sh` — opens Entra ID portal, prompts for Client ID/Tenant ID, triggers OAuth login
4. Done — tray icon appears, notifications start flowing
