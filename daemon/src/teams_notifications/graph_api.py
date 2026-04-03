from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx
import msal

from .config import Config
from .state import ChatInfo, ChannelMessageInfo

log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SCOPES = [
    "Chat.Read",
    "ChannelMessage.Read.All",
    "User.Read",
    "Presence.Read",
    "Team.ReadBasic.All",
    "Channel.ReadBasic.All",
]


def _parse_dt(s: str | None) -> datetime:
    if not s:
        return datetime.min.replace(tzinfo=timezone.utc)
    s = s.replace("Z", "+00:00")
    return datetime.fromisoformat(s)


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def parse_chats_response(response: dict[str, Any]) -> list[ChatInfo]:
    chats = []
    for chat in response.get("value", []):
        preview = chat.get("lastMessagePreview")
        if not preview:
            continue
        viewpoint = chat.get("viewpoint") or {}
        last_read = _parse_dt(viewpoint.get("lastMessageReadDateTime"))
        last_msg_time = _parse_dt(preview.get("createdDateTime"))
        if last_msg_time <= last_read:
            continue
        from_user = (preview.get("from") or {}).get("user") or {}
        body = (preview.get("body") or {}).get("content", "")
        chats.append(ChatInfo(
            chat_id=chat["id"],
            chat_type=chat.get("chatType", "oneOnOne"),
            sender_name=from_user.get("displayName", "Unknown"),
            sender_id=from_user.get("id", ""),
            last_message=_strip_html(body),
            last_message_time=last_msg_time,
            last_read_time=last_read,
        ))
    return chats


def parse_channel_messages(
    messages: list[dict[str, Any]], my_user_id: str,
    team_name: str, channel_name: str,
) -> list[ChannelMessageInfo]:
    result = []
    for msg in messages:
        mentions = msg.get("mentions", [])
        is_mentioned = any(
            (m.get("mentioned") or {}).get("user", {}).get("id") == my_user_id
            for m in mentions
        )
        if not is_mentioned:
            continue
        from_user = (msg.get("from") or {}).get("user") or {}
        body = (msg.get("body") or {}).get("content", "")
        result.append(ChannelMessageInfo(
            team_name=team_name, channel_name=channel_name,
            sender_name=from_user.get("displayName", "Unknown"),
            message_preview=_strip_html(body)[:200],
            timestamp=_parse_dt(msg.get("createdDateTime")),
        ))
    return result


class GraphClient:
    def __init__(self, config: Config):
        self._config = config
        self._app: msal.PublicClientApplication | None = None
        self._http = httpx.AsyncClient(timeout=30.0)
        self._my_user_id: str | None = None
        self._delta_links: dict[str, str] = {}

    def _get_msal_app(self) -> msal.PublicClientApplication:
        if self._app is None:
            if not self._config.client_id or not self._config.tenant_id:
                raise RuntimeError("Graph API not configured. Set client_id and tenant_id in settings.")
            self._app = msal.PublicClientApplication(
                client_id=self._config.client_id,
                authority=f"https://login.microsoftonline.com/{self._config.tenant_id}",
            )
        return self._app

    async def authenticate_interactive(self) -> str:
        app = self._get_msal_app()
        accounts = app.get_accounts()
        if accounts:
            result = app.acquire_token_silent(scopes=SCOPES, account=accounts[0])
            if result and "access_token" in result:
                return result["access_token"]
        result = app.acquire_token_interactive(scopes=SCOPES, prompt="select_account")
        if "access_token" in result:
            return result["access_token"]
        error = result.get("error", "")
        description = result.get("error_description", "")
        if "AADSTS65001" in description or "admin_consent" in error:
            raise PermissionError(
                "Your org admin needs to approve this app's permissions. "
                "Ask your admin for consent, or the daemon will run in PWA-only mode."
            )
        raise RuntimeError(f"Auth failed: {error}: {description}")

    async def get_token(self) -> str:
        app = self._get_msal_app()
        accounts = app.get_accounts()
        if not accounts:
            raise RuntimeError("Not authenticated. Run interactive auth first.")
        result = app.acquire_token_silent(scopes=SCOPES, account=accounts[0])
        if result and "access_token" in result:
            return result["access_token"]
        raise RuntimeError("Token refresh failed. Re-authenticate.")

    async def _get(self, url: str, token: str) -> dict:
        headers = {"Authorization": f"Bearer {token}"}
        for attempt in range(3):
            resp = await self._http.get(url, headers=headers)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "30"))
                log.warning("Throttled, retrying in %ds", retry_after)
                await asyncio.sleep(retry_after)
                continue
            resp.raise_for_status()
        raise RuntimeError(f"Failed after 3 retries: {url}")

    async def get_my_user_id(self, token: str) -> str:
        if self._my_user_id:
            return self._my_user_id
        data = await self._get(f"{GRAPH_BASE}/me", token)
        self._my_user_id = data["id"]
        return self._my_user_id

    async def get_unread_chats(self, token: str) -> list[ChatInfo]:
        url = f"{GRAPH_BASE}/me/chats?$expand=lastMessagePreview&$top=50"
        data = await self._get(url, token)
        return parse_chats_response(data)

    async def get_joined_teams(self, token: str) -> list[dict]:
        data = await self._get(f"{GRAPH_BASE}/me/joinedTeams", token)
        return data.get("value", [])

    async def get_channels(self, token: str, team_id: str) -> list[dict]:
        data = await self._get(f"{GRAPH_BASE}/teams/{team_id}/channels", token)
        return data.get("value", [])

    async def get_channel_messages_delta(
        self, token: str, team_id: str, channel_id: str,
        team_name: str, channel_name: str,
    ) -> list[ChannelMessageInfo]:
        delta_key = f"{team_id}/{channel_id}"
        url = self._delta_links.get(delta_key)
        if not url:
            url = f"{GRAPH_BASE}/teams/{team_id}/channels/{channel_id}/messages/delta?$top=50"
        my_id = await self.get_my_user_id(token)
        all_mentions = []
        while url:
            data = await self._get(url, token)
            messages = data.get("value", [])
            mentions = parse_channel_messages(messages, my_id, team_name, channel_name)
            all_mentions.extend(mentions)
            if "@odata.deltaLink" in data:
                self._delta_links[delta_key] = data["@odata.deltaLink"]
                url = None
            elif "@odata.nextLink" in data:
                url = data["@odata.nextLink"]
            else:
                url = None
        return all_mentions

    async def close(self):
        await self._http.aclose()
