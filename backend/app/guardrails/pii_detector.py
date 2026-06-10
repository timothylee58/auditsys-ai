from loguru import logger


def redact_pii(text: str) -> str:
    """Redact PII using Presidio when available, else pass through."""
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine

        analyzer = AnalyzerEngine()
        anonymizer = AnonymizerEngine()
        results = analyzer.analyze(text=text, language="en")
        if results:
            anonymized = anonymizer.anonymize(text=text, analyzer_results=results)
            logger.debug("pii_redacted entity_count={}", len(results))
            return anonymized.text
    except ImportError:
        pass
    return text
