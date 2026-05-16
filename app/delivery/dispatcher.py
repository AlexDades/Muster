from __future__ import annotations
import re
from app.email_ingestion.mock_inbox import MockInbox
from app.email_ingestion.models import Email
from app.delivery.draft_store import DraftStore
from app.config import settings


def _first_name(sender: str) -> str:
    local = sender.split("@")[0]
    parts = re.split(r'[._\-+]', local)
    first = parts[0]
    # Unseparated compound username (e.g. "brigitabaciu") — can't reliably extract a first name
    if len(parts) == 1 and len(first) > 12:
        return "there"
    return first.capitalize()


def not_in_scope_reply(sender: str) -> str:
    name = _first_name(sender) if sender else "there"
    return (
        f"Hello {name},\n\n"
        f"Thanks for reaching out. This inbox is dedicated to answering HR policy questions — "
        f"things like leave entitlements, expenses, working hours, benefits, and similar topics.\n\n"
        f"For anything outside that scope, please contact the HR team directly.\n\n"
        f"---\n"
        f"This reply was generated automatically by Muster HR Assistant."
    )


def format_reply(result: dict, sender: str = "", reviewed: bool = False) -> str:
    name = _first_name(sender) if sender else "there"
    base = settings.public_base_url.rstrip("/")
    if result["sources"]:
        source_lines = "\n".join(f"  - {s}: {base}/files/{s}" for s in result["sources"])
    else:
        source_lines = "  N/A"
    footer = "reviewed and approved by HR" if reviewed else "generated automatically by Muster HR Assistant"
    return (
        f"Hello {name},\n\n"
        f"I've had a look through our policy documents and here's what I found.\n\n"
        f"{result['answer']}\n\n"
        f"If you have any further questions, feel free to reach out.\n\n"
        f"---\n"
        f"Sources:\n{source_lines}\n"
        f"This reply was {footer}."
    )


def dispatch(
    email: Email,
    result: dict,
    inbox: MockInbox,
    human_review_mode: bool = False,
    draft_store: DraftStore | None = None,
) -> dict:
    if human_review_mode:
        if draft_store is None:
            raise ValueError("draft_store is required when human_review_mode=True")
        draft_id = draft_store.save_draft(email, result)
        return {"status": "pending_review", "draft_id": draft_id}

    reply = format_reply(result, sender=email.sender)
    inbox.mark_replied(email.id, reply)
    return {"status": "sent"}


def send_approved_draft(
    draft_id: int,
    draft_store: DraftStore,
    inbox: MockInbox,
    edited_answer: str | None = None,
) -> None:
    draft_store.approve(draft_id, final_answer=edited_answer)
    draft = next(d for d in draft_store.get_all() if d.id == draft_id)
    final = draft.final_answer or draft.proposed_answer
    result = {"answer": final, "sources": draft.sources}
    reply = format_reply(result, sender=draft.sender, reviewed=True)
    inbox.mark_replied(draft.email_id, reply)
