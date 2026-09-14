"""
AuditSys AI — Output Validator
===============================
Runs on every generated answer before confidence scoring. Blocks schema
leakage and raw DB values (see pii_detector.py for the separate PII scan).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Patterns that suggest raw DB/internal data leaked into the answer
SCHEMA_LEAK_PATTERNS = [
    r"\buuid\b",
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",  # UUID
    r"\buser_id\b",
    r"\bdocument_id\b",
    r"\bchunk_id\b",
    r"\bembedding\b",
    r"\bpgvector\b",
    r"\bsupabase\b",
    r"\bauth\.users\b",
    r"SELECT\s+\*\s+FROM",
    r"INSERT\s+INTO",
]

# Prompt-injection strings the model may echo back from adversarial context
_INJECTION_PATTERNS = [
    r"(?i)ignore previous instructions",
    r"(?i)disregard (your|all) (instructions|rules)",
    r"(?i)act as (if you are|an? )",
]


@dataclass
class ValidationResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    cleaned_text: str = ""


async def validate_output(answer: str) -> ValidationResult:
    """
    Check answer for schema leakage, internal metadata exposure, or echoed
    prompt-injection strings. Strips injection strings from the returned
    `cleaned_text` regardless of outcome; schema leaks are reported as
    errors rather than silently stripped, since removing them can leave a
    misleading answer — the caller (rag_agent) decides how to handle a
    failed validation (e.g. route to review).
    """
    errors: list[str] = []
    cleaned = answer

    for pattern in _INJECTION_PATTERNS:
        cleaned = re.sub(pattern, "[REDACTED]", cleaned)

    lower_answer = cleaned.lower()
    for pattern in SCHEMA_LEAK_PATTERNS:
        if re.search(pattern, lower_answer, re.IGNORECASE):
            errors.append(f"Possible schema/internal data leak: pattern '{pattern}'")

    # Block suspiciously short answers that passed retrieval
    if len(cleaned.strip()) < 10:
        errors.append("Answer too short — likely degenerate output")

    return ValidationResult(passed=len(errors) == 0, errors=errors, cleaned_text=cleaned.strip())
