from __future__ import annotations
from dataclasses import dataclass, field
import anthropic
from app.config import settings
from app.indexer.store import PolicyStore
from app.delivery.draft_store import DraftStore
from app.audit.audit_log import AuditStore
from app.email_ingestion.mock_inbox import MockInbox


@dataclass
class RuntimeSettings:
    human_review_mode: bool = False
    n_results: int = 5


_runtime_settings = RuntimeSettings()


def get_policy_store() -> PolicyStore:
    return PolicyStore(db_path=settings.chroma_db_path, collection_name=settings.collection_name)


def get_draft_store() -> DraftStore:
    return DraftStore(db_path=settings.db_path)


def get_audit_store() -> AuditStore:
    return AuditStore(db_path=settings.db_path)


def get_mock_inbox() -> MockInbox:
    return MockInbox(db_path=settings.db_path)


def get_inbox():
    """Return the appropriate inbox based on config: Gmail > M365 > Mock."""
    if settings.gmail_use_inbox:
        from app.gmail.gmail_inbox import GmailInbox
        return GmailInbox()
    if settings.ms365_use_real_inbox:
        from app.ms365.graph_inbox import GraphInbox
        return GraphInbox()
    return MockInbox(db_path=settings.db_path)


def get_anthropic_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def get_runtime_settings() -> RuntimeSettings:
    return _runtime_settings
