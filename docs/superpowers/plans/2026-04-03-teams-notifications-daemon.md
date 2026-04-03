# Teams Notifications Daemon — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python daemon that polls Microsoft Graph API for Teams unread messages, shows a KDE system tray icon with badge count, sends persistent OS notifications with configurable reminders, watches for Teams PWA process, and exposes a Unix socket for future Chrome extension integration.

**Architecture:** Single Python process using PyQt6 for tray icon + settings GUI, qasync for async event loop integration, MSAL for Graph API auth, httpx for HTTP requests, and a Unix socket server for external data sources. Configuration via TOML with hot-reload.

**Tech Stack:** Python 3.11+, PyQt6, qasync, msal, httpx, keyring, tomli

---

## File Structure

```
daemon/
├── pyproject.toml                          # Project metadata + dependencies
├── src/
│   └── teams_notifications/
│       ├── __init__.py                     # Package init, version
│       ├── main.py                         # Entry point: QApp + qasync loop + component wiring
│       ├── config.py                       # TOML config parsing, defaults, hot-reload
│       ├── state.py                        # Unread state tracking, merge logic, filters
│       ├── graph_api.py                    # MSAL auth + Graph API polling
│       ├── tray.py                         # QSystemTrayIcon, badge rendering, context menu, popup
│       ├── notifications.py                # OS notification dispatch via libnotify/notify-send
│       ├── reminders.py                    # Reminder timer + escalation logic
│       ├── watchdog.py                     # Teams PWA process detection
│       ├── socket_server.py                # Unix socket server for native messaging host
│       └── settings_ui.py                  # Settings QDialog with tabs
├── tests/
│   ├── conftest.py                         # Shared fixtures
│   ├── test_config.py
│   ├── test_state.py
│   ├── test_graph_api.py
│   ├── test_reminders.py
│   └── test_watchdog.py
├── resources/
│   └── icons/                              # Will contain generated SVG icons
scripts/
├── install.sh                              # Full install: venv, deps, systemd, autostart
├── setup-azure.sh                          # Guided Azure AD app registration
└── uninstall.sh
systemd/
└── teams-notifications.service             # systemd user unit
```

---

### Task 1: Project Scaffolding

**Files:**
- Create: `daemon/pyproject.toml`
- Create: `daemon/src/teams_notifications/__init__.py`
- Create: `daemon/tests/conftest.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "teams-notifications"
version = "0.1.0"
description = "KDE tray daemon for Microsoft Teams notifications"
requires-python = ">=3.11"
dependencies = [
    "PyQt6>=6.6",
    "qasync>=0.27",
    "msal>=1.28",
    "httpx>=0.27",
    "keyring>=25.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-qt>=4.3",
]

[project.scripts]
teams-notifications = "teams_notifications.main:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 2: Create package init**

```python
# daemon/src/teams_notifications/__init__.py
__version__ = "0.1.0"
```

- [ ] **Step 3: Create test conftest**

```python
# daemon/tests/conftest.py
import sys
from pathlib import Path

# Ensure src is on the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
```

- [ ] **Step 4: Create venv and install deps**

Run:
```bash
cd daemon
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

- [ ] **Step 5: Verify setup**

Run:
```bash
cd daemon
source .venv/bin/activate
python -c "import teams_notifications; print(teams_notifications.__version__)"
pytest --co  # collect tests (should find 0 tests, no errors)
```

Expected: prints `0.1.0`, pytest collects 0 tests with no import errors.

- [ ] **Step 6: Commit**

```bash
git add daemon/
git commit -m "Scaffold daemon project with pyproject.toml and package structure"
```

---

### Task 2: Configuration Module

**Files:**
- Create: `daemon/src/teams_notifications/config.py`
- Create: `daemon/tests/test_config.py`

- [ ] **Step 1: Write failing tests for config loading**

```python
# daemon/tests/test_config.py
import tempfile
from pathlib import Path

from teams_notifications.config import Config, DEFAULT_CONFIG_PATH


def test_default_config_values():
    config = Config()
    assert config.check_interval_sec == 30
    assert config.reminder_interval_sec == 300
    assert config.watchdog_interval_sec == 60
    assert config.watchdog_grace_checks == 2
    assert config.escalation_enabled is True
    assert config.escalation_tier2_after == 3
    assert config.escalation_tier3_after == 6
    assert config.filter_mode == "all"
    assert config.whitelist == []
    assert config.blacklist == []
    assert config.exclude_bots is False
    assert config.show_count_badge is True
    assert config.show_message_preview is True
    assert config.max_preview_length == 100


def test_load_from_toml_file():
    toml_content = """
[general]
check_interval_sec = 15
reminder_interval_sec = 120

[filters]
mode = "mentions_and_dms"
whitelist = ["user:alice@example.com"]
blacklist = ["channel:Random"]
exclude_bots = true
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(toml_content)
        f.flush()
        config = Config.from_file(Path(f.name))

    assert config.check_interval_sec == 15
    assert config.reminder_interval_sec == 120
    assert config.filter_mode == "mentions_and_dms"
    assert config.whitelist == ["user:alice@example.com"]
    assert config.blacklist == ["channel:Random"]
    assert config.exclude_bots is True
    # Unspecified values keep defaults
    assert config.watchdog_interval_sec == 60


def test_load_missing_file_returns_defaults():
    config = Config.from_file(Path("/nonexistent/path/config.toml"))
    assert config.check_interval_sec == 30


def test_save_and_reload(tmp_path):
    config = Config()
    config.filter_mode = "dms_only"
    config.reminder_interval_sec = 60
    path = tmp_path / "config.toml"
    config.save(path)

    reloaded = Config.from_file(path)
    assert reloaded.filter_mode == "dms_only"
    assert reloaded.reminder_interval_sec == 60


def test_auth_properties():
    config = Config()
    config.client_id = "test-client-id"
    config.tenant_id = "test-tenant-id"
    assert config.client_id == "test-client-id"
    assert config.tenant_id == "test-tenant-id"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd daemon && source .venv/bin/activate && pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'teams_notifications.config'`

- [ ] **Step 3: Implement config module**

```python
# daemon/src/teams_notifications/config.py
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "teams-notifications" / "config.toml"


@dataclass
class Config:
    # [general]
    check_interval_sec: int = 30
    reminder_interval_sec: int = 300
    watchdog_interval_sec: int = 60
    watchdog_grace_checks: int = 2

    # [escalation]
    escalation_enabled: bool = True
    escalation_tier2_after: int = 3
    escalation_tier3_after: int = 6
    sound_file: str = "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"

    # [filters]
    filter_mode: str = "all"  # "all", "mentions_and_dms", "dms_only"
    whitelist: list[str] = field(default_factory=list)
    blacklist: list[str] = field(default_factory=list)
    exclude_bots: bool = False

    # [tray]
    show_count_badge: bool = True

    # [notifications]
    show_message_preview: bool = True
    max_preview_length: int = 100

    # [auth]
    client_id: str = ""
    tenant_id: str = ""

    @classmethod
    def from_file(cls, path: Path) -> Config:
        config = cls()
        if not path.exists():
            return config
        with open(path, "rb") as f:
            data = tomllib.load(f)
        config._apply_toml(data)
        return config

    def _apply_toml(self, data: dict[str, Any]) -> None:
        mapping = {
            ("general", "check_interval_sec"): "check_interval_sec",
            ("general", "reminder_interval_sec"): "reminder_interval_sec",
            ("general", "watchdog_interval_sec"): "watchdog_interval_sec",
            ("general", "watchdog_grace_checks"): "watchdog_grace_checks",
            ("escalation", "enabled"): "escalation_enabled",
            ("escalation", "tier2_after_reminders"): "escalation_tier2_after",
            ("escalation", "tier3_after_reminders"): "escalation_tier3_after",
            ("escalation", "sound_file"): "sound_file",
            ("filters", "mode"): "filter_mode",
            ("filters", "whitelist"): "whitelist",
            ("filters", "blacklist"): "blacklist",
            ("filters", "exclude_bots"): "exclude_bots",
            ("tray", "show_count_badge"): "show_count_badge",
            ("notifications", "show_message_preview"): "show_message_preview",
            ("notifications", "max_preview_length"): "max_preview_length",
            ("auth", "client_id"): "client_id",
            ("auth", "tenant_id"): "tenant_id",
        }
        for (section, key), attr in mapping.items():
            if section in data and key in data[section]:
                setattr(self, attr, data[section][key])

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "[general]",
            f"check_interval_sec = {self.check_interval_sec}",
            f"reminder_interval_sec = {self.reminder_interval_sec}",
            f"watchdog_interval_sec = {self.watchdog_interval_sec}",
            f"watchdog_grace_checks = {self.watchdog_grace_checks}",
            "",
            "[escalation]",
            f"enabled = {_to_toml_bool(self.escalation_enabled)}",
            f"tier2_after_reminders = {self.escalation_tier2_after}",
            f"tier3_after_reminders = {self.escalation_tier3_after}",
            f'sound_file = "{self.sound_file}"',
            "",
            "[filters]",
            f'mode = "{self.filter_mode}"',
            f"whitelist = {_to_toml_list(self.whitelist)}",
            f"blacklist = {_to_toml_list(self.blacklist)}",
            f"exclude_bots = {_to_toml_bool(self.exclude_bots)}",
            "",
            "[tray]",
            f"show_count_badge = {_to_toml_bool(self.show_count_badge)}",
            "",
            "[notifications]",
            f"show_message_preview = {_to_toml_bool(self.show_message_preview)}",
            f"max_preview_length = {self.max_preview_length}",
            "",
            "[auth]",
            f'client_id = "{self.client_id}"',
            f'tenant_id = "{self.tenant_id}"',
        ]
        path.write_text("\n".join(lines) + "\n")


def _to_toml_bool(val: bool) -> str:
    return "true" if val else "false"


def _to_toml_list(val: list[str]) -> str:
    if not val:
        return "[]"
    items = ", ".join(f'"{v}"' for v in val)
    return f"[{items}]"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd daemon && source .venv/bin/activate && pytest tests/test_config.py -v`
