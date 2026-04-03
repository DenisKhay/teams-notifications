from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "teams-notifications" / "config.toml"


@dataclass
class Config:
    check_interval_sec: int = 30
    reminder_interval_sec: int = 300
    watchdog_interval_sec: int = 60
    watchdog_grace_checks: int = 2
    escalation_enabled: bool = True
    escalation_tier2_after: int = 3
    escalation_tier3_after: int = 6
    sound_file: str = "/usr/share/sounds/Oxygen-Im-Message-In.ogg"
    escalation_sound_file: str = "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"
    filter_mode: str = "all"
    whitelist: list[str] = field(default_factory=list)
    blacklist: list[str] = field(default_factory=list)
    exclude_bots: bool = False
    show_count_badge: bool = True
    show_message_preview: bool = True
    max_preview_length: int = 100
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
