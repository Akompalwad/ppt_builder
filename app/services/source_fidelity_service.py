"""Rules for source-grounded presentation requests.

This is intentionally opt-in. A normal creative prompt still allows the
content agent to research, explain, and compose. When a requester pastes a
Word-document extract and explicitly asks for fidelity, the supplied text is
the only factual source and may be shortened only into complete statements.
"""
from __future__ import annotations

import re


_SOURCE_FIDELITY = re.compile(
    r"(?ix)\b(?:"
    r"source\s+fidelity|"
    r"use\s+only\s+(?:the\s+)?(?:provided|following|pasted)\s+(?:content|text|document|material)|"
    r"based\s+solely\s+on\s+(?:the\s+)?(?:provided|following|pasted)\s+(?:content|text|document|material)|"
    r"do\s+not\s+(?:change|alter|distort)\s+(?:the\s+)?(?:meaning|facts|figures|data)|"
    r"preserve\s+(?:the\s+)?(?:meaning|facts|figures|data)"
    r")\b"
)


def source_fidelity_requested(prompt: str | None) -> bool:
    """Return true only for an explicit request to preserve supplied material."""
    return bool(_SOURCE_FIDELITY.search(prompt or ""))


SOURCE_FIDELITY_INSTRUCTION = (
    "SOURCE-FIDELITY MODE: The requester supplied source material. Use it as the only "
    "factual source. You may condense it for slide readability, but retain names, dates, "
    "numbers, units, qualifiers, causal relationships, and uncertainty. Do not invent, "
    "estimate, embellish, or replace any factual claim. Omit a detail only when necessary "
    "for fit; never state a stronger, weaker, or different claim."
)
