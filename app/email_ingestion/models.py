from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Email:
    sender: str
    subject: str
    body: str
    message_id: str
    received_at: datetime = field(default_factory=datetime.utcnow)
    id: Optional[int] = None
    status: str = "unread"
    reply_body: Optional[str] = None
    replied_at: Optional[datetime] = None
