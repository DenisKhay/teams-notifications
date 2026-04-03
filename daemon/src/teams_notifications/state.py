from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ChatInfo:
    chat_id: str
    chat_type: str  # "oneOnOne", "group", "meeting"
    sender_name: str
    sender_id: str  # Azure AD user ID (GUID)
    last_message: str
    last_message_time: datetime
    last_read_time: datetime


@dataclass
class ChannelMessageInfo:
    team_name: str
    channel_name: str
    sender_name: str
    message_preview: str
    timestamp: datetime


@dataclass
class UnreadState:
    chats: dict[str, ChatInfo] = field(default_factory=dict)
    channel_mentions: list[ChannelMessageInfo] = field(default_factory=list)
    last_updated: datetime | None = None

    @property
    def total_unread(self) -> int:
        return len(self.chats) + len(self.channel_mentions)

    @property
    def dm_count(self) -> int:
        return sum(1 for c in self.chats.values() if c.chat_type == "oneOnOne")

    @property
    def group_count(self) -> int:
        return sum(1 for c in self.chats.values() if c.chat_type in ("group", "meeting"))

    @property
    def mention_count(self) -> int:
        return len(self.channel_mentions)

    @property
    def is_empty(self) -> bool:
        return self.total_unread == 0

    def summary(self) -> str:
        if self.is_empty:
            return "No unread messages"
        parts = []
        if self.dm_count:
            parts.append(f"{self.dm_count} DM{'s' if self.dm_count != 1 else ''}")
        if self.group_count:
            parts.append(f"{self.group_count} group")
        if self.mention_count:
            parts.append(f"{self.mention_count} mention{'s' if self.mention_count != 1 else ''}")
        return f"{self.total_unread} unread — {', '.join(parts)}"


@dataclass
class FilterConfig:
    mode: str  # "all", "mentions_and_dms", "dms_only"
    whitelist: list[str]
    blacklist: list[str]
    exclude_bots: bool


def _matches_filter(name: str, channel: str, entries: list[str]) -> bool:
    for entry in entries:
        if entry.startswith("user:") and entry[5:].lower() == name.lower():
            return True
        if entry.startswith("channel:") and entry[8:].lower() == channel.lower():
            return True
    return False


def filter_notifications(
    chats: list[ChatInfo],
    mentions: list[ChannelMessageInfo],
    fc: FilterConfig,
) -> tuple[list[ChatInfo], list[ChannelMessageInfo]]:
    filtered_chats = []
    for chat in chats:
        if _matches_filter(chat.sender_name, "", fc.blacklist):
            continue
        if _matches_filter(chat.sender_name, "", fc.whitelist):
            filtered_chats.append(chat)
            continue
        if fc.mode == "all":
            filtered_chats.append(chat)
        elif fc.mode in ("mentions_and_dms", "dms_only"):
            if chat.chat_type == "oneOnOne":
                filtered_chats.append(chat)

    filtered_mentions = []
    for mention in mentions:
        if _matches_filter("", mention.channel_name, fc.blacklist):
            continue
        if _matches_filter("", mention.channel_name, fc.whitelist):
            filtered_mentions.append(mention)
            continue
        if fc.mode in ("all", "mentions_and_dms"):
            filtered_mentions.append(mention)

    return filtered_chats, filtered_mentions
