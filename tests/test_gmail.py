"""Gmail inbox unit tests — all network calls are mocked (imaplib + smtplib)."""
from __future__ import annotations
import email as _email
import email.mime.multipart
import email.mime.text
import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime

from app.gmail.gmail_inbox import GmailInbox, _decode_header, _extract_body, _strip_html


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_raw_message(
    subject: str = "Test subject",
    sender: str = "emp@co.com",
    body: str = "How many vacation days do I get?",
    message_id: str = "<msg001@mail.gmail.com>",
    date: str = "Thu, 08 May 2026 09:00:00 +0000",
) -> bytes:
    msg = _email.mime.multipart.MIMEMultipart("alternative")
    msg["From"] = sender
    msg["To"] = "hr@co.com"
    msg["Subject"] = subject
    msg["Message-ID"] = message_id
    msg["Date"] = date
    msg.attach(_email.mime.text.MIMEText(body, "plain"))
    return msg.as_bytes()


def _make_imap(uids: list[str] = None, raw: bytes = None) -> MagicMock:
    imap = MagicMock()
    uid_bytes = b" ".join(u.encode() for u in (uids or ["1"]))
    imap.uid.side_effect = _make_imap_uid_side_effect(uid_bytes, raw or _make_raw_message())
    return imap


def _make_imap_uid_side_effect(uid_bytes: bytes, raw: bytes):
    def side_effect(cmd, *args):
        if cmd == "search":
            return ("OK", [uid_bytes])
        if cmd == "fetch":
            return ("OK", [(None, raw)])
        if cmd == "store":
            return ("OK", [])
        return ("OK", [])
    return side_effect


# ── Unit tests: helpers ───────────────────────────────────────────────────────

class TestHelpers:
    def test_strip_html_removes_tags(self):
        assert "<" not in _strip_html("<p>Hello <b>world</b></p>")
        assert "Hello" in _strip_html("<p>Hello <b>world</b></p>")

    def test_strip_html_decodes_entities(self):
        assert "&" in _strip_html("a &amp; b")

    def test_decode_header_plain(self):
        assert _decode_header("Hello World") == "Hello World"

    def test_decode_header_empty(self):
        assert _decode_header("") == ""

    def test_decode_header_encoded(self):
        # RFC-2047 base64 encoded "Hello"
        encoded = "=?utf-8?b?SGVsbG8=?="
        assert _decode_header(encoded) == "Hello"

    def test_extract_body_plain_text(self):
        msg = _email.message_from_bytes(_make_raw_message(body="Plain text body"))
        assert _extract_body(msg) == "Plain text body"

    def test_extract_body_html_fallback(self):
        html_msg = _email.mime.multipart.MIMEMultipart("alternative")
        html_msg.attach(_email.mime.text.MIMEText("<p>HTML body</p>", "html"))
        parsed = _email.message_from_bytes(html_msg.as_bytes())
        body = _extract_body(parsed)
        assert "<" not in body
        assert "HTML body" in body

    def test_extract_body_single_part(self):
        msg = _email.mime.text.MIMEText("Single part body", "plain")
        parsed = _email.message_from_bytes(msg.as_bytes())
        assert "Single part body" in _extract_body(parsed)


# ── Unit tests: GmailInbox ────────────────────────────────────────────────────