Expected: all 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add daemon/src/teams_notifications/config.py daemon/tests/test_config.py
git commit -m "Add config module with TOML parsing, defaults, and save/load"
```

---

### Task 3: State Management

**Files:**
- Create: `daemon/src/teams_notifications/state.py`
- Create: `daemon/tests/test_state.py`

- [ ] **Step 1: Write failing tests**

```python
# daemon/tests/test_state.py
from datetime import datetime, timezone

from teams_notifications.state import (
    ChatInfo,
    ChannelMessageInfo,
    UnreadState,
    FilterConfig,
    filter_notifications,
)


def _utc(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def test_unread_state_total_count():
    state = UnreadState()
    state.chats = {
        "chat1": ChatInfo(
            chat_id="chat1",
            chat_type="oneOnOne",
            sender_name="Alice",
            sender_id="user-id-alice",
            last_message="Hello",
            last_message_time=_utc(2026, 4, 3, 10),
            last_read_time=_utc(2026, 4, 3, 9),
        ),
        "chat2": ChatInfo(
            chat_id="chat2",
            chat_type="group",
            sender_name="Bob",
            sender_id="user-id-bob",
            last_message="Hey",
            last_message_time=_utc(2026, 4, 3, 11),
            last_read_time=_utc(2026, 4, 3, 10),
        ),
    }
    state.channel_mentions = [
        ChannelMessageInfo(
            team_name="Engineering",
            channel_name="General",
            sender_name="Carol",
            message_preview="@Denis check this",
            timestamp=_utc(2026, 4, 3, 12),
        ),
    ]
    assert state.total_unread == 3
    assert state.dm_count == 1
    assert state.group_count == 1
    assert state.mention_count == 1


def test_unread_state_is_empty():
    state = UnreadState()
    assert state.is_empty is True
    assert state.total_unread == 0


def test_merge_replaces_state():
    old = UnreadState()
    old.chats = {
        "chat1": ChatInfo(
            chat_id="chat1", chat_type="oneOnOne", sender_name="Alice",
            sender_id="user-id-alice", last_message="Old",
            last_message_time=_utc(2026, 4, 3, 10),
            last_read_time=_utc(2026, 4, 3, 9),
        ),
    }
    new = UnreadState()
    # new has no chats — means user read everything
    merged = new  # Graph API response replaces state
    assert merged.is_empty is True


def test_filter_all_mode():
    chats = [
        ChatInfo(chat_id="c1", chat_type="oneOnOne", sender_name="Alice",
                 sender_id="user-id-alice", last_message="Hi",
                 last_message_time=_utc(2026, 4, 3, 10),
                 last_read_time=_utc(2026, 4, 3, 9)),
    ]
    mentions = [
        ChannelMessageInfo(team_name="T", channel_name="General",
                           sender_name="Bob", message_preview="@Denis",
                           timestamp=_utc(2026, 4, 3, 11)),
    ]
    fc = FilterConfig(mode="all", whitelist=[], blacklist=[], exclude_bots=False)
    filtered_chats, filtered_mentions = filter_notifications(chats, mentions, fc)
    assert len(filtered_chats) == 1
    assert len(filtered_mentions) == 1


def test_filter_mentions_and_dms_only():
    chats = [
        ChatInfo(chat_id="c1", chat_type="oneOnOne", sender_name="Alice",
                 sender_id="user-id-alice", last_message="Hi",
                 last_message_time=_utc(2026, 4, 3, 10),
                 last_read_time=_utc(2026, 4, 3, 9)),
        ChatInfo(chat_id="c2", chat_type="group", sender_name="Bob",
                 sender_id="user-id-bob", last_message="Hey team",
                 last_message_time=_utc(2026, 4, 3, 10),
                 last_read_time=_utc(2026, 4, 3, 9)),
    ]
    mentions = [
        ChannelMessageInfo(team_name="T", channel_name="General",
                           sender_name="Carol", message_preview="@Denis",
                           timestamp=_utc(2026, 4, 3, 11)),
    ]
    fc = FilterConfig(mode="mentions_and_dms", whitelist=[], blacklist=[], exclude_bots=False)
    filtered_chats, filtered_mentions = filter_notifications(chats, mentions, fc)
    assert len(filtered_chats) == 1  # only DMs
    assert filtered_chats[0].chat_type == "oneOnOne"
    assert len(filtered_mentions) == 1  # mentions pass through


def test_filter_blacklist_overrides():
    chats = [
        ChatInfo(chat_id="c1", chat_type="oneOnOne", sender_name="Alice",
                 sender_id="user-id-alice", last_message="Hi",
                 last_message_time=_utc(2026, 4, 3, 10),
                 last_read_time=_utc(2026, 4, 3, 9)),
    ]
    fc = FilterConfig(mode="all", whitelist=[], blacklist=["user:Alice"], exclude_bots=False)
    filtered_chats, filtered_mentions = filter_notifications(chats, [], fc)
    assert len(filtered_chats) == 0  # blacklisted


def test_filter_whitelist_overrides_mode():
    chats = [
        ChatInfo(chat_id="c1", chat_type="group", sender_name="Alice",
                 sender_id="user-id-alice", last_message="Hey",
                 last_message_time=_utc(2026, 4, 3, 10),
                 last_read_time=_utc(2026, 4, 3, 9)),
    ]
    # "dms_only" would filter out group chats, but whitelist overrides
    fc = FilterConfig(mode="dms_only", whitelist=["user:Alice"], blacklist=[], exclude_bots=False)
    filtered_chats, filtered_mentions = filter_notifications(chats, [], fc)
    assert len(filtered_chats) == 1  # whitelisted, passes despite mode
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd daemon && source .venv/bin/activate && pytest tests/test_state.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement state module**

```python
# daemon/src/teams_notifications/state.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ChatInfo:
    chat_id: str
    chat_type: str  # "oneOnOne", "group", "meeting"
    sender_name: str
    sender_id: str  # Azure AD user ID (GUID) — Graph API doesn't return email in chat preview
    last_message: str
    last_message_time: datetime
    last_read_time: datetime


@dataclass
class ChannelMessageInfo:
    team_name: str
    channel_name: str
    sender_name: str
    message_preview: str
    timestamp: datetime


@dataclass
class UnreadState:
    chats: dict[str, ChatInfo] = field(default_factory=dict)
    channel_mentions: list[ChannelMessageInfo] = field(default_factory=list)
    last_updated: datetime | None = None

    @property
    def total_unread(self) -> int:
        return len(self.chats) + len(self.channel_mentions)

    @property
    def dm_count(self) -> int:
        return sum(1 for c in self.chats.values() if c.chat_type == "oneOnOne")

    @property
    def group_count(self) -> int:
        return sum(1 for c in self.chats.values() if c.chat_type in ("group", "meeting"))

    @property
    def mention_count(self) -> int:
        return len(self.channel_mentions)

    @property
    def is_empty(self) -> bool:
        return self.total_unread == 0

    def summary(self) -> str:
        if self.is_empty:
            return "No unread messages"
        parts = []
        if self.dm_count:
            parts.append(f"{self.dm_count} DM{'s' if self.dm_count != 1 else ''}")
        if self.group_count:
            parts.append(f"{self.group_count} group")
        if self.mention_count:
            parts.append(f"{self.mention_count} mention{'s' if self.mention_count != 1 else ''}")
        return f"{self.total_unread} unread — {', '.join(parts)}"


@dataclass
class FilterConfig:
    mode: str  # "all", "mentions_and_dms", "dms_only"
    whitelist: list[str]
    blacklist: list[str]
    exclude_bots: bool


def _matches_filter(name: str, channel: str, entries: list[str]) -> bool:
    """Check if a sender name or channel matches any filter entry.
    Entries use 'user:Display Name' or 'channel:ChannelName' format.
    """
    for entry in entries:
        if entry.startswith("user:") and entry[5:].lower() == name.lower():
            return True
        if entry.startswith("channel:") and entry[8:].lower() == channel.lower():
            return True
    return False


def filter_notifications(
    chats: list[ChatInfo],
    mentions: list[ChannelMessageInfo],
    fc: FilterConfig,
) -> tuple[list[ChatInfo], list[ChannelMessageInfo]]:
    filtered_chats = []
    for chat in chats:
        # Blacklist always wins
        if _matches_filter(chat.sender_name, "", fc.blacklist):
            continue
        # Whitelist overrides mode
        if _matches_filter(chat.sender_name, "", fc.whitelist):
            filtered_chats.append(chat)
            continue
        # Apply mode filter
        if fc.mode == "all":
            filtered_chats.append(chat)
        elif fc.mode == "mentions_and_dms":
            if chat.chat_type == "oneOnOne":
                filtered_chats.append(chat)
        elif fc.mode == "dms_only":
            if chat.chat_type == "oneOnOne":
                filtered_chats.append(chat)

    filtered_mentions = []
    for mention in mentions:
        if _matches_filter("", mention.channel_name, fc.blacklist):
            continue
        if _matches_filter("", mention.channel_name, fc.whitelist):
            filtered_mentions.append(mention)
            continue
        # Mentions always pass in "all" and "mentions_and_dms" modes
        if fc.mode in ("all", "mentions_and_dms"):
            filtered_mentions.append(mention)
        # "dms_only" filters out channel mentions (unless whitelisted above)

    return filtered_chats, filtered_mentions
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd daemon && source .venv/bin/activate && pytest tests/test_state.py -v`
Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add daemon/src/teams_notifications/state.py daemon/tests/test_state.py
git commit -m "Add state management with unread tracking and filter logic"
```

---

### Task 4: Graph API Authentication

**Files:**
- Create: `daemon/src/teams_notifications/graph_api.py`
- Create: `daemon/tests/test_graph_api.py`

- [ ] **Step 1: Write failing tests for auth and response parsing**

```python
# daemon/tests/test_graph_api.py
from teams_notifications.graph_api import (
    parse_chats_response,
    parse_channel_messages,
)


def test_parse_chats_response_extracts_unread():
    response = {
        "value": [
            {
                "id": "chat1",
                "chatType": "oneOnOne",
                "viewpoint": {
                    "lastMessageReadDateTime": "2026-04-03T09:00:00Z",
                },
                "lastMessagePreview": {
                    "createdDateTime": "2026-04-03T10:00:00Z",
                    "body": {"content": "Hello there"},
                    "from": {
                        "user": {
                            "id": "user-id-1",
                            "displayName": "Alice Smith",
                            "userIdentityType": "aadUser",
                        }
                    },
                },
            },
            {
                "id": "chat2",
                "chatType": "group",
                "viewpoint": {
                    "lastMessageReadDateTime": "2026-04-03T11:00:00Z",
                },
                "lastMessagePreview": {
                    "createdDateTime": "2026-04-03T10:00:00Z",
                    "body": {"content": "Old message"},
                    "from": {
                        "user": {
                            "id": "user-id-2",
                            "displayName": "Bob",
                            "userIdentityType": "aadUser",
                        }
                    },
                },
            },
        ]
    }
    chats = parse_chats_response(response)
    # Only chat1 is unread (message time > read time)
    assert len(chats) == 1
    assert chats[0].chat_id == "chat1"
    assert chats[0].sender_name == "Alice Smith"
    assert chats[0].last_message == "Hello there"
    assert chats[0].chat_type == "oneOnOne"


def test_parse_chats_response_handles_no_viewpoint():
    response = {
        "value": [
            {
                "id": "chat1",
                "chatType": "oneOnOne",
                "lastMessagePreview": {
                    "createdDateTime": "2026-04-03T10:00:00Z",
                    "body": {"content": "Hi"},
                    "from": {
                        "user": {
                            "id": "uid",
                            "displayName": "Alice",
                            "userIdentityType": "aadUser",
                        }
                    },
                },
            },
        ]
    }
    chats = parse_chats_response(response)
    # No viewpoint means never read -> unread
    assert len(chats) == 1


def test_parse_channel_messages_detects_mentions():
    my_user_id = "my-id-123"
    messages = [
        {
            "id": "msg1",
            "createdDateTime": "2026-04-03T12:00:00Z",
            "body": {"content": "<p>Hey <at>Denis</at></p>"},
            "from": {
                "user": {
                    "id": "other-user",
                    "displayName": "Carol",
                    "userIdentityType": "aadUser",
                }
            },
            "mentions": [
                {
                    "id": 0,
                    "mentionText": "Denis",
                    "mentioned": {
                        "user": {
                            "id": "my-id-123",
                            "displayName": "Denis K",
                        }
                    },
                }
            ],
        },
        {
            "id": "msg2",
            "createdDateTime": "2026-04-03T12:01:00Z",
            "body": {"content": "No mention here"},
            "from": {
                "user": {
                    "id": "other-user",
                    "displayName": "Carol",
                    "userIdentityType": "aadUser",
                }
            },
            "mentions": [],
        },
    ]
    result = parse_channel_messages(
        messages, my_user_id, team_name="Engineering", channel_name="General"
    )
    assert len(result) == 1
    assert result[0].sender_name == "Carol"
    assert result[0].channel_name == "General"


def test_parse_chats_response_empty():
    response = {"value": []}
    chats = parse_chats_response(response)
    assert len(chats) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd daemon && source .venv/bin/activate && pytest tests/test_graph_api.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement graph_api module**

```python
# daemon/src/teams_notifications/graph_api.py
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx
import msal

from .config import Config
from .state import ChatInfo, ChannelMessageInfo

log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SCOPES = [
    "Chat.Read",
    "ChannelMessage.Read.All",
    "User.Read",
    "Presence.Read",
    "Team.ReadBasic.All",
    "Channel.ReadBasic.All",
]


def _parse_dt(s: str | None) -> datetime:
    if not s:
        return datetime.min.replace(tzinfo=timezone.utc)
    s = s.replace("Z", "+00:00")
    return datetime.fromisoformat(s)


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def parse_chats_response(response: dict[str, Any]) -> list[ChatInfo]:
    chats = []
    for chat in response.get("value", []):
        preview = chat.get("lastMessagePreview")
        if not preview:
            continue
        viewpoint = chat.get("viewpoint") or {}
        last_read = _parse_dt(viewpoint.get("lastMessageReadDateTime"))
        last_msg_time = _parse_dt(preview.get("createdDateTime"))

        if last_msg_time <= last_read:
            continue  # Already read

        from_user = (preview.get("from") or {}).get("user") or {}
        body = (preview.get("body") or {}).get("content", "")

        chats.append(ChatInfo(
            chat_id=chat["id"],
            chat_type=chat.get("chatType", "oneOnOne"),
            sender_name=from_user.get("displayName", "Unknown"),
            sender_id=from_user.get("id", ""),
            last_message=_strip_html(body),
            last_message_time=last_msg_time,
            last_read_time=last_read,
        ))
    return chats


def parse_channel_messages(
    messages: list[dict[str, Any]],
    my_user_id: str,
    team_name: str,
    channel_name: str,
) -> list[ChannelMessageInfo]:
    result = []
    for msg in messages:
        mentions = msg.get("mentions", [])
        is_mentioned = any(
            (m.get("mentioned") or {}).get("user", {}).get("id") == my_user_id
            for m in mentions
        )
        if not is_mentioned:
            continue

        from_user = (msg.get("from") or {}).get("user") or {}
        body = (msg.get("body") or {}).get("content", "")

        result.append(ChannelMessageInfo(
            team_name=team_name,
            channel_name=channel_name,
            sender_name=from_user.get("displayName", "Unknown"),
            message_preview=_strip_html(body)[:200],
            timestamp=_parse_dt(msg.get("createdDateTime")),
        ))
    return result


class GraphClient:
    def __init__(self, config: Config):
        self._config = config
        self._app: msal.PublicClientApplication | None = None
        self._http = httpx.AsyncClient(timeout=30.0)
        self._my_user_id: str | None = None
        self._delta_links: dict[str, str] = {}

    def _get_msal_app(self) -> msal.PublicClientApplication:
        if self._app is None:
            self._app = msal.PublicClientApplication(
                client_id=self._config.client_id,
                authority=f"https://login.microsoftonline.com/{self._config.tenant_id}",
            )
        return self._app

    async def authenticate_interactive(self) -> str:
        app = self._get_msal_app()
        accounts = app.get_accounts()
        if accounts:
            result = app.acquire_token_silent(scopes=SCOPES, account=accounts[0])
            if result and "access_token" in result:
                return result["access_token"]
        result = app.acquire_token_interactive(scopes=SCOPES, prompt="select_account")
        if "access_token" in result:
            return result["access_token"]
        error = result.get("error", "")
        description = result.get("error_description", "")
        if "AADSTS65001" in description or "admin_consent" in error:
            raise PermissionError(
                "Your org admin needs to approve this app's permissions. "
                "Ask your admin for consent, or the daemon will run in PWA-only mode."
            )
        raise RuntimeError(f"Auth failed: {error}: {description}")

    async def get_token(self) -> str:
        app = self._get_msal_app()
        accounts = app.get_accounts()
        if not accounts:
            raise RuntimeError("Not authenticated. Run interactive auth first.")
        result = app.acquire_token_silent(scopes=SCOPES, account=accounts[0])
        if result and "access_token" in result:
            return result["access_token"]
        raise RuntimeError("Token refresh failed. Re-authenticate.")

    async def _get(self, url: str, token: str) -> dict:
        headers = {"Authorization": f"Bearer {token}"}
        for attempt in range(3):
            resp = await self._http.get(url, headers=headers)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "30"))
                log.warning("Throttled, retrying in %ds", retry_after)
                await asyncio.sleep(retry_after)
                continue
            resp.raise_for_status()
        raise RuntimeError(f"Failed after 3 retries: {url}")

    async def get_my_user_id(self, token: str) -> str:
        if self._my_user_id:
            return self._my_user_id
        data = await self._get(f"{GRAPH_BASE}/me", token)
        self._my_user_id = data["id"]
        return self._my_user_id

    async def get_unread_chats(self, token: str) -> list[ChatInfo]:
        url = f"{GRAPH_BASE}/me/chats?$expand=lastMessagePreview&$top=50"
        data = await self._get(url, token)
        return parse_chats_response(data)

    async def get_joined_teams(self, token: str) -> list[dict]:
        data = await self._get(f"{GRAPH_BASE}/me/joinedTeams", token)
        return data.get("value", [])

    async def get_channels(self, token: str, team_id: str) -> list[dict]:
        data = await self._get(f"{GRAPH_BASE}/teams/{team_id}/channels", token)
        return data.get("value", [])

    async def get_channel_messages_delta(
        self, token: str, team_id: str, channel_id: str,
        team_name: str, channel_name: str,
    ) -> list[ChannelMessageInfo]:
        delta_key = f"{team_id}/{channel_id}"
        url = self._delta_links.get(delta_key)
        if not url:
            url = f"{GRAPH_BASE}/teams/{team_id}/channels/{channel_id}/messages/delta?$top=50"

        my_id = await self.get_my_user_id(token)
        all_mentions = []

        while url:
            data = await self._get(url, token)
            messages = data.get("value", [])
            mentions = parse_channel_messages(messages, my_id, team_name, channel_name)
            all_mentions.extend(mentions)

            if "@odata.deltaLink" in data:
                self._delta_links[delta_key] = data["@odata.deltaLink"]
                url = None
            elif "@odata.nextLink" in data:
                url = data["@odata.nextLink"]
            else:
                url = None

        return all_mentions

    async def close(self):
        await self._http.aclose()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd daemon && source .venv/bin/activate && pytest tests/test_graph_api.py -v`
Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add daemon/src/teams_notifications/graph_api.py daemon/tests/test_graph_api.py
git commit -m "Add Graph API client with MSAL auth and response parsing"
```

---

### Task 5: Notification Dispatcher

**Files:**
- Create: `daemon/src/teams_notifications/notifications.py`

- [ ] **Step 1: Implement notification dispatcher**

```python
# daemon/src/teams_notifications/notifications.py
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from enum import IntEnum

log = logging.getLogger(__name__)


class Urgency(IntEnum):
    LOW = 0
    NORMAL = 1
    CRITICAL = 2


@dataclass
class Notification:
    title: str
    body: str
    urgency: Urgency = Urgency.NORMAL
    timeout_ms: int = 10000  # 0 = persistent
    icon: str = "dialog-information"
    sound_file: str | None = None


def send_notification(notification: Notification) -> None:
    urgency_map = {Urgency.LOW: "low", Urgency.NORMAL: "normal", Urgency.CRITICAL: "critical"}
    cmd = [
        "notify-send",
        "--urgency", urgency_map[notification.urgency],
        "--expire-time", str(notification.timeout_ms),
        "--icon", notification.icon,
        "--app-name", "Teams Notifications",
        notification.title,
        notification.body,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=5)
    except FileNotFoundError:
        log.error("notify-send not found. Install libnotify-bin.")
    except subprocess.SubprocessError as e:
        log.error("Failed to send notification: %s", e)

    if notification.sound_file:
        _play_sound(notification.sound_file)


def _play_sound(path: str) -> None:
    for player in ("pw-play", "paplay", "aplay"):
        try:
            subprocess.Popen(
                [player, path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except FileNotFoundError:
            continue
    log.warning("No sound player found (tried pw-play, paplay, aplay)")
```

- [ ] **Step 2: Manual test**

Run:
```bash
cd daemon && source .venv/bin/activate
python -c "
from teams_notifications.notifications import send_notification, Notification, Urgency
send_notification(Notification(title='Test', body='Teams notification test', urgency=Urgency.NORMAL))
"
```

Expected: a system notification appears on KDE desktop.

- [ ] **Step 3: Commit**

```bash
git add daemon/src/teams_notifications/notifications.py
git commit -m "Add notification dispatcher using notify-send with sound support"
```

---

### Task 6: Reminder Scheduler

**Files:**
- Create: `daemon/src/teams_notifications/reminders.py`
- Create: `daemon/tests/test_reminders.py`

- [ ] **Step 1: Write failing tests**

```python
# daemon/tests/test_reminders.py
from datetime import datetime, timezone, timedelta

from teams_notifications.reminders import ReminderScheduler, EscalationTier
from teams_notifications.notifications import Urgency


def test_initial_state():
    rs = ReminderScheduler(interval_sec=300, tier2_after=3, tier3_after=6)
    assert rs.reminder_count == 0
    assert rs.is_snoozed is False
    assert rs.current_tier == EscalationTier.NORMAL


def test_should_remind_after_interval():
    rs = ReminderScheduler(interval_sec=300, tier2_after=3, tier3_after=6)
    now = datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc)
    rs.start(now)

    # Before interval: no
    assert rs.should_remind(now + timedelta(seconds=100)) is False
    # After interval: yes
    assert rs.should_remind(now + timedelta(seconds=301)) is True


def test_remind_increments_count():
    rs = ReminderScheduler(interval_sec=300, tier2_after=3, tier3_after=6)
    now = datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc)
    rs.start(now)
    rs.fire_reminder(now + timedelta(seconds=301))
    assert rs.reminder_count == 1
    rs.fire_reminder(now + timedelta(seconds=602))
    assert rs.reminder_count == 2


def test_escalation_tiers():
    rs = ReminderScheduler(interval_sec=60, tier2_after=3, tier3_after=6)
    now = datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc)
    rs.start(now)

    for i in range(3):
        rs.fire_reminder(now + timedelta(seconds=60 * (i + 1)))
    assert rs.current_tier == EscalationTier.PERSISTENT  # after 3

    for i in range(3):
        rs.fire_reminder(now + timedelta(seconds=60 * (i + 4)))
    assert rs.current_tier == EscalationTier.SOUND  # after 6


