from __future__ import annotations
from threading import Lock
from fastapi import APIRouter, Depends
from pydantic import BaseModel
import anthropic
from app.indexer.store import PolicyStore
from app.retrieval.retriever import retrieve
from app.retrieval.generator import generate_chat_answer
from app.config import settings
from app import dependencies as deps

router = APIRouter(prefix="/chat", tags=["chat"])

_sessions: dict[str, list[dict]] = {}
_lock = Lock()
_MAX_TURNS = 10  # keep last 10 Q&A pairs = 20 messages


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[str]
    session_id: str


@router.post("/message")
def chat_message(
    body: ChatRequest,
    store: PolicyStore = Depends(deps.get_policy_store),
) -> ChatResponse:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    with _lock:
        history = list(_sessions.get(body.session_id, []))

    chunks = retrieve(body.message, store, n_results=5)
    result = generate_chat_answer(body.message, chunks, history, client=client)

    with _lock:
        h = list(_sessions.get(body.session_id, []))
        h.append({"role": "user", "content": body.message})
        h.append({"role": "assistant", "content": result["answer"]})
        _sessions[body.session_id] = h[-(_MAX_TURNS * 2):]

    return ChatResponse(
        answer=result["answer"],
        sources=result["sources"],
        session_id=body.session_id,
    )


@router.delete("/{session_id}", status_code=204)
def clear_session(session_id: str) -> None:
    with _lock:
        _sessions.pop(session_id, None)