class TestGmailInbox:
    def _inbox(self, imap: MagicMock) -> GmailInbox:
        inbox = GmailInbox(address="hr@co.com", app_password="test pass word")
        inbox._connect = lambda: imap
        return inbox

    def test_password_strips_spaces(self):
        inbox = GmailInbox(address="hr@co.com", app_password="abcd efgh ijkl mnop")
        assert " " not in inbox._password

    def test_get_unread_searches_unseen(self):
        imap = _make_imap(["1"])
        inbox = self._inbox(imap)
        emails = inbox.get_unread()
        search_call = imap.uid.call_args_list[0]
        assert search_call == call("search", None, "UNSEEN")
        assert len(emails) == 1

    def test_get_all_searches_all(self):
        imap = _make_imap(["1"])
        inbox = self._inbox(imap)
        inbox.get_all()
        search_call = imap.uid.call_args_list[0]
        assert search_call == call("search", None, "ALL")

    def test_get_unread_maps_fields(self):
        raw = _make_raw_message(
            subject="PTO question",
            sender="emp@company.com",
            body="How many days off?",
            message_id="<unique-id@mail>",
        )
        imap = _make_imap(["42"], raw)
        inbox = self._inbox(imap)
        emails = inbox.get_unread()
        e = emails[0]
        assert e.id == "42"
        assert e.subject == "PTO question"
        assert e.sender == "emp@company.com"
        assert e.body == "How many days off?"
        assert e.status == "unread"
        assert e.message_id == "<unique-id@mail>"

    def test_get_unread_empty_inbox(self):
        imap = MagicMock()
        imap.uid.return_value = ("OK", [b""])
        inbox = self._inbox(imap)
        assert inbox.get_unread() == []

    def test_get_unread_multiple_messages(self):
        calls = []

        def uid_side(cmd, *args):
            if cmd == "search":
                return ("OK", [b"1 2 3"])
            if cmd == "fetch":
                uid = args[0]
                raw = _make_raw_message(subject=f"Subject {uid.decode()}", sender=f"s{uid.decode()}@co.com")
                return ("OK", [(None, raw)])
            return ("OK", [])

        imap = MagicMock()
        imap.uid.side_effect = uid_side
        inbox = self._inbox(imap)
        emails = inbox.get_unread()
        assert len(emails) == 3

    def test_mark_replied_sends_and_marks_seen(self):
        imap = _make_imap(["5"])
        inbox = self._inbox(imap)

        with patch.object(inbox, "_send_reply") as mock_send:
            inbox.mark_replied("5", "You get 15 days.")
            mock_send.assert_called_once()
            reply_text = mock_send.call_args[0][1]
            assert reply_text == "You get 15 days."

        store_call = imap.uid.call_args_list[-1]
        assert store_call == call("store", "5", "+FLAGS", r"(\Seen)")

    def test_mark_failed_marks_seen_without_reply(self):
        imap = _make_imap(["7"])
        inbox = self._inbox(imap)

        with patch.object(inbox, "_send_reply") as mock_send:
            inbox.mark_failed("7")
            mock_send.assert_not_called()

        store_call = imap.uid.call_args_list[-1]
        assert store_call == call("store", "7", "+FLAGS", r"(\Seen)")

    def test_count_unread(self):
        imap = MagicMock()
        imap.uid.return_value = ("OK", [b"1 2 3"])
        inbox = self._inbox(imap)
        assert inbox.count(status="unread") == 3
        search_call = imap.uid.call_args_list[0]
        assert "UNSEEN" in search_call[0]

    def test_count_all(self):
        imap = MagicMock()
        imap.uid.return_value = ("OK", [b"1 2"])
        inbox = self._inbox(imap)
        assert inbox.count() == 2
        search_call = imap.uid.call_args_list[0]
        assert "ALL" in search_call[0]

    def test_send_reply_uses_smtp(self):
        raw = _make_raw_message(
            subject="PTO",
            sender="emp@co.com",
            message_id="<orig@mail>",
        )
        original = _email.message_from_bytes(raw)

        inbox = GmailInbox(address="hr@co.com", app_password="testpass")
        with patch("app.gmail.gmail_inbox.smtplib") as mock_smtp_mod:
            smtp_ctx = MagicMock()
            mock_smtp_mod.SMTP.return_value.__enter__ = lambda s: smtp_ctx
            mock_smtp_mod.SMTP.return_value.__exit__ = MagicMock(return_value=False)
            inbox._send_reply(original, "Here is your answer.")
            smtp_ctx.sendmail.assert_called_once()
            args = smtp_ctx.sendmail.call_args[0]
            assert args[0] == "hr@co.com"
            assert args[1] == "emp@co.com"

    def test_send_reply_adds_re_prefix(self):
        raw = _make_raw_message(subject="PTO question", sender="emp@co.com")
        original = _email.message_from_bytes(raw)

        inbox = GmailInbox(address="hr@co.com", app_password="testpass")
        with patch("app.gmail.gmail_inbox.smtplib") as mock_smtp_mod:
            smtp_ctx = MagicMock()
            mock_smtp_mod.SMTP.return_value.__enter__ = lambda s: smtp_ctx
            mock_smtp_mod.SMTP.return_value.__exit__ = MagicMock(return_value=False)
            inbox._send_reply(original, "Answer.")
            _, _, raw_msg = smtp_ctx.sendmail.call_args[0]
            parsed_reply = _email.message_from_string(raw_msg)
            assert parsed_reply["Subject"].startswith("Re:")

    def test_send_reply_sets_threading_headers(self):
        raw = _make_raw_message(subject="Q", sender="emp@co.com", message_id="<orig123@mail>")
        original = _email.message_from_bytes(raw)

        inbox = GmailInbox(address="hr@co.com", app_password="testpass")
        with patch("app.gmail.gmail_inbox.smtplib") as mock_smtp_mod:
            smtp_ctx = MagicMock()
            mock_smtp_mod.SMTP.return_value.__enter__ = lambda s: smtp_ctx
            mock_smtp_mod.SMTP.return_value.__exit__ = MagicMock(return_value=False)
            inbox._send_reply(original, "Answer.")
            _, _, raw_msg = smtp_ctx.sendmail.call_args[0]
            parsed_reply = _email.message_from_string(raw_msg)
            assert parsed_reply["In-Reply-To"] == "<orig123@mail>"
            assert "<orig123@mail>" in parsed_reply["References"]

    def test_send_reply_none_original_is_noop(self):
        inbox = GmailInbox(address="hr@co.com", app_password="testpass")
        with patch("app.gmail.gmail_inbox.smtplib") as mock_smtp_mod:
            inbox._send_reply(None, "Answer.")
            mock_smtp_mod.SMTP.assert_not_called()