def test_reset_clears_state():
    rs = ReminderScheduler(interval_sec=300, tier2_after=3, tier3_after=6)
    now = datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc)
    rs.start(now)
    rs.fire_reminder(now + timedelta(seconds=301))
    rs.reset()
    assert rs.reminder_count == 0
    assert rs.current_tier == EscalationTier.NORMAL


def test_snooze():
    rs = ReminderScheduler(interval_sec=300, tier2_after=3, tier3_after=6)
    now = datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc)
    rs.start(now)
    rs.snooze(duration_sec=900, at=now + timedelta(seconds=301))
    assert rs.is_snoozed is True
    assert rs.should_remind(now + timedelta(seconds=602)) is False  # still snoozed
    assert rs.should_remind(now + timedelta(seconds=1202)) is True  # snooze expired


def test_get_urgency():
    rs = ReminderScheduler(interval_sec=60, tier2_after=2, tier3_after=4)
    assert rs.get_urgency() == Urgency.NORMAL
    now = datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc)
    rs.start(now)
    rs.fire_reminder(now + timedelta(seconds=61))
    rs.fire_reminder(now + timedelta(seconds=122))
    assert rs.get_urgency() == Urgency.CRITICAL
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd daemon && source .venv/bin/activate && pytest tests/test_reminders.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement reminders module**

