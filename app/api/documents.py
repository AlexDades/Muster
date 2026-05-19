from __future__ import annotations
import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.indexer.store import PolicyStore
from app.indexer.pipeline import index_document, remove_document
from app.config import settings
from app import dependencies as deps
from app.versioning.store import VersionStore
from app.email_utils import send_email

router = APIRouter(prefix="/documents", tags=["documents"])
_limiter = Limiter(key_func=get_remote_address)

ALLOWED_EXTENSIONS = {".pdf", ".docx"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


class NotifyRequest(BaseModel):
    recipients: list[str]
    message: str = ""


@router.get("")
def list_documents(store: PolicyStore = Depends(deps.get_policy_store)) -> list[dict]:
    docs = store.list_documents()
    version_store = VersionStore(db_path=settings.db_path)
    all_versions = version_store.get_all_latest()
    for doc in docs:
        doc["version"] = all_versions.get(doc["id"], 1)
    return docs


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
    version_store = VersionStore(db_path=settings.db_path)
    version = version_store.record_upload(
        doc_id=result["doc_id"],
        filename=file.filename,
        chunks=result.get("chunks", 0),
    )
    return {"message": "Document indexed successfully.", "version": version, **result}


@router.delete("/{doc_id}", status_code=204)
def delete_document(
    doc_id: str,
    store: PolicyStore = Depends(deps.get_policy_store),
) -> None:
    remove_document(doc_id, store=store)
    VersionStore(db_path=settings.db_path).remove_by_doc_id(doc_id)


@router.get("/{doc_id}/versions")
def get_versions(doc_id: str) -> list[dict]:
    return VersionStore(db_path=settings.db_path).get_versions(doc_id)


@router.post("/{doc_id}/notify")
def notify_policy_update(
    doc_id: str,
    body: NotifyRequest,
    store: PolicyStore = Depends(deps.get_policy_store),
) -> dict:
    docs = store.list_documents()
    doc = next((d for d in docs if d["id"] == doc_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    filename = doc.get("filename") or doc.get("name", doc_id)
    version_store = VersionStore(db_path=settings.db_path)
    version = version_store.get_latest_version(doc_id) or 1

    subject = f"[Policy Update] {filename} — Version {version}"
    custom_message = body.message or f"Our HR team has updated the {filename} policy."
    file_link = f"{settings.public_base_url}/files/{filename}"
    email_body = (
        f"Hello,\n\n"
        f"{custom_message}\n\n"
        f"You can view the updated document here:\n{file_link}\n\n"
        f"If you have any questions about this policy, feel free to ask Veridas or reach out via Muster.\n\n"
        f"— The HR Team | Muster Policy Assistant"
    )

    sent: list[str] = []
    failed: list[str] = []
    for recipient in body.recipients:
        try:
            send_email(to=recipient, subject=subject, body=email_body)
            sent.append(recipient)
        except Exception:
            failed.append(recipient)

    return {"sent": len(sent), "failed": len(failed), "sent_to": sent, "failed_to": failed}
