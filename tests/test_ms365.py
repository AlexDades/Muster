"""Microsoft 365 integration tests — all unit tests mock MSAL and httpx."""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from fastapi.testclient import TestClient

from app.main import app
from app.auth.jwt_auth import require_auth
import app.dependencies as deps


# ── Helpers ─────────────────────────────────────────────────────────────────

def _make_graph_message(
    msg_id: str = "AAA123",
    subject: str = "Test subject",
    sender: str = "emp@co.com",
    body: str = "How many days off do I get?",
    is_read: bool = False,
    received: str = "2026-05-08T09:00:00Z",
) -> dict:
    return {
        "id": msg_id,
        "subject": subject,
        "from": {"emailAddress": {"address": sender}},
        "body": {"contentType": "text", "content": body},
        "receivedDateTime": received,
        "isRead": is_read,
        "conversationId": "conv1",
    }


def _mock_graph_client(messages=None) -> MagicMock:
    client = MagicMock()
    client.get_messages.return_value = messages or [_make_graph_message()]
    return client


# ── GraphClient unit tests ───────────────────────────────────────────────────

class TestGraphClient:
    def test_acquire_token_success(self):
        with patch("app.ms365.graph_client.msal") as mock_msal, \
             patch("app.ms365.graph_client.settings") as mock_cfg:
            mock_cfg.ms365_client_id = "cid"
            mock_cfg.ms365_client_secret = "csec"
            mock_cfg.ms365_tenant_id = "tid"
            mock_cfg.ms365_mailbox = "hr@co.com"
            msal_app = MagicMock()
            msal_app.acquire_token_silent.return_value = None
            msal_app.acquire_token_for_client.return_value = {"access_token": "tok123"}
            mock_msal.ConfidentialClientApplication.return_value = msal_app

            from app.ms365.graph_client import _acquire_token
            token = _acquire_token()
            assert token == "tok123"

    def test_acquire_token_failure_raises(self):
        with patch("app.ms365.graph_client.msal") as mock_msal, \
             patch("app.ms365.graph_client.settings"):
            msal_app = MagicMock()
            msal_app.acquire_token_silent.return_value = None
            msal_app.acquire_token_for_client.return_value = {"error": "invalid_client", "error_description": "bad credentials"}
            mock_msal.ConfidentialClientApplication.return_value = msal_app

            from app.ms365.graph_client import _acquire_token
            with pytest.raises(RuntimeError, match="token acquisition failed"):
                _acquire_token()

    def test_get_messages_calls_correct_endpoint(self):
        from app.ms365.graph_client import GraphClient
        with patch("app.ms365.graph_client._acquire_token", return_value="tok"), \
             patch("app.ms365.graph_client.httpx") as mock_httpx, \
             patch("app.ms365.graph_client.settings") as mock_cfg:
            mock_cfg.ms365_mailbox = "hr@co.com"
            resp = MagicMock()
            resp.json.return_value = {"value": [_make_graph_message()]}
            mock_httpx.get.return_value = resp

            client = GraphClient(token="tok")
            msgs = client.get_messages(unread_only=True)

            assert len(msgs) == 1
            call_args = mock_httpx.get.call_args
            assert "hr@co.com" in call_args[0][0]
            assert "isRead eq false" in call_args[1]["params"]["$filter"]

    def test_get_messages_strips_html(self):
        from app.ms365.graph_client import GraphClient
        html_msg = _make_graph_message(body="<p>Hello <b>world</b></p>")
        html_msg["body"]["contentType"] = "html"

        with patch("app.ms365.graph_client._acquire_token", return_value="tok"), \
             patch("app.ms365.graph_client.httpx") as mock_httpx, \
             patch("app.ms365.graph_client.settings") as mock_cfg:
            mock_cfg.ms365_mailbox = "hr@co.com"
            resp = MagicMock()
            resp.json.return_value = {"value": [html_msg]}
            mock_httpx.get.return_value = resp

            client = GraphClient(token="tok")
            msgs = client.get_messages()
            assert "<" not in msgs[0]["body"]["content"]
            assert "Hello" in msgs[0]["body"]["content"]

    def test_send_reply_creates_then_sends_draft(self):
        from app.ms365.graph_client import GraphClient
        with patch("app.ms365.graph_client._acquire_token", return_value="tok"), \
             patch("app.ms365.graph_client.httpx") as mock_httpx, \
             patch("app.ms365.graph_client.settings") as mock_cfg:
            mock_cfg.ms365_mailbox = "hr@co.com"
            create_resp = MagicMock()
            create_resp.json.return_value = {"id": "draft999"}
            send_resp = MagicMock()
            mock_httpx.post.side_effect = [create_resp, send_resp]

            client = GraphClient(token="tok")
            client.send_reply("msg123", "Here is your answer.")

            assert mock_httpx.post.call_count == 2
            first_url = mock_httpx.post.call_args_list[0][0][0]
            assert "msg123/createReply" in first_url
            second_url = mock_httpx.post.call_args_list[1][0][0]
            assert "draft999/send" in second_url

    def test_mark_as_read_patches_message(self):
        from app.ms365.graph_client import GraphClient
        with patch("app.ms365.graph_client._acquire_token", return_value="tok"), \
             patch("app.ms365.graph_client.httpx") as mock_httpx, \
             patch("app.ms365.graph_client.settings") as mock_cfg:
            mock_cfg.ms365_mailbox = "hr@co.com"
            mock_httpx.patch.return_value = MagicMock()

            client = GraphClient(token="tok")
            client.mark_as_read("msg123")

            call_args = mock_httpx.patch.call_args
            assert "msg123" in call_args[0][0]
            assert call_args[1]["json"] == {"isRead": True}


