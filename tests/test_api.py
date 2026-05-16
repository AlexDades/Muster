"""API tests — no API key required (pipeline is mocked)."""
import io
import uuid
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from pathlib import Path

from app.main import app
from app.indexer.store import PolicyStore
from app.delivery.draft_store import DraftStore
from app.audit.audit_log import AuditStore
from app.email_ingestion.mock_inbox import MockInbox
from app.email_ingestion.models import Email
from app.dependencies import RuntimeSettings
from app.auth.jwt_auth import require_auth
import app.dependencies as deps


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def api(tmp_path, store):
    draft_store = DraftStore(db_path=str(tmp_path / "drafts.db"))
    audit_store = AuditStore(db_path=str(tmp_path / "audit.db"))
    inbox = MockInbox(db_path=str(tmp_path / "inbox.db"))
    rs = RuntimeSettings()

    val_json = '{"valid": true, "confidence": 0.95, "issues": [], "reasoning": "ok"}'

    def mock_answer(**kwargs):
        msg = kwargs["messages"][0]["content"]
        resp = MagicMock()
        resp.content = [MagicMock(
            text="15 days [Source: pto.pdf]." if "Employee question:" in msg else val_json
        )]
        return resp

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = mock_answer

    app.dependency_overrides[deps.get_policy_store] = lambda: store
    app.dependency_overrides[deps.get_draft_store] = lambda: draft_store
    app.dependency_overrides[deps.get_audit_store] = lambda: audit_store
    app.dependency_overrides[deps.get_mock_inbox] = lambda: inbox
    app.dependency_overrides[deps.get_inbox] = lambda: inbox
    app.dependency_overrides[deps.get_anthropic_client] = lambda: mock_client
    app.dependency_overrides[deps.get_runtime_settings] = lambda: rs
    app.dependency_overrides[require_auth] = lambda: "test-user"

    with TestClient(app) as client:
        yield {
            "client": client,
            "store": store,
            "draft_store": draft_store,
            "audit_store": audit_store,
            "inbox": inbox,
            "rs": rs,
        }

    app.dependency_overrides.clear()


SAMPLE_DOCS_DIR = Path(__file__).parent.parent / "sample_docs"


# ── Health ────────────────────────────────────────────────────────────────────

def test_health(api):
    r = api["client"].get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── Documents ─────────────────────────────────────────────────────────────────

def test_list_documents_empty(api):
    r = api["client"].get("/documents")
    assert r.status_code == 200
    assert r.json() == []


def test_upload_pdf_document(api, tmp_path):
    pdf_path = SAMPLE_DOCS_DIR / "pto_vacation_policy.pdf"
    with open(pdf_path, "rb") as f:
        r = api["client"].post("/documents", files={"file": ("pto_vacation_policy.pdf", f, "application/pdf")})
    assert r.status_code == 201
    data = r.json()
    assert data["filename"] == "pto_vacation_policy.pdf"
    assert data["chunks"] > 0


