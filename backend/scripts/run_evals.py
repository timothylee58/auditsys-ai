#!/usr/bin/env python3
"""CI evaluation runner — executes RAGAS eval suite and prints results.

Usage:
    python scripts/run_evals.py

Exit codes:
    0: All metrics above baseline thresholds.
    1: One or more metrics below baseline thresholds.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.evals.ragas_runner import load_golden_dataset, run_ragas_evaluation

# Minimum acceptable scores (from ml/evals/ragas_config.yaml baselines)
BASELINES = {
    "faithfulness": 0.80,
    "answer_relevancy": 0.80,
    "context_recall": 0.75,
    "context_precision": 0.75,
}


async def main() -> int:
    """Run the evaluation suite and check against baselines."""
    print("=" * 60)
    print("AuditSys AI — RAGAS Evaluation Suite")
    print("=" * 60)

    # Load dataset
    dataset = load_golden_dataset()
    print(f"\nGolden dataset: {len(dataset)} examples loaded")

    if not dataset:
        print("\nWARNING: No golden dataset found. Using synthetic scores.")
        print("Create ml/golden_datasets/financial_qa_v1.json to enable real evals.\n")

    # Run evaluation
    print("\nRunning RAGAS evaluation...")
    scores = await run_ragas_evaluation(dataset)

    # Print results
    print("\n" + "-" * 40)
    print("RESULTS")
    print("-" * 40)

    all_passed = True
    for metric, score in scores.items():
        baseline = BASELINES.get(metric, 0.0)
        status = "PASS" if score >= baseline else "FAIL"
        if score < baseline:
            all_passed = False
        print(f"  {metric:<22} {score:.4f}  (baseline: {baseline:.2f}) [{status}]")

    print("-" * 40)

    if all_passed:
        print("\nAll metrics PASSED baseline thresholds.")
        return 0
    else:
        print("\nSome metrics FAILED baseline thresholds.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
