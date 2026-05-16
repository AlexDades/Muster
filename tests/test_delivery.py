"""
Unit tests run without an API key.
Integration tests require ANTHROPIC_API_KEY in .env — run with:
    pytest tests/test_delivery.py -m integration
"""
import uuid
import pytest
from unittest.mock import MagicMock

from app.email_ingestion.models import Email
from app.delivery.draft_store import DraftStore, Draft
from app.delivery.dispatcher import dispatch, send_approved_draft, format_reply
from app.email_ingestion.poller import process_inbox


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_email(inbox, body="How many vacation days do I get?") -> Email:
    email = Email(
        sender="employee@company.com",
        subject="HR Question",
        body=body,
        message_id=str(uuid.uuid4()),
    )
    email_id = inbox.add_email(email)
    email.id = inbox.get_unread()[0].id
    return email


def _make_pipeline_result(answer="You get 15 days [Source: pto.pdf].") -> dict:
    return {
        "question": "How many vacation days do I get?",
        "answer": answer,
        "sources": ["pto_vacation_policy.pdf"],
        "validation": {"valid": True, "confidence": 0.95, "issues": [], "reasoning": "ok"},
        "chunks_used": 2,
    }


def _mock_pipeline_client(answer="You get 15 days [Source: pto.pdf].") -> MagicMock:
    val_json = '{"valid": true, "confidence": 0.95, "issues": [], "reasoning": "ok"}'

    def side_effect(**kwargs):
        msg = kwargs["messages"][0]["content"]
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text=answer if "Employee question:" in msg else val_json)]
        return mock_resp

    client = MagicMock()
    client.messages.create.side_effect = side_effect
    return client


# ── DraftStore unit tests ─────────────────────────────────────────────────────

def test_draft_store_starts_empty(draft_store):
    assert draft_store.count() == 0


def test_draft_store_save_draft(inbox, draft_store):
    email = _make_email(inbox)
    result = _make_pipeline_result()
    draft_id = draft_store.save_draft(email, result)
    assert isinstance(draft_id, int)
    assert draft_store.count() == 1


def test_draft_store_get_pending(inbox, draft_store):
    email = _make_email(inbox)
    draft_store.save_draft(email, _make_pipeline_result())
    pending = draft_store.get_pending()
    assert len(pending) == 1
    assert pending[0].status == "pending"


def test_draft_store_preserves_fields(inbox, draft_store):
    email = _make_email(inbox)
    result = _make_pipeline_result()
    draft_store.save_draft(email, result)
    draft = draft_store.get_pending()[0]
    assert draft.sender == email.sender
    assert draft.subject == email.subject
    assert draft.question == result["question"]
    assert draft.proposed_answer == result["answer"]
    assert draft.sources == result["sources"]
    assert draft.validation == result["validation"]


def test_draft_store_approve_sets_status(inbox, draft_store):
    email = _make_email(inbox)
    draft_id = draft_store.save_draft(email, _make_pipeline_result())
    draft_store.approve(draft_id)
    draft = draft_store.get_all()[0]
    assert draft.status == "approved"
    assert draft.final_answer == draft.proposed_answer
    assert draft.reviewed_at is not None


def test_draft_store_approve_with_edit_sets_edited_status(inbox, draft_store):
    email = _make_email(inbox)
    draft_id = draft_store.save_draft(email, _make_pipeline_result())
    draft_store.approve(draft_id, final_answer="HR-edited answer.")
    draft = draft_store.get_all()[0]
    assert draft.status == "edited"
    assert draft.final_answer == "HR-edited answer."


def test_draft_store_reject_sets_status(inbox, draft_store):
    email = _make_email(inbox)
    draft_id = draft_store.save_draft(email, _make_pipeline_result())
    draft_store.reject(draft_id, note="Answer was incorrect.")
    draft = draft_store.get_all()[0]
    assert draft.status == "rejected"
    assert draft.reviewer_note == "Answer was incorrect."
    assert draft.reviewed_at is not None


def test_draft_store_get_pending_excludes_reviewed(inbox, draft_store):
    email1 = _make_email(inbox, body="Question 1 about vacation")
    email2 = _make_email(inbox, body="Question 2 about expenses")
    id1 = draft_store.save_draft(email1, _make_pipeline_result())
    draft_store.save_draft(email2, _make_pipeline_result())
    draft_store.approve(id1)
    assert draft_store.count(status="pending") == 1
    assert draft_store.count(status="approved") == 1