def test_upload_docx_document(api):
    docx_path = SAMPLE_DOCS_DIR / "expense_reimbursement.docx"
    with open(docx_path, "rb") as f:
        r = api["client"].post("/documents", files={"file": ("expense_reimbursement.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    assert r.status_code == 201
    assert r.json()["chunks"] > 0


def test_upload_unsupported_file_type_returns_400(api):
    r = api["client"].post(
        "/documents",
        files={"file": ("notes.txt", io.BytesIO(b"some text"), "text/plain")},
    )
    assert r.status_code == 400


def test_list_documents_after_upload(api):
    pdf_path = SAMPLE_DOCS_DIR / "pto_vacation_policy.pdf"
    with open(pdf_path, "rb") as f:
        api["client"].post("/documents", files={"file": ("pto_vacation_policy.pdf", f, "application/pdf")})
    r = api["client"].get("/documents")
    assert r.status_code == 200
    assert any(d["filename"] == "pto_vacation_policy.pdf" for d in r.json())


def test_delete_document(api):
    pdf_path = SAMPLE_DOCS_DIR / "pto_vacation_policy.pdf"
    with open(pdf_path, "rb") as f:
        api["client"].post("/documents", files={"file": ("pto_vacation_policy.pdf", f, "application/pdf")})
    r = api["client"].delete("/documents/pto_vacation_policy")
    assert r.status_code == 204
    docs = api["client"].get("/documents").json()
    assert not any(d["doc_id"] == "pto_vacation_policy" for d in docs)


# ── Settings ──────────────────────────────────────────────────────────────────

def test_get_settings_defaults(api):
    r = api["client"].get("/settings")
    assert r.status_code == 200
    data = r.json()
    assert data["human_review_mode"] is False
    assert data["n_results"] == 5


def test_patch_settings_human_review_mode(api):
    r = api["client"].patch("/settings", json={"human_review_mode": True})
    assert r.status_code == 200
    assert r.json()["human_review_mode"] is True


def test_patch_settings_n_results(api):
    r = api["client"].patch("/settings", json={"n_results": 8})
    assert r.status_code == 200
    assert r.json()["n_results"] == 8


def test_patch_settings_n_results_clamped(api):
    r = api["client"].patch("/settings", json={"n_results": 999})
    assert r.status_code == 200
    assert r.json()["n_results"] == 20


def test_patch_settings_partial_update(api):
    api["client"].patch("/settings", json={"n_results": 7})
    r = api["client"].patch("/settings", json={"human_review_mode": True})
    data = r.json()
    assert data["n_results"] == 7
    assert data["human_review_mode"] is True


# ── Inbox ─────────────────────────────────────────────────────────────────────

def _seed_inbox(inbox: MockInbox, n: int = 1) -> None:
    for i in range(n):
        inbox.add_email(Email(
            sender=f"user{i}@company.com",
            subject="HR question",
            body="How many vacation days do I get?",
            message_id=str(uuid.uuid4()),
        ))


def test_process_inbox_auto_mode(api):
    _seed_inbox(api["inbox"], n=2)
    r = api["client"].post("/inbox/process")
    assert r.status_code == 200
    data = r.json()
    assert data["processed"] == 2
    assert all(res["status"] == "sent" for res in data["results"])


def test_process_inbox_creates_audit_entries(api):
    _seed_inbox(api["inbox"])
    api["client"].post("/inbox/process")
    r = api["client"].get("/audit")
    assert r.json()["total"] == 1


def test_process_inbox_review_mode_creates_drafts(api):
    api["client"].patch("/settings", json={"human_review_mode": True})
    _seed_inbox(api["inbox"])
    r = api["client"].post("/inbox/process")
    assert r.json()["results"][0]["status"] == "pending_review"
    drafts = api["client"].get("/drafts").json()
    assert len(drafts) == 1


def test_process_empty_inbox(api):
    r = api["client"].post("/inbox/process")
    assert r.status_code == 200
    assert r.json()["processed"] == 0


# ── Drafts ────────────────────────────────────────────────────────────────────

def _create_draft(api) -> int:
    api["client"].patch("/settings", json={"human_review_mode": True})
    _seed_inbox(api["inbox"])
    result = api["client"].post("/inbox/process").json()
    return result["results"][0]["draft_id"]


def test_list_drafts_empty(api):
    r = api["client"].get("/drafts")
    assert r.status_code == 200
    assert r.json() == []


def test_list_drafts_after_processing(api):
    _create_draft(api)
    r = api["client"].get("/drafts")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_get_draft_by_id(api):
    draft_id = _create_draft(api)
    r = api["client"].get(f"/drafts/{draft_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == draft_id
    assert data["status"] == "pending"


def test_get_draft_not_found(api):
    r = api["client"].get("/drafts/99999")
    assert r.status_code == 404


def test_approve_draft(api):
    draft_id = _create_draft(api)
    r = api["client"].post(f"/drafts/{draft_id}/approve")
    assert r.status_code == 200
    assert r.json()["status"] == "approved"
    assert api["inbox"].count(status="replied") == 1


def test_approve_draft_with_edit(api):
    draft_id = _create_draft(api)
    r = api["client"].post(f"/drafts/{draft_id}/approve", json={"edited_answer": "Edited by HR."})
    assert r.status_code == 200
    assert r.json()["status"] == "edited"
    reply = api["inbox"].get_all()[0].reply_body
    assert "Edited by HR." in reply


def test_approve_draft_not_found(api):
    r = api["client"].post("/drafts/99999/approve")
    assert r.status_code == 404


def test_approve_already_approved_draft_returns_409(api):
    draft_id = _create_draft(api)
    api["client"].post(f"/drafts/{draft_id}/approve")
    r = api["client"].post(f"/drafts/{draft_id}/approve")
    assert r.status_code == 409


def test_reject_draft(api):
    draft_id = _create_draft(api)
    r = api["client"].post(f"/drafts/{draft_id}/reject", json={"note": "Incorrect answer."})
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"


def test_reject_draft_not_found(api):
    r = api["client"].post("/drafts/99999/reject")
    assert r.status_code == 404


def test_reject_already_rejected_returns_409(api):
    draft_id = _create_draft(api)
    api["client"].post(f"/drafts/{draft_id}/reject")
    r = api["client"].post(f"/drafts/{draft_id}/reject")
    assert r.status_code == 409


# ── Audit ─────────────────────────────────────────────────────────────────────

def test_audit_empty(api):
    r = api["client"].get("/audit")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["entries"] == []


def test_audit_entry_created_after_process(api):
    _seed_inbox(api["inbox"])
    api["client"].post("/inbox/process")
    r = api["client"].get("/audit")
    assert r.json()["total"] == 1
    entry = r.json()["entries"][0]
    assert entry["sender"] == "user0@company.com"
    assert entry["status"] == "sent"


def test_audit_filter_by_status(api):
    _seed_inbox(api["inbox"], n=2)
    api["client"].post("/inbox/process")
    r = api["client"].get("/audit?status=sent")
    assert r.json()["total"] == 2
    r2 = api["client"].get("/audit?status=failed")
    assert r2.json()["total"] == 0


def test_audit_filter_by_sender(api):
    _seed_inbox(api["inbox"], n=3)
    api["client"].post("/inbox/process")
    r = api["client"].get("/audit?sender=user0@company.com")
    assert r.json()["total"] == 1


def test_audit_get_by_id(api):
    _seed_inbox(api["inbox"])
    api["client"].post("/inbox/process")
    entries = api["client"].get("/audit").json()["entries"]
    audit_id = entries[0]["id"]
    r = api["client"].get(f"/audit/{audit_id}")
    assert r.status_code == 200
    assert r.json()["id"] == audit_id


def test_audit_get_by_id_not_found(api):
    r = api["client"].get("/audit/99999")
    assert r.status_code == 404


def test_audit_pagination(api):
    _seed_inbox(api["inbox"], n=5)
    api["client"].post("/inbox/process")
    r = api["client"].get("/audit?limit=2&offset=0")
    assert len(r.json()["entries"]) == 2
    r2 = api["client"].get("/audit?limit=2&offset=2")
    assert len(r2.json()["entries"]) == 2
