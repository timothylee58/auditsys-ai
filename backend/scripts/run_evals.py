#!/usr/bin/env python
"""CI entrypoint: run the RAGAS golden-dataset eval suite and gate on baselines.

Usage: python scripts/run_evals.py
Exits 0 when every metric clears its `ml/evals/ragas_config.yaml` baseline,
1 otherwise (or on error). Prints per-metric scores to stdout.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.evals.ragas_runner import run_eval_suite


async def main() -> int:
    result = await run_eval_suite()
    summary = result["summary"]
    baselines = result["baselines"]

    print(f"RAGAS eval run {result['run_id']}")
    print(f"{'metric':<20}{'score':<10}{'baseline':<10}{'status'}")
    for name, score in summary.items():
        threshold = baselines.get(name)
        ok = threshold is None or score >= threshold
        status = "PASS" if ok else "FAIL"
        print(f"{name:<20}{score:<10.3f}{threshold if threshold is not None else '-':<10}{status}")

    if not result["passed_baseline"]:
        print("One or more metrics fell below baseline.")
        return 1

    print("All metrics cleared baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
