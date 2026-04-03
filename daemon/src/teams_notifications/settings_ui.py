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
        tabs.addTab(self._build_schedule_tab(), "Schedule")
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
        self._bl_input.setPlaceholderText("user:Display Name or channel:Name")
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
        self._wl_input.setPlaceholderText("user:Display Name or channel:Name")
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

    def _build_schedule_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self._chk_schedule = QCheckBox("Enable working hours schedule")
        self._chk_schedule.setChecked(self._config.schedule_enabled)
        layout.addWidget(self._chk_schedule)

        group_hours = QGroupBox("Working Hours")
        hours_form = QFormLayout(group_hours)

        start_layout = QHBoxLayout()
        self._spin_start_hour = QSpinBox()
        self._spin_start_hour.setRange(0, 23)
        self._spin_start_hour.setValue(self._config.schedule_start_hour)
        start_layout.addWidget(self._spin_start_hour)
        start_layout.addWidget(QLabel(":"))
        self._spin_start_minute = QSpinBox()
        self._spin_start_minute.setRange(0, 59)
        self._spin_start_minute.setValue(self._config.schedule_start_minute)
        start_layout.addWidget(self._spin_start_minute)
        hours_form.addRow("Start:", start_layout)

        end_layout = QHBoxLayout()
        self._spin_end_hour = QSpinBox()
        self._spin_end_hour.setRange(0, 23)
        self._spin_end_hour.setValue(self._config.schedule_end_hour)
        end_layout.addWidget(self._spin_end_hour)
        end_layout.addWidget(QLabel(":"))
        self._spin_end_minute = QSpinBox()
        self._spin_end_minute.setRange(0, 59)
        self._spin_end_minute.setValue(self._config.schedule_end_minute)
        end_layout.addWidget(self._spin_end_minute)
        hours_form.addRow("End:", end_layout)

        layout.addWidget(group_hours)

        group_days = QGroupBox("Working Days")
        days_layout = QVBoxLayout(group_days)
        self._day_checks = {}
        for day_code, day_label in [
            ("mon", "Monday"), ("tue", "Tuesday"), ("wed", "Wednesday"),
            ("thu", "Thursday"), ("fri", "Friday"),
            ("sat", "Saturday"), ("sun", "Sunday"),
        ]:
            chk = QCheckBox(day_label)
            chk.setChecked(day_code in self._config.schedule_days)
            self._day_checks[day_code] = chk
            days_layout.addWidget(chk)
        layout.addWidget(group_days)

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
        self._config.schedule_enabled = self._chk_schedule.isChecked()
        self._config.schedule_start_hour = self._spin_start_hour.value()
        self._config.schedule_start_minute = self._spin_start_minute.value()
        self._config.schedule_end_hour = self._spin_end_hour.value()
        self._config.schedule_end_minute = self._spin_end_minute.value()
        self._config.schedule_days = [
            day for day, chk in self._day_checks.items() if chk.isChecked()
        ]

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
