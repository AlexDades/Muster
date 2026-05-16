from __future__ import annotations
import re
import anthropic
from app.email_ingestion.mock_inbox import MockInbox
from app.email_ingestion.parser import extract_question
from app.indexer.store import PolicyStore
from app.retrieval.pipeline import answer_question
from app.delivery.dispatcher import dispatch
from app.config import settings
from app.delivery.draft_store import DraftStore

_ACK_RE = re.compile(
    r'^\s*(thank(s| you( so much| very much)?)?'
    r'|much appreciated'
    r'|cheers'
    r'|got it'
    r'|perfect'
    r'|great'
    r'|ok(ay)?'
    r')[!\s.,]*$',
    re.IGNORECASE,
)


def _is_acknowledgment(body: str) -> bool:
    stripped = body.strip()
    return len(stripped) < 120 and "?" not in stripped and bool(_ACK_RE.match(stripped))


def process_inbox(
    inbox: MockInbox,
    store: PolicyStore,
    client: anthropic.Anthropic,
    human_review_mode: bool = False,
    draft_store: DraftStore | None = None,
) -> list[dict]:
    """Process all unread emails. Returns one result dict per email."""
    allowed = {s.strip().lower() for s in settings.allowed_senders.split(",") if s.strip()}
    emails = inbox.get_unread()
    results = []

    for email in emails:
        if allowed and email.sender.lower() not in allowed:
            inbox.mark_failed(email.id)  # mark read, no reply
            continue

        if _is_acknowledgment(email.body):
            inbox.mark_failed(email.id)  # mark read, no reply
            continue

        question = extract_question(email.body)
        try:
            result = answer_question(question, store, client=client)
            delivery = dispatch(
                email=email,
                result=result,
                inbox=inbox,
                human_review_mode=human_review_mode,
                draft_store=draft_store,
            )
            results.append({
                "email_id": email.id,
                "sender": email.sender,
                "subject": email.subject,
                "question": question,
                "answer": result["answer"],
                "sources": result["sources"],
                "validation": result["validation"],
                **delivery,
            })
        except Exception as exc:
            inbox.mark_failed(email.id)
            results.append({
                "email_id": email.id,
                "sender": email.sender,
                "subject": email.subject,
                "status": "failed",
                "error": str(exc),
            })

    return results
