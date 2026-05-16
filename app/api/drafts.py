from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.delivery.draft_store import DraftStore, Draft
from app.delivery.dispatcher import send_approved_draft
from app.email_ingestion.mock_inbox import MockInbox
from app.audit.audit_log import AuditStore
from app import dependencies as deps

router = APIRouter(prefix="/drafts", tags=["drafts"])


class ApproveRequest(BaseModel):
    edited_answer: Optional[str] = None
    reviewer: Optional[str] = None


class RejectRequest(BaseModel):
    note: Optional[str] = ""
    reviewer: Optional[str] = None


@router.get("")
def list_drafts(
    draft_store: DraftStore = Depends(deps.get_draft_store),
) -> list[dict]:
    return [_draft_to_dict(d) for d in draft_store.get_pending()]


@router.get("/{draft_id}")
def get_draft(
    draft_id: int,
    draft_store: DraftStore = Depends(deps.get_draft_store),
) -> dict:
    drafts = [d for d in draft_store.get_all() if d.id == draft_id]
    if not drafts:
        raise HTTPException(status_code=404, detail="Draft not found.")
    return _draft_to_dict(drafts[0])


@router.post("/{draft_id}/approve", status_code=200)
def approve_draft(
    draft_id: int,
    body: ApproveRequest = ApproveRequest(),
    draft_store: DraftStore = Depends(deps.get_draft_store),
    inbox: MockInbox = Depends(deps.get_mock_inbox),
    audit_store: AuditStore = Depends(deps.get_audit_store),
) -> dict:
    drafts = [d for d in draft_store.get_all() if d.id == draft_id]
    if not drafts:
        raise HTTPException(status_code=404, detail="Draft not found.")
    if drafts[0].status != "pending":
        raise HTTPException(status_code=409, detail=f"Draft is already {drafts[0].status}.")

    send_approved_draft(draft_id, draft_store, inbox, edited_answer=body.edited_answer)

    draft = [d for d in draft_store.get_all() if d.id == draft_id][0]
    entries = audit_store.get_all()
    matching = [e for e in entries if e.get("draft_id") == draft_id]
    if matching:
        audit_store.update(matching[0]["id"], {
            "status": draft.status,
            "final_answer": draft.final_answer,
            "reviewer": body.reviewer,
        })

    return {"message": "Draft approved and reply sent.", "status": draft.status}


@router.post("/{draft_id}/reject", status_code=200)
def reject_draft(
    draft_id: int,
    body: RejectRequest = RejectRequest(),
    draft_store: DraftStore = Depends(deps.get_draft_store),
    audit_store: AuditStore = Depends(deps.get_audit_store),
) -> dict:
    drafts = [d for d in draft_store.get_all() if d.id == draft_id]
    if not drafts:
        raise HTTPException(status_code=404, detail="Draft not found.")
    if drafts[0].status != "pending":
        raise HTTPException(status_code=409, detail=f"Draft is already {drafts[0].status}.")

    draft_store.reject(draft_id, note=body.note or "")

    entries = audit_store.get_all()
    matching = [e for e in entries if e.get("draft_id") == draft_id]
    if matching:
        audit_store.update(matching[0]["id"], {
            "status": "rejected",
            "reviewer": body.reviewer,
        })

    return {"message": "Draft rejected.", "status": "rejected"}


def _draft_to_dict(draft: Draft) -> dict:
    return {
        "id": draft.id,
        "email_id": draft.email_id,
        "sender": draft.sender,
        "subject": draft.subject,
        "question": draft.question,
        "proposed_answer": draft.proposed_answer,
        "sources": draft.sources,
        "validation": draft.validation,
        "status": draft.status,
        "final_answer": draft.final_answer,
        "reviewer_note": draft.reviewer_note,
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
        "reviewed_at": draft.reviewed_at.isoformat() if draft.reviewed_at else None,
    }
