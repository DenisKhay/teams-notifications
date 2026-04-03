from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone

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
        if msg_type == "ping":
            log.debug("Ping from native host")
        elif msg_type == "badge":
            count = msg.get("count", 0)
            log.info("Badge update from PWA: %d", count)
            # Update tray with badge count from PWA
            if count > 0 and self._tray:
                from .state import ChatInfo
                # Create a synthetic unread state from badge count
                now = datetime.now(timezone.utc)
                new_state = UnreadState(last_updated=now)
                new_state.chats["pwa_badge"] = ChatInfo(
                    chat_id="pwa_badge", chat_type="oneOnOne",
                    sender_name="Teams", sender_id="",
                    last_message=f"{count} unread message{'s' if count != 1 else ''}",
                    last_message_time=now, last_read_time=datetime.min.replace(tzinfo=timezone.utc),
                )
                self._state = new_state
                self._tray.update(self._state, self._teams_running)
            elif count == 0 and self._tray:
                self._state = UnreadState()
                self._tray.update(self._state, self._teams_running)
                self._reminder.reset()
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

    async def _reminder_loop(self) -> None:
        """Check every 30s if a reminder notification should fire."""
        while self._running:
            now = datetime.now(timezone.utc)
            if not self._state.is_empty:
                self._reminder.start(now)
                should = self._reminder.should_remind(now)
                log.debug("Reminder check: count=%d, should=%s, snoozed=%s, last=%s",
                          self._state.total_unread, should,
                          self._reminder.is_snoozed, self._reminder._last_reminder_at)
                if should:
                    log.info("Firing reminder notification: %s", self._state.summary())
                    send_notification(Notification(
                        title="Teams — Unread Messages",
                        body=self._state.summary(),
                        sound_file=self._config.sound_file,
                    ))
                    self._reminder.fire_reminder(now)
            else:
                self._reminder.reset()
            await asyncio.sleep(30)

    async def run_async(self) -> None:
        self._running = True
        socket_server = SocketServer(on_message=self._on_socket_message)
        await socket_server.start()
        try:
            await asyncio.gather(
                self._poll_loop(),
                self._watchdog_loop(),
                self._reminder_loop(),
            )
        finally:
            await socket_server.stop()
            await self._graph.close()

    def stop(self) -> None:
        self._running = False


def main():
    logging.basicConfig(
        level=logging.DEBUG,
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
