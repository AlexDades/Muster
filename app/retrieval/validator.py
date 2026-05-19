from __future__ import annotations
import json
import re
import anthropic
from app.config import settings

SYSTEM_PROMPT = """You are a quality assurance agent reviewing AI-generated HR policy answers.

Evaluate whether the answer is:
1. Grounded in the provided context — no hallucinations or invented facts
2. Accurately citing sources that appear in the provided excerpts
3. Complete — not omitting critical information from the context that would change the answer
4. Not contradicting anything stated in the provided documents

Respond ONLY with valid JSON in this exact format (no markdown fences, no extra text):
{
  "valid": true,
  "confidence": 0.95,
  "issues": [],
  "reasoning": "brief explanation"
}"""


def _parse_json(text: str) -> dict:
    text = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.MULTILINE)
    text = re.sub(r'\s*```$', '', text.strip(), flags=re.MULTILINE)
    return json.loads(text.strip())


def validate_answer(
    question: str,
    answer: str,
    chunks: list[dict],
    client: anthropic.Anthropic | None = None,
) -> dict:
    if client is None:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    context_summary = "\n\n".join(
        f"[{c['metadata']['filename']}]: {c['text'][:400]}" for c in chunks
    )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
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
                    f"Question: {question}\n\n"
                    f"Context provided to the assistant:\n{context_summary}\n\n"
                    f"Generated answer:\n{answer}"
                ),
            }
        ],
    )

    try:
        return _parse_json(response.content[0].text)
    except (json.JSONDecodeError, KeyError):
        return {
            "valid": False,
            "confidence": 0.0,
            "issues": ["Validator returned unparseable response"],
            "reasoning": response.content[0].text,
        }
