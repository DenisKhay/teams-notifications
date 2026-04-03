from datetime import datetime, timezone

from teams_notifications.state import (
    ChatInfo,
    ChannelMessageInfo,
    UnreadState,
    FilterConfig,
    filter_notifications,
)


def _utc(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def test_unread_state_total_count():
    state = UnreadState()
    state.chats = {
        "chat1": ChatInfo(
            chat_id="chat1", chat_type="oneOnOne", sender_name="Alice",
            sender_id="user-id-alice", last_message="Hello",
            last_message_time=_utc(2026, 4, 3, 10), last_read_time=_utc(2026, 4, 3, 9)),
        "chat2": ChatInfo(
            chat_id="chat2", chat_type="group", sender_name="Bob",
            sender_id="user-id-bob", last_message="Hey",
            last_message_time=_utc(2026, 4, 3, 11), last_read_time=_utc(2026, 4, 3, 10)),
    }
    state.channel_mentions = [
        ChannelMessageInfo(team_name="Engineering", channel_name="General",
                           sender_name="Carol", message_preview="@Denis check this",
                           timestamp=_utc(2026, 4, 3, 12)),
    ]
    assert state.total_unread == 3
    assert state.dm_count == 1
    assert state.group_count == 1
    assert state.mention_count == 1


def test_unread_state_is_empty():
    state = UnreadState()
    assert state.is_empty is True
    assert state.total_unread == 0


def test_merge_replaces_state():
    old = UnreadState()
    old.chats = {
        "chat1": ChatInfo(chat_id="chat1", chat_type="oneOnOne", sender_name="Alice",
                          sender_id="user-id-alice", last_message="Old",
                          last_message_time=_utc(2026, 4, 3, 10), last_read_time=_utc(2026, 4, 3, 9)),
    }
    new = UnreadState()
    merged = new
    assert merged.is_empty is True


def test_filter_all_mode():
    chats = [
        ChatInfo(chat_id="c1", chat_type="oneOnOne", sender_name="Alice",
                 sender_id="uid1", last_message="Hi",
                 last_message_time=_utc(2026, 4, 3, 10), last_read_time=_utc(2026, 4, 3, 9)),
    ]
    mentions = [
        ChannelMessageInfo(team_name="T", channel_name="General",
                           sender_name="Bob", message_preview="@Denis",
                           timestamp=_utc(2026, 4, 3, 11)),
    ]
    fc = FilterConfig(mode="all", whitelist=[], blacklist=[], exclude_bots=False)
    filtered_chats, filtered_mentions = filter_notifications(chats, mentions, fc)
    assert len(filtered_chats) == 1
    assert len(filtered_mentions) == 1


def test_filter_mentions_and_dms_only():
    chats = [
        ChatInfo(chat_id="c1", chat_type="oneOnOne", sender_name="Alice",
                 sender_id="uid1", last_message="Hi",
                 last_message_time=_utc(2026, 4, 3, 10), last_read_time=_utc(2026, 4, 3, 9)),
        ChatInfo(chat_id="c2", chat_type="group", sender_name="Bob",
                 sender_id="uid2", last_message="Hey team",
                 last_message_time=_utc(2026, 4, 3, 10), last_read_time=_utc(2026, 4, 3, 9)),
    ]
    mentions = [
        ChannelMessageInfo(team_name="T", channel_name="General",
                           sender_name="Carol", message_preview="@Denis",
                           timestamp=_utc(2026, 4, 3, 11)),
    ]
    fc = FilterConfig(mode="mentions_and_dms", whitelist=[], blacklist=[], exclude_bots=False)
    filtered_chats, filtered_mentions = filter_notifications(chats, mentions, fc)
    assert len(filtered_chats) == 1
    assert filtered_chats[0].chat_type == "oneOnOne"
    assert len(filtered_mentions) == 1


def test_filter_blacklist_overrides():
    chats = [
        ChatInfo(chat_id="c1", chat_type="oneOnOne", sender_name="Alice",
                 sender_id="uid1", last_message="Hi",
                 last_message_time=_utc(2026, 4, 3, 10), last_read_time=_utc(2026, 4, 3, 9)),
    ]
    fc = FilterConfig(mode="all", whitelist=[], blacklist=["user:Alice"], exclude_bots=False)
    filtered_chats, filtered_mentions = filter_notifications(chats, [], fc)
    assert len(filtered_chats) == 0


def test_filter_whitelist_overrides_mode():
    chats = [
        ChatInfo(chat_id="c1", chat_type="group", sender_name="Alice",
                 sender_id="uid1", last_message="Hey",
                 last_message_time=_utc(2026, 4, 3, 10), last_read_time=_utc(2026, 4, 3, 9)),
    ]
    fc = FilterConfig(mode="dms_only", whitelist=["user:Alice"], blacklist=[], exclude_bots=False)
    filtered_chats, filtered_mentions = filter_notifications(chats, [], fc)
    assert len(filtered_chats) == 1