```python
# daemon/src/teams_notifications/reminders.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum

from .notifications import Urgency


class EscalationTier(Enum):
    NORMAL = "normal"
    PERSISTENT = "persistent"
    SOUND = "sound"


class ReminderScheduler:
    def __init__(self, interval_sec: int, tier2_after: int, tier3_after: int):
        self._interval = timedelta(seconds=interval_sec)
        self._tier2_after = tier2_after
        self._tier3_after = tier3_after
        self._reminder_count = 0
        self._started_at: datetime | None = None
        self._last_reminder_at: datetime | None = None
        self._snooze_until: datetime | None = None

    @property
    def reminder_count(self) -> int:
        return self._reminder_count

    @property
    def is_snoozed(self) -> bool:
        if self._snooze_until is None:
            return False
        now = datetime.now(timezone.utc)
        return now < self._snooze_until

    @property
    def current_tier(self) -> EscalationTier:
        if self._reminder_count >= self._tier3_after:
            return EscalationTier.SOUND
        if self._reminder_count >= self._tier2_after:
            return EscalationTier.PERSISTENT
        return EscalationTier.NORMAL

    def start(self, at: datetime) -> None:
        if self._started_at is None:
            self._started_at = at
            self._last_reminder_at = at

    def should_remind(self, now: datetime) -> bool:
        if self._last_reminder_at is None:
            return False
        if self._snooze_until and now < self._snooze_until:
            return False
        return (now - self._last_reminder_at) >= self._interval

    def fire_reminder(self, at: datetime) -> None:
        self._reminder_count += 1
        self._last_reminder_at = at

    def reset(self) -> None:
        self._reminder_count = 0
        self._started_at = None
        self._last_reminder_at = None
        self._snooze_until = None

    def snooze(self, duration_sec: int, at: datetime) -> None:
        self._snooze_until = at + timedelta(seconds=duration_sec)

    def get_urgency(self) -> Urgency:
        tier = self.current_tier
        if tier in (EscalationTier.SOUND, EscalationTier.PERSISTENT):
            return Urgency.CRITICAL
        return Urgency.NORMAL

    def get_timeout_ms(self) -> int:
        tier = self.current_tier
        if tier in (EscalationTier.PERSISTENT, EscalationTier.SOUND):
            return 0  # persistent
        return 10000
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd daemon && source .venv/bin/activate && pytest tests/test_reminders.py -v`
Expected: all 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add daemon/src/teams_notifications/reminders.py daemon/tests/test_reminders.py
git commit -m "Add reminder scheduler with escalation tiers and snooze"
```

---

### Task 7: Process Watchdog

**Files:**
- Create: `daemon/src/teams_notifications/watchdog.py`
- Create: `daemon/tests/test_watchdog.py`

- [ ] **Step 1: Write failing tests**

```python
# daemon/tests/test_watchdog.py
from unittest.mock import patch

