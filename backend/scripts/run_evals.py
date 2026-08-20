#!/usr/bin/env python
"""
AuditSys AI — Eval Runner
Usage: python backend/scripts/run_evals.py [--live]

--live: calls the live agent for answers (slower, end-to-end)
        default: uses pre-computed answers from golden dataset
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Ensure backend is on path when run from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.evals.ragas_runner import DEFAULT_CONFIG_PATH, DEFAULT_DATASET_PATH, run_eval_suite


async def main():
    parser = argparse.ArgumentParser(description="Run AuditSys RAGAS eval suite")
    parser.add_argument("--live", action="store_true", help="Use live agent for answers")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    args = parser.parse_args()

    print("=" * 60)
    print("AuditSys AI — RAGAS Eval Suite")
    print(f"Dataset: {args.dataset}")
    print(f"Mode:    {'live agent' if args.live else 'golden dataset (pre-computed)'}")
    print("=" * 60)

    result = await run_eval_suite(
        dataset_path=args.dataset,
        config_path=args.config,
        use_live_agent=args.live,
    )

    print("\n" + result.summary())

    if not result.passed:
        print("\n❌ Eval regression detected — blocking PR merge")
        sys.exit(1)
    else:
        print("\n✅ All metrics above baseline — eval gate passed")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