def test_draft_store_count_by_status(inbox, draft_store):
    for i in range(3):
        e = _make_email(inbox, body=f"Question {i}")
        draft_store.save_draft(e, _make_pipeline_result())
    ids = [d.id for d in draft_store.get_all()]
    draft_store.approve(ids[0])
    draft_store.reject(ids[1])
    assert draft_store.count(status="pending") == 1
    assert draft_store.count(status="approved") == 1
    assert draft_store.count(status="rejected") == 1


# ── Dispatcher unit tests ─────────────────────────────────────────────────────

def test_dispatch_auto_send_marks_inbox_replied(inbox, draft_store):
    email = _make_email(inbox)
    result = _make_pipeline_result()
    delivery = dispatch(email, result, inbox, human_review_mode=False)
    assert delivery["status"] == "sent"
    assert inbox.count(status="replied") == 1


def test_dispatch_auto_send_does_not_create_draft(inbox, draft_store):
    email = _make_email(inbox)
    dispatch(email, _make_pipeline_result(), inbox, human_review_mode=False)
    assert draft_store.count() == 0


def test_dispatch_review_mode_creates_draft(inbox, draft_store):
    email = _make_email(inbox)
    result = _make_pipeline_result()
    delivery = dispatch(email, result, inbox, human_review_mode=True, draft_store=draft_store)
    assert delivery["status"] == "pending_review"
    assert "draft_id" in delivery
    assert draft_store.count(status="pending") == 1


def test_dispatch_review_mode_does_not_reply(inbox, draft_store):
    email = _make_email(inbox)
    dispatch(email, _make_pipeline_result(), inbox, human_review_mode=True, draft_store=draft_store)
    assert inbox.count(status="unread") == 1
    assert inbox.count(status="replied") == 0


def test_dispatch_review_mode_without_draft_store_raises(inbox):
    email = _make_email(inbox)
    with pytest.raises(ValueError, match="draft_store is required"):
        dispatch(email, _make_pipeline_result(), inbox, human_review_mode=True, draft_store=None)


def test_send_approved_draft_marks_inbox_replied(inbox, draft_store):
    email = _make_email(inbox)
    draft_id = draft_store.save_draft(email, _make_pipeline_result())
    send_approved_draft(draft_id, draft_store, inbox)
    assert inbox.count(status="replied") == 1


def test_send_approved_draft_with_edit_uses_edited_answer(inbox, draft_store):
    email = _make_email(inbox)
    draft_id = draft_store.save_draft(email, _make_pipeline_result())
    send_approved_draft(draft_id, draft_store, inbox, edited_answer="Corrected by HR.")
    replied = inbox.get_all()[0]
    assert "Corrected by HR." in replied.reply_body
    assert draft_store.get_all()[0].status == "edited"


def test_send_approved_draft_reply_contains_reviewed_footer(inbox, draft_store):
    email = _make_email(inbox)
    draft_id = draft_store.save_draft(email, _make_pipeline_result())
    send_approved_draft(draft_id, draft_store, inbox)
    reply = inbox.get_all()[0].reply_body
    assert "reviewed and approved by HR" in reply


def test_format_reply_auto_contains_muster_footer():
    result = {"answer": "15 days.", "sources": ["pto.pdf"]}
    reply = format_reply(result, reviewed=False)
    assert "Muster HR Assistant" in reply


def test_format_reply_reviewed_contains_hr_footer():
    result = {"answer": "15 days.", "sources": ["pto.pdf"]}
    reply = format_reply(result, reviewed=True)
    assert "reviewed and approved by HR" in reply


# ── Updated poller unit tests ─────────────────────────────────────────────────

def test_poller_auto_mode_marks_replied(inbox, store, draft_store):
    inbox.add_email(Email(
        sender="a@co.com", subject="Q", body="How many vacation days?",
        message_id=str(uuid.uuid4()),
    ))
    client = _mock_pipeline_client()
    results = process_inbox(inbox, store, client, human_review_mode=False)
    assert results[0]["status"] == "sent"
    assert inbox.count(status="replied") == 1


def test_poller_review_mode_creates_draft(inbox, store, draft_store):
    inbox.add_email(Email(
        sender="a@co.com", subject="Q", body="How many vacation days?",
        message_id=str(uuid.uuid4()),
    ))
    client = _mock_pipeline_client()
    results = process_inbox(inbox, store, client, human_review_mode=True, draft_store=draft_store)
    assert results[0]["status"] == "pending_review"
    assert "draft_id" in results[0]
    assert draft_store.count(status="pending") == 1
    assert inbox.count(status="unread") == 1


