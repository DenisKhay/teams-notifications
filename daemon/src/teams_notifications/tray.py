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
    OFF_HOURS = "off_hours"
    ERROR = "error"


STATE_COLORS = {
    TrayState.OK: QColor(0, 230, 64),           # bright green
    TrayState.UNREAD: QColor(255, 40, 40),       # bright red
    TrayState.TEAMS_DOWN: QColor(255, 200, 0),   # bright yellow
    TrayState.OFF_HOURS: QColor(90, 90, 90),     # dark gray
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

        self._menu = QMenu()
        self._actions = []

        action_open = QAction("Open Teams", self._menu)
        action_open.triggered.connect(
            lambda: webbrowser.open("https://teams.microsoft.com")
        )
        self._menu.addAction(action_open)
        self._actions.append(action_open)
        self._menu.addSeparator()

        for label, seconds in [
            ("Snooze 15 min", 900),
            ("Snooze 30 min", 1800),
            ("Snooze 1 hour", 3600),
        ]:
            action = QAction(label, self._menu)
            action.triggered.connect(
                lambda checked, s=seconds: on_snooze(s)
            )
            self._menu.addAction(action)
            self._actions.append(action)

        self._menu.addSeparator()
        action_settings = QAction("Settings...", self._menu)
        action_settings.triggered.connect(on_settings)
        self._menu.addAction(action_settings)
        self._actions.append(action_settings)
        self._menu.addSeparator()
        action_quit = QAction("Quit", self._menu)
        action_quit.triggered.connect(on_quit)
        self._menu.addAction(action_quit)
        self._actions.append(action_quit)
        self._tray.setContextMenu(self._menu)

    def update(self, state: UnreadState, teams_running: bool = True, working_hours: bool = True) -> None:
        import logging
        log = logging.getLogger(__name__)
        self._current_state = state
        self._unread_count = state.total_unread
        log.debug("tray.update: working_hours=%s, teams_running=%s, empty=%s",
                  working_hours, teams_running, state.is_empty)

        if not working_hours:
            self._state = TrayState.OFF_HOURS
            self._tray.setToolTip("Teams Notifications — Outside working hours")
        elif not teams_running:
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
