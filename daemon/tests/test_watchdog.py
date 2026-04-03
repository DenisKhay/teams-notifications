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
    assert wd.should_alert is True


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