# ── GraphInbox unit tests ────────────────────────────────────────────────────

class TestGraphInbox:
    def test_get_unread_returns_emails(self):
        from app.ms365.graph_inbox import GraphInbox
        client = _mock_graph_client([
            _make_graph_message("id1", "Subject 1", "a@co.com"),
            _make_graph_message("id2", "Subject 2", "b@co.com"),
        ])
        inbox = GraphInbox(client=client)
        emails = inbox.get_unread()
        assert len(emails) == 2
        assert emails[0].id == "id1"
        assert emails[0].sender == "a@co.com"
        assert emails[1].subject == "Subject 2"
        client.get_messages.assert_called_once_with(unread_only=True)

    def test_get_all_passes_unread_false(self):
        from app.ms365.graph_inbox import GraphInbox
        client = _mock_graph_client()
        inbox = GraphInbox(client=client)
        inbox.get_all()
        client.get_messages.assert_called_once_with(unread_only=False)

    def test_email_fields_mapped_correctly(self):
        from app.ms365.graph_inbox import GraphInbox
        client = _mock_graph_client([
            _make_graph_message("gid1", "PTO question", "emp@company.com", "How many days?", received="2026-05-08T10:00:00Z")
        ])
        inbox = GraphInbox(client=client)
        email = inbox.get_unread()[0]
        assert email.message_id == "gid1"
        assert email.subject == "PTO question"
        assert email.sender == "emp@company.com"
        assert email.body == "How many days?"
        assert email.status == "unread"

    def test_mark_replied_sends_then_marks_read(self):
        from app.ms365.graph_inbox import GraphInbox
        client = _mock_graph_client()
        inbox = GraphInbox(client=client)
        inbox.mark_replied("gid1", "You get 15 days.")
        client.send_reply.assert_called_once_with("gid1", "You get 15 days.")
        client.mark_as_read.assert_called_once_with("gid1")

    def test_mark_failed_marks_read_without_reply(self):
        from app.ms365.graph_inbox import GraphInbox
        client = _mock_graph_client()
        inbox = GraphInbox(client=client)
        inbox.mark_failed("gid1")
        client.mark_as_read.assert_called_once_with("gid1")
        client.send_reply.assert_not_called()

    def test_count_unread(self):
        from app.ms365.graph_inbox import GraphInbox
        client = _mock_graph_client([_make_graph_message(), _make_graph_message("id2")])
        inbox = GraphInbox(client=client)
        assert inbox.count(status="unread") == 2
        client.get_messages.assert_called_with(unread_only=True)

    def test_count_all(self):
        from app.ms365.graph_inbox import GraphInbox
        client = _mock_graph_client([_make_graph_message()])
        inbox = GraphInbox(client=client)
        assert inbox.count() == 1
        client.get_messages.assert_called_with(unread_only=False)


# ── OAuth stub tests ─────────────────────────────────────────────────────────

