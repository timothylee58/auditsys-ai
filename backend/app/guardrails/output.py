"""Output policy: the last checks before an answer leaves the system.

Runs after claims have been verified. It composes the existing schema-leak
validator and PII scanner and adds two audit-specific rules:

* every non-refusal answer must carry at least one citation marker;
* the answer must not be empty.

PII in the final text is redacted (the claim was verified against the source
first, so redaction only ever removes information) and reported so it can be
logged and alerted on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.guardrails.output_validator import validate_output
from app.guardrails.pii_detector import scan_pii

_CITATION_MARKER = re.compile(r"\[\d+\]")


@dataclass
class OutputPolicyResult:
    passed: bool
    answer: str
    errors: list[str] = field(default_factory=list)
    pii_detected: bool = False
    pii_types: list[str] = field(default_factory=list)


async def enforce_output_policy(answer: str, *, require_citation: bool = True) -> OutputPolicyResult:
    errors: list[str] = []
    if not answer.strip():
        return OutputPolicyResult(passed=False, answer=answer, errors=["empty_answer"])

    validation = await validate_output(answer)
    cleaned = validation.cleaned_text or answer
    errors.extend(validation.errors)

    if require_citation and not _CITATION_MARKER.search(cleaned):
        errors.append("answer_has_no_citation")

    pii = await scan_pii(cleaned)
    if pii.has_pii and pii.anonymised_text:
        cleaned = pii.anonymised_text

    return OutputPolicyResult(
        passed=not errors,
        answer=cleaned,
        errors=errors,
        pii_detected=pii.has_pii,
        pii_types=pii.entity_types if pii.has_pii else [],
    )
