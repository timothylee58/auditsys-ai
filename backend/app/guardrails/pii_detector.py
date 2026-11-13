"""
AuditSys AI — PII Detector
===========================
Presidio-based personal data detection, run on every generated answer
after output validation. Falls back to a lightweight regex scan when
Presidio or its spaCy model isn't available.
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


class PresidioUnavailable(RuntimeError):
    """Presidio or its spaCy model is not installed in this environment."""


# Presidio engines are expensive to build (NLP model load). Instantiate them
# once and reuse across requests instead of per call.
_analyzer = None
_anonymizer = None
_unavailable: str | None = None  # remembered so we neither retry nor re-log per request


def _get_engines():
    """Build the engines once.

    The spaCy model is checked explicitly rather than left to Presidio: when
    the model is missing, Presidio shells out to ``pip`` to download it and
    then calls ``sys.exit`` on failure — a ``SystemExit`` that no ordinary
    ``except`` clause catches and that would kill the request worker. The
    model is baked into the image (see Dockerfile); if it is absent we fall
    back to regex scanning and say so loudly instead.
    """
    global _analyzer, _anonymizer, _unavailable
    if _unavailable is not None:
        raise PresidioUnavailable(_unavailable)
    if _analyzer is None:
        from app.core.settings import settings

        model = settings.presidio_spacy_model
        try:
            import spacy
            from presidio_analyzer import AnalyzerEngine
            from presidio_analyzer.nlp_engine import NlpEngineProvider
            from presidio_anonymizer import AnonymizerEngine
        except ImportError as exc:
            _unavailable = f"presidio/spaCy not installed: {exc}"
            raise PresidioUnavailable(_unavailable) from exc

        if not spacy.util.is_package(model):
            _unavailable = f"spaCy model {model!r} is not installed"
            raise PresidioUnavailable(_unavailable)

        nlp_engine = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": model}],
            }
        ).create_engine()
        _analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
        _anonymizer = AnonymizerEngine()
    return _analyzer, _anonymizer


async def scan_pii(text: str) -> PIIResult:
    """
    Scan text for PII using Microsoft Presidio.
    Detects: PERSON, EMAIL, PHONE, CREDIT_CARD, IBAN, UK_NHS, etc.
    Returns the anonymised text alongside which entity types were found.
    Falls back to a regex scan if Presidio or its spaCy model isn't available.
    """
    from app.core.settings import settings

    if not settings.presidio_enabled:
        return PIIResult(has_pii=False)

    try:
        analyzer, anonymizer = _get_engines()

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

    except PresidioUnavailable as exc:
        # Fall back to basic regex, loudly: the fallback is substantially
        # weaker (no person names) and must not degrade silently.
        logger.warning("pii_presidio_unavailable using_regex_fallback reason={}", exc)
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
