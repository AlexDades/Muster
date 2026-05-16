"""
Unit tests run without an API key.
Integration tests require ANTHROPIC_API_KEY in .env — run with:
    pytest tests/test_email.py -m integration
"""
import uuid
import pytest
from datetime import datetime
from unittest.mock import MagicMock

from app.email_ingestion.models import Email
from app.email_ingestion.mock_inbox import MockInbox
from app.email_ingestion.parser import extract_question
from app.email_ingestion.poller import process_inbox
from app.delivery.dispatcher import format_reply as _format_reply


# ── MockInbox unit tests ──────────────────────────────────────────────────────

def test_inbox_starts_empty(inbox):
    assert inbox.count() == 0


def test_inbox_add_email(inbox, sample_email):
    inbox.add_email(sample_email)
    assert inbox.count() == 1


def test_inbox_add_email_returns_id(inbox, sample_email):
    row_id = inbox.add_email(sample_email)
    assert isinstance(row_id, int)
    assert row_id > 0


def test_inbox_get_unread_returns_added_email(inbox, sample_email):
    inbox.add_email(sample_email)
    unread = inbox.get_unread()
    assert len(unread) == 1
    assert unread[0].sender == sample_email.sender
    assert unread[0].subject == sample_email.subject


def test_inbox_get_unread_returns_only_unread(inbox):
    for i in range(3):
        inbox.add_email(Email(
            sender=f"user{i}@co.com", subject="Q", body="body",
            message_id=str(uuid.uuid4()),
        ))
    unread = inbox.get_unread()
    inbox.mark_replied(unread[0].id, "reply text")
    assert inbox.count(status="unread") == 2
    assert inbox.count(status="replied") == 1


def test_inbox_mark_replied_updates_status(inbox, sample_email):
    inbox.add_email(sample_email)
    email = inbox.get_unread()[0]
    inbox.mark_replied(email.id, "Here is your answer.")
    assert inbox.count(status="replied") == 1
    assert inbox.count(status="unread") == 0


def test_inbox_mark_replied_stores_reply_body(inbox, sample_email):
    inbox.add_email(sample_email)
    email = inbox.get_unread()[0]
    inbox.mark_replied(email.id, "Your reply here.")
    replied = inbox.get_all()
    assert replied[0].reply_body == "Your reply here."
    assert replied[0].replied_at is not None


def test_inbox_mark_failed_updates_status(inbox, sample_email):
    inbox.add_email(sample_email)
    email = inbox.get_unread()[0]
    inbox.mark_failed(email.id)
    assert inbox.count(status="failed") == 1
    assert inbox.count(status="unread") == 0


def test_inbox_duplicate_message_id_ignored(inbox, sample_email):
    inbox.add_email(sample_email)
    inbox.add_email(sample_email)  # same message_id
    assert inbox.count() == 1


def test_inbox_count_all(inbox):
    for _ in range(5):
        inbox.add_email(Email(
            sender="a@b.com", subject="s", body="b",
            message_id=str(uuid.uuid4()),
        ))
    assert inbox.count() == 5


def test_inbox_email_preserves_fields(inbox):
    sent = Email(
        sender="alice@company.com",
        subject="PTO question",
        body="How much PTO do I have?",
        message_id="msg-001",
        received_at=datetime(2024, 1, 15, 9, 0, 0),
    )
    inbox.add_email(sent)
    received = inbox.get_unread()[0]
    assert received.sender == "alice@company.com"
    assert received.subject == "PTO question"
    assert received.body == "How much PTO do I have?"
    assert received.status == "unread"


# ── Parser unit tests ─────────────────────────────────────────────────────────

def test_extract_question_plain_body():
    body = "Hi, how many vacation days do I get?\n\nThanks, Alice"
    assert extract_question(body) == body.strip()


def test_extract_question_strips_quoted_lines():
    body = "How many sick days do I have?\n\n> On Mon, HR wrote:\n> Please check the policy."
    result = extract_question(body)
    assert ">" not in result
    assert "sick days" in result


def test_extract_question_strips_reply_separator():
    body = (
        "What is the meal allowance?\n\n"
        "On Mon, 6 May 2024, HR wrote:\n"
        "> Please refer to the expense policy.\n"
    )
    result = extract_question(body)
    assert "meal allowance" in result
    assert "expense policy" not in result


def test_extract_question_strips_original_message_separator():
    body = (
        "Can I book business class?\n\n"
        "-----Original Message-----\n"
        "From: hr@company.com\nSubject: Re: travel\nCheck the travel policy."
    )
    result = extract_question(body)
    assert "business class" in result
    assert "travel policy" not in result


def test_extract_question_returns_stripped_text():
    body = "   How many holidays are there?   "
    assert extract_question(body) == "How many holidays are there?"


def test_extract_question_empty_body():
    assert extract_question("") == ""


# ── Poller unit tests ─────────────────────────────────────────────────────────

def _mock_pipeline_client(answer: str = "You get 15 days PTO [Source: pto.pdf].") -> MagicMock:
    val_json = '{"valid": true, "confidence": 0.95, "issues": [], "reasoning": "ok"}'

    def side_effect(**kwargs):
        msg = kwargs["messages"][0]["content"]
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text=answer if "Employee question:" in msg else val_json)]
        return mock_resp

    client = MagicMock()
    client.messages.create.side_effect = side_effect
    return client