def test_poller_review_mode_then_approve_marks_replied(inbox, store, draft_store):
    inbox.add_email(Email(
        sender="a@co.com", subject="Q", body="How many vacation days?",
        message_id=str(uuid.uuid4()),
    ))
    client = _mock_pipeline_client()
    results = process_inbox(inbox, store, client, human_review_mode=True, draft_store=draft_store)
    draft_id = results[0]["draft_id"]
    send_approved_draft(draft_id, draft_store, inbox)
    assert inbox.count(status="replied") == 1
    assert draft_store.count(status="approved") == 1


def test_poller_review_mode_then_edit_uses_edited_text(inbox, store, draft_store):
    inbox.add_email(Email(
        sender="a@co.com", subject="Q", body="How many vacation days?",
        message_id=str(uuid.uuid4()),
    ))
    client = _mock_pipeline_client()
    results = process_inbox(inbox, store, client, human_review_mode=True, draft_store=draft_store)
    draft_id = results[0]["draft_id"]
    send_approved_draft(draft_id, draft_store, inbox, edited_answer="HR says: you get 20 days.")
    reply = inbox.get_all()[0].reply_body
    assert "HR says: you get 20 days." in reply
    assert draft_store.count(status="edited") == 1


def test_poller_review_mode_then_reject(inbox, store, draft_store):
    inbox.add_email(Email(
        sender="a@co.com", subject="Q", body="How many vacation days?",
        message_id=str(uuid.uuid4()),
    ))
    client = _mock_pipeline_client()
    results = process_inbox(inbox, store, client, human_review_mode=True, draft_store=draft_store)
    draft_id = results[0]["draft_id"]
    draft_store.reject(draft_id, note="Answer was wrong.")
    assert draft_store.count(status="rejected") == 1
    assert inbox.count(status="unread") == 1


# ── Integration tests (require ANTHROPIC_API_KEY) ─────────────────────────────

@pytest.mark.integration
def test_auto_send_mode_full_flow(inbox, indexed_store, api_client):
    inbox.add_email(Email(
        sender="employee@co.com", subject="PTO", body="How many vacation days per year?",
        message_id=str(uuid.uuid4()),
    ))
    results = process_inbox(inbox, indexed_store, api_client, human_review_mode=False)
    assert results[0]["status"] == "sent"
    assert "15" in inbox.get_all()[0].reply_body


@pytest.mark.integration
def test_review_mode_approve_full_flow(inbox, draft_store, indexed_store, api_client):
    inbox.add_email(Email(
        sender="employee@co.com", subject="Remote work", body="How many days can I work from home?",
        message_id=str(uuid.uuid4()),
    ))
    results = process_inbox(inbox, indexed_store, api_client, human_review_mode=True, draft_store=draft_store)
    assert results[0]["status"] == "pending_review"
    assert inbox.count(status="replied") == 0

    draft_id = results[0]["draft_id"]
    send_approved_draft(draft_id, draft_store, inbox)
    assert inbox.count(status="replied") == 1
    assert "reviewed and approved by HR" in inbox.get_all()[0].reply_body


@pytest.mark.integration
def test_review_mode_edit_full_flow(inbox, draft_store, indexed_store, api_client):
    inbox.add_email(Email(
        sender="employee@co.com", subject="PTO", body="How many vacation days per year?",
        message_id=str(uuid.uuid4()),
    ))
    results = process_inbox(inbox, indexed_store, api_client, human_review_mode=True, draft_store=draft_store)
    draft_id = results[0]["draft_id"]
    send_approved_draft(draft_id, draft_store, inbox, edited_answer="Per our policy, you get 15 days of PTO. — HR Team")
    reply = inbox.get_all()[0].reply_body
    assert "HR Team" in reply
    assert draft_store.get_all()[0].status == "edited"


@pytest.mark.integration
def test_validation_pass_rate(inbox, draft_store, indexed_store, api_client):
    questions = [
        "How many sick days do I get?",
        "What is the meal allowance for domestic travel?",
        "How long is parental leave for the primary caregiver?",
    ]
    for q in questions:
        inbox.add_email(Email(
            sender="emp@co.com", subject="Q", body=q,
            message_id=str(uuid.uuid4()),
        ))
    results = process_inbox(inbox, indexed_store, api_client, human_review_mode=False)
    passed = sum(1 for r in results if r.get("validation", {}).get("valid"))
    assert passed >= 2
