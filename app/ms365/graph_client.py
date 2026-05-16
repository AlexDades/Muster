"""Thin authenticated wrapper around Microsoft Graph API."""
from __future__ import annotations
import html
import re
from typing import Optional
import msal
import httpx
from app.config import settings

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_SCOPES = ["https://graph.microsoft.com/.default"]

_MSG_SELECT = "id,subject,from,body,receivedDateTime,isRead,conversationId"
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode entities (Graph returns HTML bodies)."""
    stripped = _HTML_TAG_RE.sub(" ", text)
    return html.unescape(stripped).strip()


def _acquire_token() -> str:
    app = msal.ConfidentialClientApplication(
        client_id=settings.ms365_client_id,
        client_credential=settings.ms365_client_secret,
        authority=f"https://login.microsoftonline.com/{settings.ms365_tenant_id}",
    )
    result = (
        app.acquire_token_silent(_SCOPES, account=None)
        or app.acquire_token_for_client(scopes=_SCOPES)
    )
    if "access_token" not in result:
        raise RuntimeError(
            f"M365 token acquisition failed: {result.get('error_description', result.get('error'))}"
        )
    return result["access_token"]


class GraphClient:
    def __init__(self, token: Optional[str] = None):
        self._token = token or _acquire_token()
        self._mailbox = settings.ms365_mailbox
        self._headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        r = httpx.get(f"{GRAPH_BASE}{path}", headers=self._headers, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, json: Optional[dict] = None) -> httpx.Response:
        r = httpx.post(f"{GRAPH_BASE}{path}", headers=self._headers, json=json or {}, timeout=30)
        r.raise_for_status()
        return r

    def _patch(self, path: str, json: dict) -> None:
        r = httpx.patch(f"{GRAPH_BASE}{path}", headers=self._headers, json=json, timeout=30)
        r.raise_for_status()

    def get_messages(self, unread_only: bool = True, top: int = 50) -> list[dict]:
        params: dict = {"$select": _MSG_SELECT, "$top": top, "$orderby": "receivedDateTime asc"}
        if unread_only:
            params["$filter"] = "isRead eq false"
        data = self._get(f"/users/{self._mailbox}/messages", params=params)
        messages = data.get("value", [])
        for m in messages:
            if m.get("body", {}).get("contentType") == "html":
                m["body"]["content"] = _strip_html(m["body"]["content"])
        return messages

    def send_reply(self, message_id: str, reply_text: str) -> None:
        """Create a reply draft then send it (keeps the conversation thread)."""
        resp = self._post(
            f"/users/{self._mailbox}/messages/{message_id}/createReply",
            {"comment": reply_text},
        )
        draft_id = resp.json()["id"]
        self._post(f"/users/{self._mailbox}/messages/{draft_id}/send")

    def mark_as_read(self, message_id: str) -> None:
        self._patch(f"/users/{self._mailbox}/messages/{message_id}", {"isRead": True})
