import re


_BLOCKED_PATTERNS = [
    r"(?i)ignore previous instructions",
    r"(?i)disregard (your|all) (instructions|rules)",
    r"(?i)act as (if you are|an? )",
]


def validate_output(text: str) -> str:
    """Strip prompt injection attempts from LLM output."""
    for pattern in _BLOCKED_PATTERNS:
        text = re.sub(pattern, "[REDACTED]", text)
    return text.strip()
