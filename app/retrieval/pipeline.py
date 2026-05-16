from __future__ import annotations
import anthropic
from app.indexer.store import PolicyStore
from app.retrieval.retriever import retrieve
from app.retrieval.generator import generate_answer
from app.retrieval.validator import validate_answer
from app.config import settings


def answer_question(
    question: str,
    store: PolicyStore,
    n_results: int = 5,
    client: anthropic.Anthropic | None = None,
) -> dict:
    if client is None:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    chunks = retrieve(question, store, n_results=n_results)
    generated = generate_answer(question, chunks, client=client)
    validation = validate_answer(question, generated["answer"], chunks, client=client)

    return {
        "question": question,
        "answer": generated["answer"],
        "sources": generated["sources"],
        "validation": validation,
        "chunks_used": len(chunks),
    }
