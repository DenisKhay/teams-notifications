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
