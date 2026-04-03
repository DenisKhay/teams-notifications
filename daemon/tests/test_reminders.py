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
    assert rs.should_remind(now + timedelta(seconds=100)) is False
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
    assert rs.current_tier == EscalationTier.PERSISTENT
    for i in range(3):
        rs.fire_reminder(now + timedelta(seconds=60 * (i + 4)))
    assert rs.current_tier == EscalationTier.SOUND


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
    assert rs.should_remind(now + timedelta(seconds=602)) is False
    assert rs.should_remind(now + timedelta(seconds=1202)) is True


def test_get_urgency():
    rs = ReminderScheduler(interval_sec=60, tier2_after=2, tier3_after=4)
    assert rs.get_urgency() == Urgency.NORMAL
    now = datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc)
    rs.start(now)
    rs.fire_reminder(now + timedelta(seconds=61))
    rs.fire_reminder(now + timedelta(seconds=122))
    assert rs.get_urgency() == Urgency.CRITICAL
