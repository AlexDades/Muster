import uuid
import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def allow_all_senders():
    """Disable the sender allowlist so test emails are never filtered out."""
    from app.email_ingestion import poller
    original = poller.settings.allowed_senders
    poller.settings.allowed_senders = ""
    yield
    poller.settings.allowed_senders = original


@pytest.fixture(autouse=True)
def disable_rate_limits():
    """Disable all slowapi rate limiters for every test so hit counts don't accumulate."""
    from app.api import inbox, documents
    from app.api.auth_api import _limiter as auth_limiter
    from app.main import limiter as main_limiter
    for lim in [inbox._limiter, documents._limiter, auth_limiter, main_limiter]:
        lim.enabled = False
    yield
    for lim in [inbox._limiter, documents._limiter, auth_limiter, main_limiter]:
        lim.enabled = True
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
import docx
import anthropic
from app.indexer.store import PolicyStore
from app.indexer.pipeline import index_document
from app.email_ingestion.mock_inbox import MockInbox
from app.email_ingestion.models import Email
from app.delivery.draft_store import DraftStore


SAMPLE_TEXT = (
    "Employees are entitled to fifteen days of paid vacation per year. "
    "Vacation days accrue at a rate of one point two five days per month. "
    "Unused vacation days up to five may be carried over to the next year. "
    "Vacation requests must be submitted two weeks in advance via the HR portal. "
    "Sick leave is separate from vacation leave and amounts to ten days per year. "
    "Medical certificates are required for sick leave exceeding three consecutive days. "
    "The company observes twelve public holidays annually. "
)


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "test_policy.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=A4)
    styles = getSampleStyleSheet()
    doc.build([Paragraph(SAMPLE_TEXT * 10, styles["BodyText"])])
    return path


@pytest.fixture
def sample_docx(tmp_path: Path) -> Path:
    path = tmp_path / "test_policy.docx"
    document = docx.Document()
    document.add_paragraph(SAMPLE_TEXT * 10)
    document.save(str(path))
    return path


@pytest.fixture
def store(tmp_path: Path) -> PolicyStore:
    return PolicyStore(
        db_path=str(tmp_path / "test_chroma"),
        collection_name="test_policies",
    )


# --- Integration fixtures (session-scoped to avoid re-indexing on every test) ---

SAMPLE_DOCS_DIR = Path(__file__).parent.parent / "sample_docs"


@pytest.fixture(scope="session")
def indexed_store(tmp_path_factory) -> PolicyStore:
    db_path = str(tmp_path_factory.mktemp("integration_chroma"))
    s = PolicyStore(db_path=db_path, collection_name="integration_policies")
    for doc_path in sorted(SAMPLE_DOCS_DIR.glob("*.pdf")) + sorted(SAMPLE_DOCS_DIR.glob("*.docx")):
        index_document(doc_path, store=s)
    return s


@pytest.fixture
def inbox(tmp_path: Path) -> MockInbox:
    return MockInbox(db_path=str(tmp_path / "test_inbox.db"))


@pytest.fixture
def draft_store(tmp_path: Path) -> DraftStore:
    return DraftStore(db_path=str(tmp_path / "test_drafts.db"))


@pytest.fixture
def sample_email() -> Email:
    return Email(
        sender="employee@company.com",
        subject="Vacation question",
        body="Hi, how many vacation days do I get per year?\n\nThanks",
        message_id=str(uuid.uuid4()),
    )


@pytest.fixture(scope="session")
def api_client() -> anthropic.Anthropic:
    from app.config import settings
    if not settings.anthropic_api_key:
        pytest.skip("ANTHROPIC_API_KEY not set — skipping integration test")
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)
