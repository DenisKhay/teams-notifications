from __future__ import annotations

import logging
import subprocess

log = logging.getLogger(__name__)

TEAMS_APP_IDS = [
    "cifhbcnohmdccbgoicgdjpfamggdegmo",
    "lhkgjmfkhgocfcnphhacgheobkdlkifg",
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
