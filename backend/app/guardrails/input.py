"""Input guardrails: screen the question, and neutralise retrieved text.

Two different trust problems live here:

* **The question** is user input. It is screened for prompt-injection
  phrasing and for PII. Injection attempts are refused. PII is not refused
  (auditors legitimately ask about named people) but the *logged* copy of
  the question is redacted, so raw personal data is not written to the audit
  trail. The model still receives the original question.
* **Retrieved document text** is untrusted input too. Anyone who can get a
  file ingested can plant instructions in it. ``neutralize_retrieved_text``
  strips invisible characters, markdown images (a data-exfiltration channel)
  and instruction-like lines before the text is shown to a model, and
  reports what it removed. Retrieved text can never choose tools — the
  agent graph has no tool-calling node at all, which is the real defence;
  this is defence in depth.

Pattern matching catches the lazy attacks, not a determined adversary. The
red-team set (``eval/redteam.jsonl``) measures what slips through.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from app.guardrails.pii_detector import scan_pii

MAX_QUESTION_CHARS = 2000
REMOVED_MARKER = "[instruction-like text removed]"

# (reason, pattern). Case-insensitive; reasons are stable identifiers used in
# audit entries and metrics.
_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "override_instructions",
        re.compile(
            r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b(previous|prior|above|earlier|all|any|your|the)\b"
            r"[^.\n]{0,30}\b(instructions?|prompts?|rules?|guidelines?|context)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "reveal_system_prompt",
        re.compile(
            r"\b(reveal|print|show|repeat|output|leak|disclose)\b[^.\n]{0,30}"
            r"\b(system|hidden|initial|secret)\b[^.\n]{0,15}\b(prompt|instructions?|message)\b",
            re.IGNORECASE,
        ),
    ),
    ("role_override", re.compile(r"\byou are now (an?|the|in)\b|\bact as (if you (are|were)|an?)\b", re.IGNORECASE)),
    ("new_instructions", re.compile(r"\b(new|updated|override|revised)\s+(system\s+)?instructions?\s*:", re.IGNORECASE)),
    ("control_tokens", re.compile(r"<\|?\s*(im_start|im_end|system|endoftext|assistant)\s*\|?>", re.IGNORECASE)),
    ("role_marker", re.compile(r"^\s*(system|assistant|developer)\s*:", re.IGNORECASE | re.MULTILINE)),
    ("jailbreak", re.compile(r"\b(developer mode|jailbreak|do anything now)\b", re.IGNORECASE)),
    (
        "tool_directive",
        re.compile(
            r"\b(call|invoke|run|execute|use)\s+(the\s+)?(tool|function|command|code|shell)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "secrecy_directive",
        re.compile(r"\bdo not (tell|inform|mention|reveal)\b[^.\n]{0,40}\b(user|anyone|reviewer|auditor)\b", re.IGNORECASE),
    ),
]
_MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass
class ScreenResult:
    allowed: bool
    reasons: list[str] = field(default_factory=list)
    log_question: str = ""
    pii_types: list[str] = field(default_factory=list)


def find_injection(text: str) -> list[str]:
    """Reasons for every injection pattern present in ``text`` (stable ids)."""
    cleaned = strip_invisible(text)
    return [reason for reason, pattern in _INJECTION_PATTERNS if pattern.search(cleaned)]


def strip_invisible(text: str) -> str:
    """Remove zero-width, bidi/format (Cf) and control characters — the usual
    way to hide instructions from a human reviewer while a model reads them."""
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    return _CONTROL_CHARS.sub("", text)


async def screen_question(question: str) -> ScreenResult:
    """Screen a user question. ``allowed`` is False for injection attempts or
    over-long input; PII is flagged and redacted in ``log_question`` only."""
    reasons: list[str] = []
    if not question.strip():
        reasons.append("empty_question")
    if len(question) > MAX_QUESTION_CHARS:
        reasons.append("question_too_long")
    reasons.extend(f"injection:{r}" for r in find_injection(question))

    pii = await scan_pii(question)
    log_question = pii.anonymised_text if pii.has_pii and pii.anonymised_text else question

    return ScreenResult(
        allowed=not reasons,
        reasons=reasons,
        log_question=log_question,
        pii_types=pii.entity_types if pii.has_pii else [],
    )


def neutralize_retrieved_text(text: str) -> tuple[str, list[str]]:
    """Make retrieved text safer to put in a prompt.

    Returns ``(clean_text, reasons)``. Instruction-like lines are replaced by
    a visible marker (not silently deleted, so the model and the audit trail
    both know something was removed). The original span text is never
    modified — only the copy shown to the model.
    """
    reasons: list[str] = []
    cleaned = strip_invisible(text)
    if cleaned != text:
        reasons.append("hidden_characters")

    if _MARKDOWN_IMAGE.search(cleaned):
        cleaned = _MARKDOWN_IMAGE.sub("[image removed]", cleaned)
        reasons.append("markdown_image")

    out_lines: list[str] = []
    for line in cleaned.split("\n"):
        hits = [reason for reason, pattern in _INJECTION_PATTERNS if pattern.search(line)]
        if hits:
            reasons.extend(f"injection:{h}" for h in hits)
            out_lines.append(REMOVED_MARKER)
        else:
            out_lines.append(line)
    return "\n".join(out_lines), sorted(set(reasons))
