"""Gmail inbox backed by IMAP (read) and SMTP (send).

Uses Python's standard library only — no extra packages required.
Authentication uses a Gmail App Password (Google Account → Security → App Passwords).
"""
from __future__ import annotations
import email
import email.header
import email.utils
import imaplib
import re
import smtplib
import textwrap
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from app.email_ingestion.models import Email
from app.config import settings

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    import html as _html
    return _html.unescape(_HTML_TAG_RE.sub(" ", text)).strip()


def _decode_header(value: str) -> str:
    """Decode RFC-2047 encoded email header value."""
    if not value:
        return ""
    parts = email.header.decode_header(value)
    decoded = []
    for chunk, charset in parts:
        if isinstance(chunk, bytes):
            decoded.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(chunk)
    return " ".join(decoded)


def _extract_body(msg: email.message.Message) -> str:
    """Return plain-text body from a possibly multipart MIME message."""
    if msg.is_multipart():
        # Prefer plain text part
        for part in msg.walk():
            ct = part.get_content_type()
            disp = part.get("Content-Disposition", "")
            if ct == "text/plain" and "attachment" not in disp:
                charset = part.get_content_charset() or "utf-8"
                return part.get_payload(decode=True).decode(charset, errors="replace")
        # Fall back to HTML
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                charset = part.get_content_charset() or "utf-8"
                raw = part.get_payload(decode=True).decode(charset, errors="replace")
                return _strip_html(raw)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            return _strip_html(text) if msg.get_content_type() == "text/html" else text
    return ""


def _parse_sender_address(from_header: str) -> str:
    _, addr = email.utils.parseaddr(from_header)
    return addr or from_header


def _fetch_messages(imap: imaplib.IMAP4_SSL, unread_only: bool) -> list[Email]:
    imap.select("INBOX")
    criterion = "UNSEEN" if unread_only else "ALL"
    _, uid_data = imap.uid("search", None, criterion)
    uids = uid_data[0].split() if uid_data[0] else []

    emails = []
    for uid in uids:
        _, msg_data = imap.uid("fetch", uid, "(RFC822)")
        raw = msg_data[0][1] if msg_data and msg_data[0] else None
        if not raw:
            continue
        msg = email.message_from_bytes(raw)
        uid_str = uid.decode() if isinstance(uid, bytes) else uid
        received_str = msg.get("Date", "")
        try:
            received_at = email.utils.parsedate_to_datetime(received_str)
            # Convert to naive UTC for consistency with the rest of the app
            received_at = received_at.replace(tzinfo=None)
        except Exception:
            received_at = datetime.utcnow()

        emails.append(Email(
            id=uid_str,
            message_id=msg.get("Message-ID", uid_str),
            sender=_parse_sender_address(msg.get("From", "")),
            subject=_decode_header(msg.get("Subject", "")),
            body=_extract_body(msg),
            received_at=received_at,
            status="unread",
        ))
    return emails


class GmailInbox:
    def __init__(
        self,
        address: Optional[str] = None,
        app_password: Optional[str] = None,
    ):
        self._address = address or settings.gmail_address
        self._password = (app_password or settings.gmail_app_password).replace(" ", "")

    def _connect(self) -> imaplib.IMAP4_SSL:
        imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        imap.login(self._address, self._password)
        return imap

    def get_unread(self) -> list[Email]:
        imap = self._connect()
        try:
            return _fetch_messages(imap, unread_only=True)
        finally:
            imap.logout()

    def get_all(self) -> list[Email]:
        imap = self._connect()
        try:
            return _fetch_messages(imap, unread_only=False)
        finally:
            imap.logout()

    def mark_replied(self, email_id: str, reply_body: str) -> None:
        """Send the reply via SMTP then mark the source message as read."""
        # Fetch the original to get threading headers
        imap = self._connect()
        try:
            imap.select("INBOX")
            _, msg_data = imap.uid("fetch", email_id, "(RFC822)")
            raw = msg_data[0][1] if msg_data and msg_data[0] else None
            original = email.message_from_bytes(raw) if raw else None
            # Mark as read
            imap.uid("store", email_id, "+FLAGS", r"(\Seen)")
        finally:
            imap.logout()

        self._send_reply(original, reply_body)

    def mark_failed(self, email_id: str) -> None:
        """Mark as read so it's not re-processed."""
        imap = self._connect()
        try:
            imap.select("INBOX")
            imap.uid("store", email_id, "+FLAGS", r"(\Seen)")
        finally:
            imap.logout()

    def count(self, status: Optional[str] = None) -> int:
        imap = self._connect()
        try:
            imap.select("INBOX")
            criterion = "UNSEEN" if status == "unread" else "ALL"
            _, uid_data = imap.uid("search", None, criterion)
            uids = uid_data[0].split() if uid_data[0] else []
            return len(uids)
        finally:
            imap.logout()

    def _send_reply(self, original: Optional[email.message.Message], reply_text: str) -> None:
        if original is None:
            return

        to_addr = _parse_sender_address(original.get("From", ""))
        subject = original.get("Subject", "")
        if not subject.lower().startswith("re:"):
            subject = "Re: " + subject
        orig_message_id = original.get("Message-ID", "")
        orig_references = original.get("References", "")

        reply = MIMEMultipart("alternative")
        reply["From"] = self._address
        reply["To"] = to_addr
        reply["Subject"] = subject
        if orig_message_id:
            reply["In-Reply-To"] = orig_message_id
            reply["References"] = (orig_references + " " + orig_message_id).strip()

        reply.attach(MIMEText(reply_text, "plain"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(self._address, self._password)
            smtp.sendmail(self._address, to_addr, reply.as_string())
