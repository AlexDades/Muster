from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from app.audit.audit_log import AuditStore
from app import dependencies as deps

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
def list_audit_entries(
    status: Optional[str] = Query(None),
    sender: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    audit_store: AuditStore = Depends(deps.get_audit_store),
) -> dict:
    entries = audit_store.get_all(status=status, sender=sender, limit=limit, offset=offset)
    return {"total": audit_store.count(status=status, sender=sender), "entries": entries}


@router.get("/{audit_id}")
def get_audit_entry(
    audit_id: int,
    audit_store: AuditStore = Depends(deps.get_audit_store),
) -> dict:
    entry = audit_store.get_by_id(audit_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Audit entry not found.")
    return entry
