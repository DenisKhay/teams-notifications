# Teams Notifications for Linux

A system tray daemon + Chrome extension that makes Microsoft Teams notifications impossible to miss on Linux.

Teams runs as a PWA in Chrome, which means notifications are unreliable, there's no persistent badge in the system tray, and you have no idea if Teams is even running. This project fixes all of that.

## What it does

- **System tray icon** with unread badge count (green/red/yellow/gray states)
- **Desktop notifications** with sound when new messages arrive
- **Recurring reminders** every N minutes if you haven't read your messages, with escalating urgency
- **Auto-relaunch** if Teams gets accidentally closed
- **Working hours schedule** — notifications only during configured hours, gray icon outside
- **Configurable filters** — everything, mentions & DMs only, or DMs only, plus whitelist/blacklist
- **Settings GUI** — right-click the tray icon

## How it works

```
Chrome Extension                    Python Daemon (systemd)
┌─────────────────┐                ┌──────────────────────┐
│ Content script   │  native       │ Tray icon (PyQt6)    │
│ intercepts Teams │──messaging──→ │ Notifications        │
│ badges & notifs  │  host         │ Reminder scheduler   │
│                  │               │ Process watchdog     │
└─────────────────┘                │ Settings UI          │
                                   └──────────────────────┘
```

The Chrome extension runs in the Teams tab, intercepts badge updates and notification events, and forwards them through Chrome's native messaging to the daemon. The daemon manages the tray icon, fires OS notifications, and handles reminders.

## Requirements

- Linux with KDE Plasma (X11)
- Google Chrome
- Python 3.11+
- `notify-send` (libnotify)
- `xdotool`

### Install dependencies (Ubuntu/Debian)

```bash
sudo apt install python3 python3-venv libnotify-bin xdotool
```

### Install dependencies (Arch)

```bash
sudo pacman -S python libnotify xdotool
```

## Installation

```bash
git clone https://github.com/pinkynrg/teams-notifications.git
cd teams-notifications
./scripts/install.sh
```

The installer will:
1. Create a Python virtual environment and install dependencies
2. Install a systemd user service (auto-starts on login)
3. Register the Chrome native messaging host
4. Add a "Microsoft Teams" entry to your app launcher
5. Start the daemon

### Load the Chrome extension

After running the installer:

1. Open `chrome://extensions` in Chrome
2. Enable **Developer mode** (top right toggle)
3. Click **Load unpacked**
4. Select the `chrome-extension/` directory from this repo
5. **Refresh your Teams tab** (or launch Teams from the app launcher)

You only need to do this once. The extension persists across Chrome restarts.

## Usage

**Launch Teams** — search "Microsoft Teams" in your app launcher, or:

```bash
./scripts/launch-teams.sh
```

This opens Teams with the extension loaded and ensures the tray daemon is running.

**Tray icon states:**
- Green = connected, no unreads
- Red (with count) = unread messages
- Yellow = Teams is not running
- Gray = outside working hours

**Right-click the tray icon** for:
- Open Teams
- Snooze (15 min / 30 min / 1 hour)
- Settings
- Quit

**Left-click the tray icon** to see an unread summary popup.

## Configuration

Edit `~/.config/teams-notifications/config.toml` or use the Settings GUI (right-click tray icon).

```toml
[general]
check_interval_sec = 30          # how often to check for updates
reminder_interval_sec = 120      # reminder every N seconds when unreads exist
watchdog_interval_sec = 60       # how often to check if Teams is running
watchdog_grace_checks = 2        # miss N checks before alerting

[escalation]
enabled = true
tier2_after_reminders = 3        # persistent notifications after N reminders
tier3_after_reminders = 6        # alarm sound after N reminders
sound_file = "/usr/share/sounds/Oxygen-Im-Message-In.ogg"

[filters]
mode = "all"                     # "all", "mentions_and_dms", "dms_only"
whitelist = []                   # always notify: ["user:Display Name", "channel:General"]
blacklist = []                   # never notify: same format
exclude_bots = false

[schedule]
enabled = true
days = ["mon", "tue", "wed", "thu", "fri"]
start_hour = 9
start_minute = 0
end_hour = 18
end_minute = 0
```

Changes require a daemon restart: `systemctl --user restart teams-notifications`

## Managing the daemon

```bash
# Status
systemctl --user status teams-notifications

# Restart (picks up config changes)
systemctl --user restart teams-notifications

# Stop
systemctl --user stop teams-notifications

# Live logs
journalctl --user -u teams-notifications -f
```

## Uninstall

```bash
./scripts/uninstall.sh
```

Then remove the extension from `chrome://extensions`.

## Project structure

```
teams-notifications/
├── chrome-extension/        # Chrome extension (MV3)
│   ├── manifest.json
│   ├── content-script.js    # Intercepts Teams badges/notifications
│   ├── relay.js             # Bridges page → extension
│   └── service-worker.js    # Forwards to native host
├── daemon/                  # Python daemon
│   ├── src/teams_notifications/
│   │   ├── main.py          # Entry point, wires everything
│   │   ├── tray.py          # System tray icon (PyQt6)
│   │   ├── notifications.py # OS notifications via notify-send
│   │   ├── reminders.py     # Reminder scheduler with escalation
│   │   ├── watchdog.py      # Teams process detection
│   │   ├── config.py        # TOML config management
│   │   ├── state.py         # Unread state and filters
│   │   ├── settings_ui.py   # Settings dialog (PyQt6)
│   │   ├── socket_server.py # Unix socket for native host
│   │   └── native_host.py   # Chrome native messaging bridge
│   └── tests/
├── scripts/
│   ├── install.sh
│   ├── uninstall.sh
│   └── launch-teams.sh
└── systemd/
    └── teams-notifications.service
```

## License

MIT