from teams_notifications.watchdog import TeamsWatchdog


def test_teams_detected_resets_misses():
    wd = TeamsWatchdog(grace_checks=2)
    wd._consecutive_misses = 1
    wd._update(teams_running=True)
    assert wd.consecutive_misses == 0
    assert wd.should_alert is False


def test_alert_after_grace_period():
    wd = TeamsWatchdog(grace_checks=2)
    wd._update(teams_running=False)
    assert wd.should_alert is False
    wd._update(teams_running=False)
    assert wd.should_alert is False
    wd._update(teams_running=False)
    assert wd.should_alert is True  # 3 misses > grace of 2


def test_alert_clears_when_teams_returns():
    wd = TeamsWatchdog(grace_checks=1)
    wd._update(teams_running=False)
    wd._update(teams_running=False)
    assert wd.should_alert is True
    wd._update(teams_running=True)
    assert wd.should_alert is False


@patch("teams_notifications.watchdog.subprocess.run")
def test_check_calls_pgrep(mock_run):
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = b"/opt/google/chrome --app-id=cifhbcnohmdccbgoicgdjpfamggdegmo"
    wd = TeamsWatchdog(grace_checks=2)
    result = wd.check()
    assert result is True
    assert wd.consecutive_misses == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd daemon && source .venv/bin/activate && pytest tests/test_watchdog.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement watchdog module**

```python
# daemon/src/teams_notifications/watchdog.py
from __future__ import annotations

import logging
import subprocess

log = logging.getLogger(__name__)

# Known Teams PWA app IDs in Chrome
TEAMS_APP_IDS = [
    "cifhbcnohmdccbgoicgdjpfamggdegmo",  # Teams PWA (new)
    "lhkgjmfkhgocfcnphhacgheobkdlkifg",  # Teams PWA (old)
]


class TeamsWatchdog:
    def __init__(self, grace_checks: int = 2):
        self._grace_checks = grace_checks
        self._consecutive_misses = 0

    @property
    def consecutive_misses(self) -> int:
        return self._consecutive_misses

    @property
    def should_alert(self) -> bool:
        return self._consecutive_misses > self._grace_checks

    def check(self) -> bool:
        running = self._is_teams_running()
        self._update(running)
        return running

    def _update(self, teams_running: bool) -> None:
        if teams_running:
            self._consecutive_misses = 0
        else:
            self._consecutive_misses += 1

    def _is_teams_running(self) -> bool:
        try:
            result = subprocess.run(
                ["pgrep", "-a", "-f", "chrome.*--app-id="],
                capture_output=True,
                timeout=5,
            )
            if result.returncode != 0:
                return False
            output = result.stdout.decode("utf-8", errors="replace")
            return any(app_id in output for app_id in TEAMS_APP_IDS)
        except (subprocess.SubprocessError, OSError) as e:
            log.warning("Watchdog check failed: %s", e)
            return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd daemon && source .venv/bin/activate && pytest tests/test_watchdog.py -v`
Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add daemon/src/teams_notifications/watchdog.py daemon/tests/test_watchdog.py
git commit -m "Add Teams PWA process watchdog with grace period"
```

---

### Task 8: Tray Icon

**Files:**
- Create: `daemon/src/teams_notifications/tray.py`

- [ ] **Step 1: Implement tray icon with badge rendering**

```python
# daemon/src/teams_notifications/tray.py
from __future__ import annotations

import webbrowser
from enum import Enum
from typing import Callable

from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QAction, QColor, QCursor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QMenu,
    QSystemTrayIcon,
    QVBoxLayout,
)

from .state import UnreadState


class TrayState(Enum):
    OK = "ok"
    UNREAD = "unread"
    TEAMS_DOWN = "teams_down"
    ERROR = "error"


STATE_COLORS = {
    TrayState.OK: QColor(34, 197, 94),
    TrayState.UNREAD: QColor(239, 68, 68),
    TrayState.TEAMS_DOWN: QColor(234, 179, 8),
    TrayState.ERROR: QColor(156, 163, 175),
}

ICON_SIZE = 64


