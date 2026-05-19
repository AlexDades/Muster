from __future__ import annotations
import re
import anthropic
from app.config import settings

SYSTEM_PROMPT = """You are a warm, helpful HR policy assistant writing a reply to an employee's question. Your answer will be inserted into an email that already has a greeting and a sign-off, so write only the body — no "Hello", no "Best regards", nothing like that.

Rules:
- Base your answer strictly on the provided policy excerpts. Never invent or assume details not stated in the documents.
- Write in a friendly but professional tone — like a knowledgeable colleague, not a legal document.
- After each factual claim, add an inline citation in the format [Source: filename].
- If the answer cannot be found in the provided excerpts, respond with exactly: "I wasn't able to find this in our current policy documents — I'd recommend checking with the HR team directly."
- Keep it concise. One short paragraph is usually enough; use a brief bullet list only if the answer has multiple distinct parts.
- Never extrapolate beyond what the documents state."""


def _format_context(chunks: list[dict]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, 1):
        filename = chunk["metadata"]["filename"]
        parts.append(f"[Excerpt {i} — {filename}]\n{chunk['text']}")
    return "\n\n---\n\n".join(parts)


def _extract_sources(text: str) -> list[str]:
    found = re.findall(r'\[Source:\s*([^\]]+)\]', text)
    seen: set[str] = set()
    unique = []
    for s in found:
        s = s.strip()
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique


CHAT_SYSTEM_PROMPT = """You are a warm, helpful HR policy assistant answering questions in a live chat with an employee.

Rules:
- Base your answer strictly on the provided policy excerpts. Never invent or assume details not stated in the documents.
- Write in a friendly, conversational tone — like a knowledgeable colleague.
- After each factual claim, add an inline citation in the format [Source: filename].
- If the answer cannot be found in the provided excerpts, say so naturally and recommend checking with the HR team directly.
- Keep it concise. One short paragraph is usually enough; use a brief bullet list only if the answer has multiple distinct parts.
- Never extrapolate beyond what the documents state.
- You have access to the conversation history — use it to give coherent follow-up answers without the employee needing to repeat themselves."""


def generate_chat_answer(
    message: str,
    chunks: list[dict],
    history: list[dict],
    client: anthropic.Anthropic | None = None,
) -> dict:
    if client is None:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    context = _format_context(chunks) if chunks else "No relevant policy excerpts found."

    # History contains clean Q&A pairs; current message gets fresh policy context
    messages = list(history)
    messages.append({
        "role": "user",
        "content": f"Policy excerpts:\n\n{context}\n\nQuestion: {message}",
    })

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=[{"type": "text", "text": CHAT_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=messages,
    )
    answer_text = response.content[0].text
    return {
        "answer": answer_text,
        "sources": _extract_sources(answer_text),
    }


def is_policy_question(question: str, client: anthropic.Anthropic | None = None) -> bool:
    """Return True if the question is an HR policy matter worth answering."""
    if client is None:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=5,
        system="You are a classifier. Reply with only YES or NO.",
        messages=[{
            "role": "user",
            "content": (
                "Is this a question about HR or company policy — such as leave, expenses, "
                "working hours, benefits, conduct, or similar workplace topics?\n\n"
                f"Message: {question}"
            ),
        }],
    )
    return response.content[0].text.strip().upper().startswith("Y")


def generate_answer(
    question: str,
    chunks: list[dict],
    client: anthropic.Anthropic | None = None,
) -> dict:
    if not chunks:
        return {
            "answer": "I could not find this information in the available policy documents.",
            "sources": [],
        }

    if client is None:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    context = _format_context(chunks)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": (
                    f"Policy document excerpts:\n\n{context}\n\n"
                    f"Employee question: {question}"
                ),
            }
        ],
    )
    answer_text = response.content[0].text
    return {
        "answer": answer_text,
        "sources": _extract_sources(answer_text),
    }
