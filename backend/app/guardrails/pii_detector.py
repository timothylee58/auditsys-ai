"""
AuditSys AI — PII Detector
===========================
Presidio-based personal data detection, run on every generated answer
after output validation. Falls back to a lightweight regex scan when
Presidio isn't installed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from loguru import logger


@dataclass
class PIIResult:
    has_pii: bool
    entity_types: list[str] = field(default_factory=list)
    anonymised_text: str = ""


async def scan_pii(text: str) -> PIIResult:
    """
    Scan text for PII using Microsoft Presidio.
    Detects: PERSON, EMAIL, PHONE, CREDIT_CARD, IBAN, UK_NHS, etc.
    Returns the anonymised text alongside which entity types were found.
    Falls back to a regex scan if Presidio isn't installed.
    """
    from app.core.settings import settings

    if not settings.presidio_enabled:
        return PIIResult(has_pii=False)

    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine

        analyzer = AnalyzerEngine()
        anonymizer = AnonymizerEngine()

        results = analyzer.analyze(
            text=text,
            language="en",
            entities=[
                "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER",
                "CREDIT_CARD", "IBAN_CODE", "UK_NHS",
                "US_SSN", "US_BANK_NUMBER", "IP_ADDRESS",
            ],
        )

        if not results:
            return PIIResult(has_pii=False)

        anonymised = anonymizer.anonymize(text=text, analyzer_results=results)
        entity_types = list({r.entity_type for r in results})
        logger.debug("pii_detected entity_types={}", entity_types)

        return PIIResult(
            has_pii=True,
            entity_types=entity_types,
            anonymised_text=anonymised.text,
        )

    except ImportError:
        # Presidio not installed — fall back to basic regex
        return _regex_pii_scan(text)


def _regex_pii_scan(text: str) -> PIIResult:
    """Lightweight regex fallback for PII detection."""
    patterns = {
        "EMAIL": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "PHONE": r"\b(?:\+44|0)[\d\s\-]{9,12}\b",
        "UK_NI": r"\b[A-Z]{2}\d{6}[A-Z]\b",
    }
    found = []
    anonymised = text
    for entity_type, pattern in patterns.items():
        if re.search(pattern, anonymised):
            found.append(entity_type)
            anonymised = re.sub(pattern, f"<{entity_type}>", anonymised)

    return PIIResult(
        has_pii=len(found) > 0,
        entity_types=found,
        anonymised_text=anonymised if found else "",
    )