def _create_base_icon(color: QColor) -> QPixmap:
    pixmap = QPixmap(ICON_SIZE, ICON_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(color)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(4, 4, ICON_SIZE - 8, ICON_SIZE - 8, 12, 12)
    painter.setPen(QColor(255, 255, 255))
    font = QFont("Sans", 28, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(
        QRect(4, 4, ICON_SIZE - 8, ICON_SIZE - 8),
        Qt.AlignmentFlag.AlignCenter, "T",
    )
    painter.end()
    return pixmap


def create_tray_icon(state: TrayState, count: int = 0) -> QIcon:
    color = STATE_COLORS[state]
    pixmap = _create_base_icon(color)

    if count > 0:
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        badge_text = str(count) if count <= 99 else "99+"
        badge_w = max(24, len(badge_text) * 10 + 8)
        badge_h = 22
        badge_x = ICON_SIZE - badge_w
        badge_y = 0
        painter.setBrush(QColor(220, 38, 38))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(badge_x, badge_y, badge_w, badge_h, 8, 8)
        font = QFont("Sans", 11, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(
            QRect(badge_x, badge_y, badge_w, badge_h),
            Qt.AlignmentFlag.AlignCenter, badge_text,
        )
        painter.end()

    return QIcon(pixmap)


class SummaryPopup(QFrame):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.Popup
        )
        self.setFixedSize(320, 400)
        self.setStyleSheet("""
            QFrame {
                background: #2d2d2d;
                border: 1px solid #555;
                border-radius: 8px;
            }
            QLabel { color: #eee; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        self._header = QLabel("Unread Messages")
        self._header.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self._header)
        self._body = QLabel("No new messages")
        self._body.setWordWrap(True)
        layout.addWidget(self._body)
        layout.addStretch()

    def update_content(self, state: UnreadState) -> None:
        if state.is_empty:
            self._header.setText("No Unread Messages")
            self._body.setText("You're all caught up.")
            return
        self._header.setText(state.summary())
        lines = []
        for chat in list(state.chats.values())[:10]:
            preview = chat.last_message[:80]
            lines.append(f"<b>{chat.sender_name}</b>: {preview}")
        for mention in state.channel_mentions[:5]:
            lines.append(
                f"<b>@{mention.channel_name}</b> — "
                f"{mention.sender_name}: {mention.message_preview[:60]}"
            )
        self._body.setText("<br>".join(lines))

    def show_near(self, tray: QSystemTrayIcon) -> None:
        geo = tray.geometry()
        if geo.isValid() and not geo.isNull():
            x = geo.center().x() - self.width() // 2
            y = geo.top() - self.height() - 8
            screen = QApplication.screenAt(geo.center())
            if screen:
                sg = screen.availableGeometry()
                if y < sg.top():
                    y = geo.bottom() + 8
                x = max(sg.left(), min(x, sg.right() - self.width()))
        else:
            pos = QCursor.pos()
            x = pos.x() - self.width() // 2
            y = pos.y() - self.height() - 20
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()


class TrayManager:
    def __init__(
        self,
        on_settings: Callable[[], None],
        on_snooze: Callable[[int], None],
        on_quit: Callable[[], None],
    ):
        self._tray = QSystemTrayIcon()
        self._popup = SummaryPopup()
        self._state = TrayState.OK
        self._unread_count = 0
        self._current_state = UnreadState()

        self._tray.setIcon(create_tray_icon(TrayState.OK))
        self._tray.setToolTip("Teams Notifications — Connected")
        self._tray.setVisible(True)
        self._tray.activated.connect(self._on_activated)

        menu = QMenu()
        action_open = QAction("Open Teams")
        action_open.triggered.connect(
            lambda: webbrowser.open("https://teams.microsoft.com")
        )
        menu.addAction(action_open)
        menu.addSeparator()

        snooze_menu = menu.addMenu("Snooze")
        for label, seconds in [
            ("15 minutes", 900),
            ("30 minutes", 1800),
            ("1 hour", 3600),
        ]:
            action = QAction(label)
            action.triggered.connect(
                lambda checked, s=seconds: on_snooze(s)
            )
            snooze_menu.addAction(action)

        menu.addSeparator()
        action_settings = QAction("Settings...")
        action_settings.triggered.connect(on_settings)
        menu.addAction(action_settings)
        menu.addSeparator()
        action_quit = QAction("Quit")
        action_quit.triggered.connect(on_quit)
        menu.addAction(action_quit)
        self._tray.setContextMenu(menu)

    def update(self, state: UnreadState, teams_running: bool = True) -> None:
        self._current_state = state
        self._unread_count = state.total_unread

        if not teams_running:
            self._state = TrayState.TEAMS_DOWN
            self._tray.setToolTip("Teams Notifications — Teams is not running!")
        elif state.is_empty:
            self._state = TrayState.OK
            self._tray.setToolTip("Teams Notifications — No unread messages")
        else:
            self._state = TrayState.UNREAD
            self._tray.setToolTip(f"Teams Notifications — {state.summary()}")

        self._tray.setIcon(create_tray_icon(self._state, self._unread_count))
        self._popup.update_content(state)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self._popup.isVisible():
                self._popup.hide()
            else:
                self._popup.show_near(self._tray)
```

- [ ] **Step 2: Manual test**

Run:
```bash
cd daemon && source .venv/bin/activate
python -c "
import sys
from PyQt6.QtWidgets import QApplication
from teams_notifications.tray import TrayManager
from teams_notifications.state import UnreadState, ChatInfo
from datetime import datetime, timezone

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)
tray = TrayManager(
    on_settings=lambda: print('settings'),
    on_snooze=lambda s: print(f'snooze {s}'),
    on_quit=app.quit,
)
state = UnreadState()
state.chats = {
    'c1': ChatInfo('c1', 'oneOnOne', 'Alice', 'alice@ex.com', 'Hey there!',
                   datetime.now(timezone.utc),
                   datetime.min.replace(tzinfo=timezone.utc)),
}
tray.update(state)
sys.exit(app.exec())
"
```

Expected: Red "T" tray icon with badge "1". Left-click shows popup. Right-click shows menu.

- [ ] **Step 3: Commit**

```bash
git add daemon/src/teams_notifications/tray.py
git commit -m "Add KDE tray icon with badge rendering, popup, and context menu"
```

---

### Task 9: Socket Server

**Files:**
- Create: `daemon/src/teams_notifications/socket_server.py`

- [ ] **Step 1: Implement Unix socket server**

```python
# daemon/src/teams_notifications/socket_server.py
from __future__ import annotations

import asyncio
import json
import logging
import os
import struct
from pathlib import Path
from typing import Awaitable, Callable

log = logging.getLogger(__name__)


def get_socket_path() -> Path:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return Path(runtime_dir) / "teams-notifications.sock"


class SocketServer:
    def __init__(self, on_message: Callable[[dict], Awaitable[None]]):
        self._on_message = on_message
        self._server: asyncio.AbstractServer | None = None
        self._socket_path = get_socket_path()

    async def start(self) -> None:
        if self._socket_path.exists():
            self._socket_path.unlink()

        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=str(self._socket_path),
        )
        os.chmod(self._socket_path, 0o600)
        log.info("Socket server listening on %s", self._socket_path)

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        log.info("Native host connected")
        try:
            while True:
                raw_len = await reader.readexactly(4)
                length = struct.unpack("<I", raw_len)[0]
                if length == 0:
                    continue
                if length > 1_048_576:
                    log.warning("Message too large (%d bytes), dropping", length)
                    await reader.readexactly(length)
                    continue
                raw_msg = await reader.readexactly(length)
                msg = json.loads(raw_msg.decode("utf-8"))
                log.debug("Received from native host: %s", msg)
                await self._on_message(msg)

                ack = json.dumps({"type": "ack"}).encode("utf-8")
                writer.write(struct.pack("<I", len(ack)) + ack)
                await writer.drain()
        except asyncio.IncompleteReadError:
            log.info("Native host disconnected")
        except Exception:
            log.exception("Error handling native host connection")
        finally:
            writer.close()
            await writer.wait_closed()

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        if self._socket_path.exists():
            self._socket_path.unlink()
```

- [ ] **Step 2: Commit**

```bash
git add daemon/src/teams_notifications/socket_server.py
git commit -m "Add Unix socket server for native messaging host communication"
```

---

### Task 10: Settings UI

**Files:**
- Create: `daemon/src/teams_notifications/settings_ui.py`

- [ ] **Step 1: Implement settings dialog**

```python
# daemon/src/teams_notifications/settings_ui.py
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .config import Config


class SettingsDialog(QDialog):
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("Teams Notifications — Settings")
        self.setMinimumSize(520, 480)

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._build_notifications_tab(), "Notifications")
        tabs.addTab(self._build_reminders_tab(), "Reminders")
        tabs.addTab(self._build_watchdog_tab(), "Watchdog")
        tabs.addTab(self._build_about_tab(), "About")
        layout.addWidget(tabs)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(self._save_and_close)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def _build_notifications_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        group_mode = QGroupBox("Notification Mode")
        mode_layout = QVBoxLayout(group_mode)
        self._mode_group = QButtonGroup(self)
        modes = [
            ("Everything", "all"),
            ("Mentions && DMs only", "mentions_and_dms"),
            ("DMs only", "dms_only"),
        ]
        for i, (label, value) in enumerate(modes):
            rb = QRadioButton(label)
            rb.setProperty("mode_value", value)
            if value == self._config.filter_mode:
                rb.setChecked(True)
            self._mode_group.addButton(rb, i)
            mode_layout.addWidget(rb)
        layout.addWidget(group_mode)

        group_filter = QGroupBox("Filters (applied on top of mode)")
        filter_layout = QVBoxLayout(group_filter)

        filter_layout.addWidget(QLabel("Blacklist (always silent):"))
        self._blacklist = QListWidget()
        self._blacklist.addItems(self._config.blacklist)
        filter_layout.addWidget(self._blacklist)
        bl_btn_layout = QHBoxLayout()
        self._bl_input = QLineEdit()
        self._bl_input.setPlaceholderText("user:email@example.com or channel:Name")
        bl_add = QPushButton("Add")
        bl_add.clicked.connect(
            lambda: self._add_to_list(self._bl_input, self._blacklist)
        )
        bl_remove = QPushButton("Remove")
        bl_remove.clicked.connect(lambda: self._remove_from_list(self._blacklist))
        bl_btn_layout.addWidget(self._bl_input)
        bl_btn_layout.addWidget(bl_add)
        bl_btn_layout.addWidget(bl_remove)
        filter_layout.addLayout(bl_btn_layout)

        filter_layout.addWidget(QLabel("Whitelist (always notify):"))
        self._whitelist = QListWidget()
        self._whitelist.addItems(self._config.whitelist)
        filter_layout.addWidget(self._whitelist)
        wl_btn_layout = QHBoxLayout()
        self._wl_input = QLineEdit()
        self._wl_input.setPlaceholderText("user:email@example.com or channel:Name")
        wl_add = QPushButton("Add")
        wl_add.clicked.connect(
            lambda: self._add_to_list(self._wl_input, self._whitelist)
        )
        wl_remove = QPushButton("Remove")
        wl_remove.clicked.connect(lambda: self._remove_from_list(self._whitelist))
        wl_btn_layout.addWidget(self._wl_input)
        wl_btn_layout.addWidget(wl_add)
        wl_btn_layout.addWidget(wl_remove)
        filter_layout.addLayout(wl_btn_layout)

        self._chk_exclude_bots = QCheckBox("Exclude bot messages")
        self._chk_exclude_bots.setChecked(self._config.exclude_bots)
        filter_layout.addWidget(self._chk_exclude_bots)
        layout.addWidget(group_filter)

        layout.addStretch()
        return tab

    def _build_reminders_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        group = QGroupBox("Reminder Settings")
        form = QFormLayout(group)

        self._spin_reminder = QSpinBox()
        self._spin_reminder.setRange(1, 60)
        self._spin_reminder.setValue(self._config.reminder_interval_sec // 60)
        self._spin_reminder.setSuffix(" min")
        form.addRow("Reminder interval:", self._spin_reminder)

        self._chk_escalation = QCheckBox("Enable escalation")
        self._chk_escalation.setChecked(self._config.escalation_enabled)
        form.addRow(self._chk_escalation)

        self._spin_tier2 = QSpinBox()
        self._spin_tier2.setRange(1, 20)
        self._spin_tier2.setValue(self._config.escalation_tier2_after)
        form.addRow("Persistent after N reminders:", self._spin_tier2)

        self._spin_tier3 = QSpinBox()
        self._spin_tier3.setRange(1, 30)
        self._spin_tier3.setValue(self._config.escalation_tier3_after)
        form.addRow("Sound after N reminders:", self._spin_tier3)

        layout.addWidget(group)

        group_poll = QGroupBox("Graph API Polling")
        poll_form = QFormLayout(group_poll)
        self._spin_poll = QSpinBox()
        self._spin_poll.setRange(10, 300)
        self._spin_poll.setValue(self._config.check_interval_sec)
        self._spin_poll.setSuffix(" sec")
        poll_form.addRow("Poll interval:", self._spin_poll)
        layout.addWidget(group_poll)

        layout.addStretch()
        return tab

    def _build_watchdog_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        group = QGroupBox("Teams Process Watchdog")
        form = QFormLayout(group)

        self._spin_watchdog = QSpinBox()
        self._spin_watchdog.setRange(10, 300)
        self._spin_watchdog.setValue(self._config.watchdog_interval_sec)
        self._spin_watchdog.setSuffix(" sec")
        form.addRow("Check interval:", self._spin_watchdog)

        self._spin_grace = QSpinBox()
        self._spin_grace.setRange(0, 10)
        self._spin_grace.setValue(self._config.watchdog_grace_checks)
        form.addRow("Grace checks before alert:", self._spin_grace)

        layout.addWidget(group)
        layout.addStretch()
        return tab

    def _build_about_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        layout.addWidget(QLabel("<b>Teams Notifications v0.1.0</b>"))
        layout.addWidget(QLabel("Graph API + KDE tray daemon for Teams"))
        layout.addWidget(QLabel(""))

        group_auth = QGroupBox("Graph API Authentication")
        auth_layout = QVBoxLayout(group_auth)
        self._lbl_auth_status = QLabel("Status: Not authenticated")
        auth_layout.addWidget(self._lbl_auth_status)

        form = QFormLayout()
        self._input_client_id = QLineEdit(self._config.client_id)
        self._input_client_id.setPlaceholderText("Azure App Client ID")
        form.addRow("Client ID:", self._input_client_id)
        self._input_tenant_id = QLineEdit(self._config.tenant_id)
        self._input_tenant_id.setPlaceholderText("Azure Tenant ID")
        form.addRow("Tenant ID:", self._input_tenant_id)
        auth_layout.addLayout(form)

        self._btn_login = QPushButton("Login with Microsoft")
        auth_layout.addWidget(self._btn_login)
        layout.addWidget(group_auth)

        layout.addStretch()
        return tab

    def _add_to_list(self, input_field: QLineEdit, list_widget: QListWidget) -> None:
        text = input_field.text().strip()
        if text and (text.startswith("user:") or text.startswith("channel:")):
            list_widget.addItem(text)
            input_field.clear()

    def _remove_from_list(self, list_widget: QListWidget) -> None:
        for item in list_widget.selectedItems():
            list_widget.takeItem(list_widget.row(item))

    def _save_and_close(self) -> None:
        checked = self._mode_group.checkedButton()
        if checked:
            self._config.filter_mode = checked.property("mode_value")

        self._config.blacklist = [
            self._blacklist.item(i).text() for i in range(self._blacklist.count())
        ]
        self._config.whitelist = [
            self._whitelist.item(i).text() for i in range(self._whitelist.count())
        ]
        self._config.exclude_bots = self._chk_exclude_bots.isChecked()
        self._config.reminder_interval_sec = self._spin_reminder.value() * 60
        self._config.escalation_enabled = self._chk_escalation.isChecked()
        self._config.escalation_tier2_after = self._spin_tier2.value()
        self._config.escalation_tier3_after = self._spin_tier3.value()
        self._config.check_interval_sec = self._spin_poll.value()
        self._config.watchdog_interval_sec = self._spin_watchdog.value()
        self._config.watchdog_grace_checks = self._spin_grace.value()
        self._config.client_id = self._input_client_id.text().strip()
        self._config.tenant_id = self._input_tenant_id.text().strip()

        self.accept()

    @property
    def login_button(self) -> QPushButton:
        return self._btn_login

    def set_auth_status(self, authenticated: bool) -> None:
        if authenticated:
            self._lbl_auth_status.setText("Status: Authenticated")
            self._lbl_auth_status.setStyleSheet("color: green;")
        else:
            self._lbl_auth_status.setText("Status: Not authenticated")
            self._lbl_auth_status.setStyleSheet("color: red;")
```

- [ ] **Step 2: Manual test**

Run:
```bash
cd daemon && source .venv/bin/activate
python -c "
import sys
from PyQt6.QtWidgets import QApplication
from teams_notifications.settings_ui import SettingsDialog
from teams_notifications.config import Config

app = QApplication(sys.argv)
config = Config()
config.blacklist = ['channel:Random']
dialog = SettingsDialog(config)
if dialog.exec():
    print('Mode:', config.filter_mode)
    print('Blacklist:', config.blacklist)
"
```

Expected: Settings dialog with 4 tabs. OK saves, Cancel discards.

- [ ] **Step 3: Commit**

```bash
git add daemon/src/teams_notifications/settings_ui.py
git commit -m "Add settings dialog with notification mode, filters, and auth config"
```

---

### Task 11: Main Entry Point

**Files:**
- Create: `daemon/src/teams_notifications/main.py`

- [ ] **Step 1: Implement main entry point wiring all components**

```python
# daemon/src/teams_notifications/main.py
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from .config import Config, DEFAULT_CONFIG_PATH
from .graph_api import GraphClient
from .notifications import Notification, Urgency, send_notification
from .reminders import ReminderScheduler
from .settings_ui import SettingsDialog
from .socket_server import SocketServer
from .state import FilterConfig, UnreadState, filter_notifications
from .tray import TrayManager
from .watchdog import TeamsWatchdog

log = logging.getLogger(__name__)


class App:
    def __init__(self):
        self._config = Config.from_file(DEFAULT_CONFIG_PATH)
        self._graph = GraphClient(self._config)
        self._watchdog = TeamsWatchdog(
            grace_checks=self._config.watchdog_grace_checks,
        )
        self._reminder = ReminderScheduler(
            interval_sec=self._config.reminder_interval_sec,
            tier2_after=self._config.escalation_tier2_after,
            tier3_after=self._config.escalation_tier3_after,
        )
        self._watchdog_reminder = ReminderScheduler(
            interval_sec=self._config.reminder_interval_sec,
            tier2_after=self._config.escalation_tier2_after,
            tier3_after=self._config.escalation_tier3_after,
        )
        self._state = UnreadState()
        self._teams_running = True
        self._tray: TrayManager | None = None
        self._settings_dialog: SettingsDialog | None = None
        self._running = False

    def _on_settings(self) -> None:
        self._settings_dialog = SettingsDialog(self._config)
        self._settings_dialog.login_button.clicked.connect(self._on_login_clicked)
        if self._settings_dialog.exec():
            self._config.save(DEFAULT_CONFIG_PATH)
            self._reminder = ReminderScheduler(
                interval_sec=self._config.reminder_interval_sec,
                tier2_after=self._config.escalation_tier2_after,
                tier3_after=self._config.escalation_tier3_after,
            )
            self._watchdog = TeamsWatchdog(
                grace_checks=self._config.watchdog_grace_checks,
            )
            self._graph = GraphClient(self._config)
            log.info("Config updated and saved")

    def _on_login_clicked(self) -> None:
        asyncio.ensure_future(self._do_login())

    async def _do_login(self) -> None:
        try:
            await self._graph.authenticate_interactive()
            log.info("Authenticated successfully")
            if self._settings_dialog:
                self._settings_dialog.set_auth_status(True)
        except Exception as e:
            log.error("Auth failed: %s", e)
            send_notification(Notification(
                title="Teams Notifications",
                body=f"Authentication failed: {e}",
                urgency=Urgency.CRITICAL,
            ))

    def _on_snooze(self, seconds: int) -> None:
        now = datetime.now(timezone.utc)
        self._reminder.snooze(seconds, now)
        send_notification(Notification(
            title="Teams Notifications",
            body=f"Snoozed for {seconds // 60} minutes",
        ))

    async def _on_socket_message(self, msg: dict) -> None:
        msg_type = msg.get("type")
        if msg_type == "badge":
            log.info("Badge update from PWA: %d", msg.get("count", 0))
        elif msg_type == "notification":
            title = msg.get("title", "")
            body = msg.get("body", "")
            log.info("Notification from PWA: %s — %s", title, body)
            send_notification(Notification(title=title, body=body))

    async def _poll_loop(self) -> None:
        while self._running:
            await self._poll_once()
            await asyncio.sleep(self._config.check_interval_sec)

    async def _poll_once(self) -> None:
        try:
            token = await self._graph.get_token()
        except RuntimeError:
            log.debug("Not authenticated yet, skipping poll")
            return

        now = datetime.now(timezone.utc)
        try:
            chats = await self._graph.get_unread_chats(token)

            mentions: list = []
            try:
                teams = await self._graph.get_joined_teams(token)
                for team in teams:
                    channels = await self._graph.get_channels(token, team["id"])
                    for channel in channels:
                        channel_mentions = (
                            await self._graph.get_channel_messages_delta(
                                token, team["id"], channel["id"],
                                team.get("displayName", ""),
                                channel.get("displayName", ""),
                            )
                        )
                        mentions.extend(channel_mentions)
            except Exception as e:
                log.warning("Channel polling failed: %s", e)

            fc = FilterConfig(
                mode=self._config.filter_mode,
                whitelist=self._config.whitelist,
                blacklist=self._config.blacklist,
                exclude_bots=self._config.exclude_bots,
            )
            filtered_chats, filtered_mentions = filter_notifications(
                chats, mentions, fc,
            )

            new_state = UnreadState(last_updated=now)
            for chat in filtered_chats:
                new_state.chats[chat.chat_id] = chat
            new_state.channel_mentions = filtered_mentions

            prev_chat_ids = set(self._state.chats.keys())
            for chat_id, chat in new_state.chats.items():
                if chat_id not in prev_chat_ids:
                    preview = chat.last_message[:self._config.max_preview_length]
                    body = preview if self._config.show_message_preview else "New message"
                    send_notification(Notification(
                        title=chat.sender_name, body=body,
                    ))

            self._state = new_state

            if self._state.is_empty:
                self._reminder.reset()
            else:
                self._reminder.start(now)
                if self._reminder.should_remind(now):
                    urgency = self._reminder.get_urgency()
                    timeout = self._reminder.get_timeout_ms()
                    tier = self._reminder.current_tier
                    sound = (
                        self._config.sound_file
                        if tier.value == "sound" else None
                    )
                    send_notification(Notification(
                        title="Teams — Unread Messages",
                        body=self._state.summary(),
                        urgency=urgency,
                        timeout_ms=timeout,
                        sound_file=sound,
                    ))
                    self._reminder.fire_reminder(now)

        except Exception as e:
            log.error("Poll failed: %s", e)

        if self._tray:
            self._tray.update(self._state, self._teams_running)

    async def _watchdog_loop(self) -> None:
        while self._running:
            self._teams_running = self._watchdog.check()
            now = datetime.now(timezone.utc)

            if self._watchdog.should_alert:
                self._watchdog_reminder.start(now)
                if self._watchdog_reminder.should_remind(now):
                    urgency = self._watchdog_reminder.get_urgency()
                    timeout = self._watchdog_reminder.get_timeout_ms()
                    tier = self._watchdog_reminder.current_tier
                    sound = (
                        self._config.sound_file
                        if tier.value == "sound" else None
                    )
                    send_notification(Notification(
                        title="Teams is not running!",
                        body="Microsoft Teams PWA is not detected.",
                        urgency=urgency,
                        timeout_ms=timeout,
                        sound_file=sound,
                    ))
                    self._watchdog_reminder.fire_reminder(now)
            else:
                self._watchdog_reminder.reset()

            if self._tray:
                self._tray.update(self._state, self._teams_running)

            await asyncio.sleep(self._config.watchdog_interval_sec)

    async def run_async(self) -> None:
        self._running = True
        socket_server = SocketServer(on_message=self._on_socket_message)
        await socket_server.start()
        try:
            await asyncio.gather(
                self._poll_loop(),
                self._watchdog_loop(),
            )
        finally:
            await socket_server.stop()
            await self._graph.close()

    def stop(self) -> None:
        self._running = False


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)
    qt_app.setApplicationName("Teams Notifications")

    import qasync
    loop = qasync.QEventLoop(qt_app)
    asyncio.set_event_loop(loop)

    app = App()
    app._tray = TrayManager(
        on_settings=app._on_settings,
        on_snooze=app._on_snooze,
        on_quit=lambda: (app.stop(), qt_app.quit()),
    )

    shutdown_event = asyncio.Event()
    qt_app.aboutToQuit.connect(
        lambda: (app.stop(), shutdown_event.set()),
    )

    asyncio.ensure_future(app.run_async())

    with loop:
        loop.run_until_complete(shutdown_event.wait())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke test**

Run:
```bash
cd daemon && source .venv/bin/activate
python -m teams_notifications.main
```

Expected: Tray icon appears. Logs show polling attempts. Watchdog checks for Teams. Ctrl+C or tray Quit exits cleanly.

- [ ] **Step 3: Commit**

```bash
git add daemon/src/teams_notifications/main.py
git commit -m "Add main entry point wiring all components with qasync event loop"
```

---

### Task 12: Install Scripts and systemd Service

**Files:**
- Create: `systemd/teams-notifications.service`
- Create: `scripts/install.sh`
- Create: `scripts/setup-azure.sh`
- Create: `scripts/uninstall.sh`

- [ ] **Step 1: Create systemd user service**

```ini
# systemd/teams-notifications.service
[Unit]
Description=Teams Notifications Tray Daemon
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=%h/Projects/teams-notifications/daemon/.venv/bin/python -m teams_notifications.main
WorkingDirectory=%h/Projects/teams-notifications/daemon
Restart=on-failure
RestartSec=5
Environment=QT_QPA_PLATFORM=xcb
PassEnvironment=DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS XDG_RUNTIME_DIR

[Install]
WantedBy=graphical-session.target
```

- [ ] **Step 2: Create install.sh**

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DAEMON_DIR="$PROJECT_DIR/daemon"

echo "=== Teams Notifications Installer ==="

echo ">>> Creating Python virtual environment..."
cd "$DAEMON_DIR"
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]" --quiet

echo ">>> Installing systemd user service..."
mkdir -p ~/.config/systemd/user
sed "s|%h|$HOME|g" "$PROJECT_DIR/systemd/teams-notifications.service" \
    > ~/.config/systemd/user/teams-notifications.service
systemctl --user daemon-reload
systemctl --user enable teams-notifications.service

echo ">>> Creating KDE autostart entry..."
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/teams-notifications.desktop << DESKTOP_EOF
[Desktop Entry]
Type=Application
Name=Teams Notifications
Exec=systemctl --user start teams-notifications
Icon=teams
X-KDE-autostart-phase=2
X-KDE-autostart-after=panel
Hidden=false
DESKTOP_EOF

CONFIG_DIR="$HOME/.config/teams-notifications"
if [ ! -f "$CONFIG_DIR/config.toml" ]; then
    echo ">>> Creating default config..."
    mkdir -p "$CONFIG_DIR"
    python -c "
from teams_notifications.config import Config, DEFAULT_CONFIG_PATH
Config().save(DEFAULT_CONFIG_PATH)
"
fi

echo ""
echo "=== Installation complete ==="
echo "Next: ./scripts/setup-azure.sh"
```

- [ ] **Step 3: Create setup-azure.sh**

```bash
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
echo "5. API permissions: Chat.Read, ChannelMessage.Read.All, User.Read, Team.ReadBasic.All, Channel.ReadBasic.All"
echo ""

read -rp "Application (client) ID: " CLIENT_ID
read -rp "Directory (tenant) ID: " TENANT_ID

cd "$DAEMON_DIR"
source .venv/bin/activate

python3 << PYEOF
from teams_notifications.config import Config, DEFAULT_CONFIG_PATH
config = Config.from_file(DEFAULT_CONFIG_PATH)
config.client_id = "${CLIENT_ID}"
config.tenant_id = "${TENANT_ID}"
config.save(DEFAULT_CONFIG_PATH)
print("Config saved.")
PYEOF

echo ""
echo "Authenticating..."
python3 << PYEOF
import asyncio
from teams_notifications.config import Config, DEFAULT_CONFIG_PATH
from teams_notifications.graph_api import GraphClient

async def do_auth():
    config = Config.from_file(DEFAULT_CONFIG_PATH)
    client = GraphClient(config)
    token = await client.authenticate_interactive()
    me = await client.get_my_user_id(token)
    print(f"Authenticated as user ID: {me}")
    await client.close()

asyncio.run(do_auth())
PYEOF

echo ""
echo "=== Setup complete! ==="
echo "Start: systemctl --user start teams-notifications"
```

- [ ] **Step 4: Create uninstall.sh**

```bash
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
```

- [ ] **Step 5: Make executable and commit**

```bash
chmod +x scripts/install.sh scripts/setup-azure.sh scripts/uninstall.sh
git add systemd/ scripts/
git commit -m "Add install/uninstall scripts and systemd user service"
```

---

### Task 13: Native Messaging Host

**Files:**
- Create: `daemon/src/teams_notifications/native_host.py`

- [ ] **Step 1: Implement native messaging host bridge**

```python
#!/usr/bin/env python3
# daemon/src/teams_notifications/native_host.py
"""Bridges Chrome extension <-> daemon Unix socket."""

import json
import os
import select
import socket
import struct
import sys

SOCKET_PATH = "/run/user/{}/teams-notifications.sock".format(os.getuid())


def read_chrome_message() -> bytes | None:
    raw_length = sys.stdin.buffer.read(4)
    if len(raw_length) < 4:
        return None
    length = struct.unpack("<I", raw_length)[0]
    if length == 0:
        return b"{}"
    raw = sys.stdin.buffer.read(length)
    if len(raw) < length:
        return None
    return raw


def write_chrome_message(data: bytes) -> None:
    sys.stdout.buffer.write(struct.pack("<I", len(data)))
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def recv_exact(sock: socket.socket, n: int) -> bytes | None:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


def main():
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(SOCKET_PATH)
    except (FileNotFoundError, ConnectionRefusedError) as e:
        write_chrome_message(
            json.dumps({"error": f"Cannot connect to daemon: {e}"}).encode()
        )
        sys.exit(1)

    stdin_fd = sys.stdin.buffer.fileno()
    sock_fd = sock.fileno()

    try:
        while True:
            readable, _, _ = select.select([stdin_fd, sock_fd], [], [])

            if stdin_fd in readable:
                msg = read_chrome_message()
                if msg is None:
                    break
                sock.sendall(struct.pack("<I", len(msg)) + msg)

            if sock_fd in readable:
                raw_len = recv_exact(sock, 4)
                if raw_len is None:
                    break
                length = struct.unpack("<I", raw_len)[0]
                raw_msg = recv_exact(sock, length)
                if raw_msg is None:
                    break
                write_chrome_message(raw_msg)
    finally:
        sock.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add daemon/src/teams_notifications/native_host.py
git commit -m "Add native messaging host bridge for future Chrome extension"
```

---

### Task 14: Final Verification

- [ ] **Step 1: Run full test suite**

Run:
```bash
cd daemon && source .venv/bin/activate && pytest tests/ -v
```

Expected: 26 tests pass (config: 5, state: 6, graph_api: 4, reminders: 7, watchdog: 4).

- [ ] **Step 2: Run install script**

Run: `./scripts/install.sh`
Expected: Venv created, deps installed, systemd service enabled.

- [ ] **Step 3: Start daemon and verify**

Run:
```bash
systemctl --user start teams-notifications
systemctl --user status teams-notifications
```

Expected: Service active. Green "T" tray icon visible.

- [ ] **Step 4: Verify settings dialog**

Right-click tray icon > Settings. Check all tabs render correctly.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "Final verification: all tests pass, daemon runs correctly"
```
