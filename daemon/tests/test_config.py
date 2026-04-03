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
whitelist = ["user:Alice"]
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
    assert config.whitelist == ["user:Alice"]
    assert config.blacklist == ["channel:Random"]
    assert config.exclude_bots is True
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
