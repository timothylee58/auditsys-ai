def confidence_gate(score: float, threshold: float) -> bool:
    """Return True if score meets threshold (answer can be shown), False if HITL needed."""
    return score >= threshold
