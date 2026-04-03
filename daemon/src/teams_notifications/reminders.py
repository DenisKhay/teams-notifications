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

    def is_snoozed_at(self, now: datetime) -> bool:
        if self._snooze_until is None:
            return False
        if now >= self._snooze_until:
            self._snooze_until = None
            return False
        return True

    @property
    def is_snoozed(self) -> bool:
        return self.is_snoozed_at(datetime.now(timezone.utc))

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
            # Set last_reminder_at far enough back so first reminder fires immediately
            self._last_reminder_at = at - self._interval

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
            return 0
        return 10000
