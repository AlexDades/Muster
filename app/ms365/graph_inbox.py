"""Drop-in replacement for MockInbox backed by Microsoft Graph API.

Satisfies the same interface as MockInbox so the poller and dispatcher
work unchanged. Uses Graph message IDs in place of SQLite integer IDs.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from app.email_ingestion.models import Email
from app.ms365.graph_client import GraphClient


def _msg_to_email(msg: dict) -> Email:
    received_raw = msg.get("receivedDateTime", "")
    try:
        received_at = datetime.fromisoformat(received_raw.rstrip("Z"))
    except (ValueError, AttributeError):
        received_at = datetime.utcnow()

    return Email(
        id=msg["id"],  # Graph message ID (string) — used as the handle for mark_replied/failed
        message_id=msg["id"],
        sender=msg.get("from", {}).get("emailAddress", {}).get("address", ""),
        subject=msg.get("subject", ""),
        body=msg.get("body", {}).get("content", ""),
        received_at=received_at,
        status="replied" if msg.get("isRead") else "unread",
    )


class GraphInbox:
    def __init__(self, client: Optional[GraphClient] = None):
        self._client = client or GraphClient()

    def get_unread(self) -> list[Email]:
        return [_msg_to_email(m) for m in self._client.get_messages(unread_only=True)]

    def get_all(self) -> list[Email]:
        return [_msg_to_email(m) for m in self._client.get_messages(unread_only=False)]

    def mark_replied(self, email_id: str, reply_body: str) -> None:
        self._client.send_reply(email_id, reply_body)
        self._client.mark_as_read(email_id)

    def mark_failed(self, email_id: str) -> None:
        # Mark as read so the message isn't re-processed on the next poll
        self._client.mark_as_read(email_id)

    def count(self, status: Optional[str] = None) -> int:
        unread_only = status == "unread"
        return len(self._client.get_messages(unread_only=unread_only))
