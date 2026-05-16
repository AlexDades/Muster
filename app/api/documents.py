from __future__ import annotations
import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.indexer.store import PolicyStore
from app.indexer.pipeline import index_document, remove_document
from app.config import settings
from app import dependencies as deps

router = APIRouter(prefix="/documents", tags=["documents"])
_limiter = Limiter(key_func=get_remote_address)

ALLOWED_EXTENSIONS = {".pdf", ".docx"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


@router.get("")
def list_documents(store: PolicyStore = Depends(deps.get_policy_store)) -> list[dict]:
    return store.list_documents()


@router.post("", status_code=201)
@_limiter.limit("20/minute")
def upload_document(
    request: Request,
    file: UploadFile = File(...),
    store: PolicyStore = Depends(deps.get_policy_store),
) -> dict:
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}. Use PDF or DOCX.")

    content = file.file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 20 MB limit.")
    file.file.seek(0)

    upload_dir = Path(settings.uploaded_docs_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / file.filename

    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    result = index_document(dest, store=store)
    return {"message": "Document indexed successfully.", **result}


@router.delete("/{doc_id}", status_code=204)
def delete_document(
    doc_id: str,
    store: PolicyStore = Depends(deps.get_policy_store),
) -> None:
    remove_document(doc_id, store=store)
