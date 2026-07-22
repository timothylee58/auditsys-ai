"""RAGAS evaluation suite runner.

Evaluates the RAG pipeline against golden Q&A datasets using RAGAS metrics:
- Faithfulness: Does the answer stick to the retrieved context?
- Answer Relevancy: Is the answer relevant to the question?
- Context Recall: Are the right chunks being retrieved?
- Context Precision: Is retrieval precise (not too noisy)?
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from app.config import settings

# Default golden dataset location
_GOLDEN_DATASET_PATH = Path(__file__).parent.parent.parent.parent / "ml" / "golden_datasets" / "financial_qa_v1.json"


def load_golden_dataset(path: Path | None = None) -> list[dict[str, Any]]:
    """Load the golden Q&A evaluation dataset.

    Args:
        path: Optional override path. Defaults to ml/golden_datasets/financial_qa_v1.json.

    Returns:
        List of evaluation examples with question, answer, contexts.
    """
    dataset_path = path or _GOLDEN_DATASET_PATH
    if not dataset_path.exists():
        logger.warning("golden_dataset_not_found path={}", dataset_path)
        return []

    with open(dataset_path) as f:
        data = json.load(f)

    logger.info("golden_dataset_loaded examples={}", len(data))
    return data


async def run_ragas_evaluation(
    dataset: list[dict[str, Any]] | None = None,
) -> dict[str, float]:
    """Execute RAGAS evaluation suite.

    Args:
        dataset: Optional override dataset. If None, loads the default golden dataset.

    Returns:
        Dict of metric_name -> score (0.0 to 1.0).
    """
    if dataset is None:
        dataset = load_golden_dataset()

    if not dataset:
        logger.warning("ragas_eval_skipped reason=empty_dataset")
        return {
            "faithfulness": 0.0,
            "answer_relevancy": 0.0,
            "context_recall": 0.0,
            "context_precision": 0.0,
        }

    logger.info("ragas_eval_start examples={}", len(dataset))

    try:
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )
        from datasets import Dataset

        # Prepare RAGAS-compatible dataset
        eval_data = {
            "question": [ex["question"] for ex in dataset],
            "answer": [ex.get("answer", "") for ex in dataset],
            "contexts": [ex.get("contexts", []) for ex in dataset],
            "ground_truth": [ex.get("ground_truth", ex.get("answer", "")) for ex in dataset],
        }

        hf_dataset = Dataset.from_dict(eval_data)

        result = evaluate(
            hf_dataset,
            metrics=[faithfulness, answer_relevancy, context_recall, context_precision],
        )

        scores = {
            "faithfulness": float(result.get("faithfulness", 0.0)),
            "answer_relevancy": float(result.get("answer_relevancy", 0.0)),
            "context_recall": float(result.get("context_recall", 0.0)),
            "context_precision": float(result.get("context_precision", 0.0)),
        }

        logger.info("ragas_eval_complete scores={}", scores)
        return scores

    except ImportError as exc:
        logger.error("ragas_import_failed error={}", str(exc))
        # Return baseline scores when RAGAS is not installed
        return {
            "faithfulness": 0.0,
            "answer_relevancy": 0.0,
            "context_recall": 0.0,
            "context_precision": 0.0,
        }
    except Exception as exc:
        logger.error("ragas_eval_failed error={}", str(exc))
        raise
