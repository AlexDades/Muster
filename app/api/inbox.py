from __future__ import annotations
from fastapi import APIRouter, Depends, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.email_ingestion.poller import process_inbox
from app.indexer.store import PolicyStore
from app.delivery.draft_store import DraftStore
from app.audit.audit_log import AuditStore
from app.dependencies import RuntimeSettings
import anthropic
from app import dependencies as deps

router = APIRouter(prefix="/inbox", tags=["inbox"])
_limiter = Limiter(key_func=get_remote_address)


@router.post("/process")
@_limiter.limit("10/minute")
def process(
    request: Request,
    inbox=Depends(deps.get_inbox),
    store: PolicyStore = Depends(deps.get_policy_store),
    draft_store: DraftStore = Depends(deps.get_draft_store),
    audit_store: AuditStore = Depends(deps.get_audit_store),
    client: anthropic.Anthropic = Depends(deps.get_anthropic_client),
    rs: RuntimeSettings = Depends(deps.get_runtime_settings),
) -> dict:
    results = process_inbox(
        inbox=inbox,
        store=store,
        client=client,
        human_review_mode=rs.human_review_mode,
        draft_store=draft_store if rs.human_review_mode else None,
    )

    for r in results:
        audit_store.log({
            "email_id": r.get("email_id"),
            "draft_id": r.get("draft_id"),
            "sender": r.get("sender", ""),
            "subject": r.get("subject", ""),
            "question": r.get("question", ""),
            "answer": r.get("answer"),
            "sources": r.get("sources", []),
            "validation": r.get("validation", {}),
            "status": r.get("status", "failed"),
            "error": r.get("error"),
        })

    return {
        "processed": len(results),
        "results": results,
    }
