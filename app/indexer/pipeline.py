from __future__ import annotations
from pathlib import Path
from app.indexer.parser import parse_document
from app.indexer.chunker import chunk_text
from app.indexer.store import PolicyStore
from app.config import settings


def get_store() -> PolicyStore:
    return PolicyStore(
        db_path=settings.chroma_db_path,
        collection_name=settings.collection_name,
    )


def index_document(
    path: str | Path,
    doc_id: str | None = None,
    store: PolicyStore | None = None,
) -> dict:
    path = Path(path)
    if doc_id is None:
        doc_id = path.stem
    if store is None:
        store = get_store()
    parsed = parse_document(path)
    chunks = chunk_text(
        parsed["text"],
        chunk_size=settings.chunk_size,
        overlap=settings.chunk_overlap,
    )
    store.add_document(doc_id=doc_id, chunks=chunks, filename=parsed["filename"])
    return {"doc_id": doc_id, "filename": parsed["filename"], "chunks": len(chunks)}


def remove_document(doc_id: str, store: PolicyStore | None = None) -> None:
    if store is None:
        store = get_store()
    store.delete_document(doc_id)