def test_poller_processes_unread_emails(inbox, store, sample_email):
    inbox.add_email(sample_email)
    client = _mock_pipeline_client()
    results = process_inbox(inbox, store, client)
    assert len(results) == 1
    assert results[0]["status"] == "sent"


def test_poller_marks_emails_as_replied(inbox, store, sample_email):
    inbox.add_email(sample_email)
    client = _mock_pipeline_client()
    process_inbox(inbox, store, client)
    assert inbox.count(status="replied") == 1
    assert inbox.count(status="unread") == 0


def test_poller_result_contains_expected_keys(inbox, store, sample_email):
    inbox.add_email(sample_email)
    client = _mock_pipeline_client()
    results = process_inbox(inbox, store, client)
    result = results[0]
    assert "email_id" in result
    assert "sender" in result
    assert "question" in result
    assert "answer" in result
    assert "sources" in result
    assert "validation" in result
    assert "status" in result


def test_poller_stores_reply_in_inbox(inbox, store, sample_email):
    inbox.add_email(sample_email)
    client = _mock_pipeline_client()
    process_inbox(inbox, store, client)
    email = inbox.get_all()[0]
    assert email.reply_body is not None
    assert len(email.reply_body) > 0


def test_poller_skips_already_replied_emails(inbox, store, sample_email):
    inbox.add_email(sample_email)
    email = inbox.get_unread()[0]
    inbox.mark_replied(email.id, "already answered")
    client = _mock_pipeline_client()
    results = process_inbox(inbox, store, client)
    assert results == []


def test_poller_handles_multiple_emails(inbox, store):
    for i in range(3):
        inbox.add_email(Email(
            sender=f"user{i}@co.com",
            subject="question",
            body=f"Question number {i} about vacation policy",
            message_id=str(uuid.uuid4()),
        ))
    client = _mock_pipeline_client()
    results = process_inbox(inbox, store, client)
    assert len(results) == 3
    assert all(r["status"] == "sent" for r in results)
    assert inbox.count(status="unread") == 0


def test_poller_marks_failed_on_exception(inbox, store, sample_email):
    inbox.add_email(sample_email)
    client = MagicMock()
    client.messages.create.side_effect = Exception("API error")
    results = process_inbox(inbox, store, client)
    assert results[0]["status"] == "failed"
    assert "error" in results[0]
    assert inbox.count(status="failed") == 1


def test_format_reply_includes_answer_and_sources():
    result = {
        "answer": "You get 15 days PTO per year.",
        "sources": ["pto_vacation_policy.pdf"],
        "validation": {"valid": True},
    }
    reply = _format_reply(result)
    assert "15 days PTO" in reply
    assert "pto_vacation_policy.pdf" in reply
    assert "Muster" in reply


def test_format_reply_handles_no_sources():
    result = {
        "answer": "I could not find this information.",
        "sources": [],
        "validation": {"valid": False},
    }
    reply = _format_reply(result)
    assert "N/A" in reply


# ── Integration tests (require ANTHROPIC_API_KEY) ─────────────────────────────

@pytest.mark.integration
def test_poller_end_to_end_vacation_question(inbox, indexed_store, api_client):
    inbox.add_email(Email(
        sender="employee@company.com",
        subject="Vacation days",
        body="Hi, how many vacation days am I entitled to per year?",
        message_id=str(uuid.uuid4()),
    ))
    results = process_inbox(inbox, indexed_store, api_client)
    assert results[0]["status"] == "sent"
    assert "15" in results[0]["answer"]


@pytest.mark.integration
def test_poller_end_to_end_reply_stored_in_inbox(inbox, indexed_store, api_client):
    inbox.add_email(Email(
        sender="employee@company.com",
        subject="Remote work",
        body="How many days per week can I work from home?",
        message_id=str(uuid.uuid4()),
    ))
    process_inbox(inbox, indexed_store, api_client)
    email = inbox.get_all()[0]
    assert email.status == "replied"
    assert email.reply_body is not None
    assert "Muster" in email.reply_body


@pytest.mark.integration
def test_poller_end_to_end_strips_quoted_text(inbox, indexed_store, api_client):
    inbox.add_email(Email(
        sender="employee@company.com",
        subject="Re: Expense policy",
        body=(
            "What is the hotel reimbursement limit?\n\n"
            "On Mon, HR wrote:\n"
            "> Please check the expense policy document.\n"
        ),
        message_id=str(uuid.uuid4()),
    ))
    results = process_inbox(inbox, indexed_store, api_client)
    assert results[0]["status"] == "sent"
    assert "150" in results[0]["answer"] or "200" in results[0]["answer"]


@pytest.mark.integration
def test_poller_processes_all_seeded_emails(inbox, indexed_store, api_client):
    from sample_emails.seed_inbox import EMAILS
    import uuid as _uuid
    for sender, subject, body in EMAILS[:3]:
        inbox.add_email(Email(
            sender=sender, subject=subject, body=body,
            message_id=str(_uuid.uuid4()),
        ))
    results = process_inbox(inbox, indexed_store, api_client)
    assert len(results) == 3
    assert all(r["status"] == "sent" for r in results)
