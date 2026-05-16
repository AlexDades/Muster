from __future__ import annotations
import re


_REPLY_SEPARATORS = re.compile(
    r"(On .+?wrote:|-----Original Message-----|________________________________)",
    re.DOTALL,
)


def extract_question(body: str) -> str:
    """Return the clean question from an email body, stripping quoted reply chains."""
    # Cut at common reply separators
    body = _REPLY_SEPARATORS.split(body)[0]

    # Strip lines that are quoted replies (start with >)
    lines = [line for line in body.splitlines() if not line.startswith(">")]

    return "\n".join(lines).strip()