@pytest.fixture
def ms365_client():
    app.dependency_overrides[require_auth] = lambda: "test-user"
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestOAuthStub:
    def test_status_unconfigured(self, ms365_client):
        with patch("app.ms365.oauth.settings") as mock_cfg:
            mock_cfg.ms365_client_id = ""
            mock_cfg.ms365_tenant_id = ""
            mock_cfg.ms365_mailbox = ""
            mock_cfg.ms365_use_real_inbox = False
            r = ms365_client.get("/ms365/status")
        assert r.status_code == 200
        assert r.json()["configured"] is False

    def test_status_configured(self, ms365_client):
        with patch("app.ms365.oauth.settings") as mock_cfg:
            mock_cfg.ms365_client_id = "cid123"
            mock_cfg.ms365_tenant_id = "tid456"
            mock_cfg.ms365_mailbox = "hr@co.com"
            mock_cfg.ms365_use_real_inbox = True
            r = ms365_client.get("/ms365/status")
        assert r.status_code == 200
        data = r.json()
        assert data["configured"] is True
        assert data["mailbox"] == "hr@co.com"

    def test_authorize_missing_config_returns_503(self, ms365_client):
        with patch("app.ms365.oauth.settings") as mock_cfg:
            mock_cfg.ms365_client_id = ""
            mock_cfg.ms365_tenant_id = ""
            r = ms365_client.get("/ms365/authorize", follow_redirects=False)
        assert r.status_code == 503

    def test_authorize_redirects_to_microsoft(self, ms365_client):
        with patch("app.ms365.oauth.settings") as mock_cfg:
            mock_cfg.ms365_client_id = "cid"
            mock_cfg.ms365_tenant_id = "tid"
            mock_cfg.ms365_redirect_uri = "http://localhost:8000/ms365/callback"
            r = ms365_client.get("/ms365/authorize", follow_redirects=False)
        assert r.status_code == 307
        assert "login.microsoftonline.com" in r.headers["location"]
        assert "cid" in r.headers["location"]

    def test_callback_with_code(self, ms365_client):
        r = ms365_client.get("/ms365/callback?code=AUTHCODE123")
        assert r.status_code == 200
        assert "Authorization code received" in r.json()["message"]

    def test_callback_with_error(self, ms365_client):
        r = ms365_client.get("/ms365/callback?error=access_denied&error_description=User+denied")
        assert r.status_code == 400
        assert r.json()["error"] == "access_denied"

    def test_callback_no_code_no_error(self, ms365_client):
        r = ms365_client.get("/ms365/callback")
        assert r.status_code == 400


# ── Dependency injection tests ────────────────────────────────────────────────

class TestInboxDependency:
    def test_returns_mock_inbox_when_not_configured(self):
        with patch("app.dependencies.settings") as mock_cfg:
            mock_cfg.gmail_use_inbox = False
            mock_cfg.ms365_use_real_inbox = False
            mock_cfg.db_path = ":memory:"
            from app.dependencies import get_inbox
            from app.email_ingestion.mock_inbox import MockInbox
            inbox = get_inbox()
            assert isinstance(inbox, MockInbox)

    def test_returns_graph_inbox_when_configured(self):
        with patch("app.dependencies.settings") as mock_cfg, \
             patch("app.ms365.graph_inbox.GraphClient") as mock_client_cls:
            mock_cfg.gmail_use_inbox = False
            mock_cfg.ms365_use_real_inbox = True
            mock_client_cls.return_value = MagicMock()
            from app.dependencies import get_inbox
            from app.ms365.graph_inbox import GraphInbox
            inbox = get_inbox()
            assert isinstance(inbox, GraphInbox)


# ── Integration tests (skip without M365 credentials) ────────────────────────

@pytest.fixture(scope="session")
def m365_credentials():
    from app.config import settings
    if not all([settings.ms365_tenant_id, settings.ms365_client_id, settings.ms365_client_secret, settings.ms365_mailbox]):
        pytest.skip("MS365_TENANT_ID, MS365_CLIENT_ID, MS365_CLIENT_SECRET, MS365_MAILBOX not set")
    return settings


@pytest.mark.integration
def test_graph_client_can_acquire_token(m365_credentials):
    from app.ms365.graph_client import _acquire_token
    token = _acquire_token()
    assert token and len(token) > 20


@pytest.mark.integration
def test_graph_inbox_can_list_messages(m365_credentials):
    from app.ms365.graph_inbox import GraphInbox
    inbox = GraphInbox()
    messages = inbox.get_all()
    assert isinstance(messages, list)