# ── Dependency injection test ─────────────────────────────────────────────────

class TestGmailDependency:
    def test_returns_gmail_inbox_when_configured(self):
        with patch("app.dependencies.settings") as mock_cfg:
            mock_cfg.gmail_use_inbox = True
            mock_cfg.gmail_address = "hr@co.com"
            mock_cfg.gmail_app_password = "testpass"
            with patch("app.gmail.gmail_inbox.settings") as gmail_cfg:
                gmail_cfg.gmail_address = "hr@co.com"
                gmail_cfg.gmail_app_password = "testpass"
                from app.dependencies import get_inbox
                from app.gmail.gmail_inbox import GmailInbox
                inbox = get_inbox()
                assert isinstance(inbox, GmailInbox)

    def test_gmail_takes_priority_over_ms365(self):
        with patch("app.dependencies.settings") as mock_cfg:
            mock_cfg.gmail_use_inbox = True
            mock_cfg.ms365_use_real_inbox = True
            mock_cfg.gmail_address = "hr@co.com"
            mock_cfg.gmail_app_password = "testpass"
            with patch("app.gmail.gmail_inbox.settings") as gmail_cfg:
                gmail_cfg.gmail_address = "hr@co.com"
                gmail_cfg.gmail_app_password = "testpass"
                from app.dependencies import get_inbox
                from app.gmail.gmail_inbox import GmailInbox
                inbox = get_inbox()
                assert isinstance(inbox, GmailInbox)


# ── Integration test (skipped without real credentials) ───────────────────────

@pytest.fixture(scope="session")
def gmail_credentials():
    from app.config import settings
    if not settings.gmail_address or not settings.gmail_app_password:
        pytest.skip("GMAIL_ADDRESS and GMAIL_APP_PASSWORD not set")
    return settings


@pytest.mark.integration
def test_gmail_inbox_can_connect(gmail_credentials):
    from app.gmail.gmail_inbox import GmailInbox
    inbox = GmailInbox()
    messages = inbox.get_all()
    assert isinstance(messages, list)
