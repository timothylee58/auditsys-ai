"""RAGAS evaluation runner.

Executes the golden Q&A dataset through the live RAG agent, scores the
results with RAGAS, and persists a summary row (plus per-question detail)
to Supabase `eval_results`. Used by both the `/evals/run` API route and
`scripts/run_evals.py` (CI gate).
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from app.agents.rag_agent import run_agent
from app.core.database import get_supabase

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "ml" / "evals" / "ragas_config.yaml"
TABLE = "eval_results"


def _load_config() -> dict[str, Any]:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _load_dataset(dataset_path: str) -> list[dict[str, Any]]:
    with open(REPO_ROOT / dataset_path) as f:
        return json.load(f)["items"]


async def _collect_agent_outputs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in items:
        result = await run_agent(item["question"])
        contexts = [c.get("content", "") for c in result.get("context", {}).get("chunks", [])]
        rows.append(
            {
                "id": item["id"],
                "question": item["question"],
                "answer": result.get("answer", ""),
                "contexts": contexts or [""],
                "ground_truth": item["ground_truth"],
            }
        )
    return rows


def _score_with_ragas(rows: list[dict[str, Any]], metric_names: list[str]) -> dict[str, Any]:
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

    metric_map = {
        "faithfulness": faithfulness,
        "answer_relevancy": answer_relevancy,
        "context_recall": context_recall,
        "context_precision": context_precision,
    }
    metrics = [metric_map[name] for name in metric_names if name in metric_map]

    dataset = Dataset.from_list(
        [
            {
                "question": row["question"],
                "answer": row["answer"],
                "contexts": row["contexts"],
                "ground_truth": row["ground_truth"],
            }
            for row in rows
        ]
    )
    result = evaluate(dataset, metrics=metrics)
    df = result.to_pandas()

    per_question = []
    for row, (_, scored) in zip(rows, df.iterrows()):
        per_question.append(
            {
                "id": row["id"],
                "question": row["question"],
                **{name: float(scored[name]) for name in metric_names if name in scored},
            }
        )

    summary = {name: float(df[name].mean()) for name in metric_names if name in df.columns}
    return {"summary": summary, "per_question": per_question}


async def run_eval_suite(*, sample_limit: int | None = None) -> dict[str, Any]:
    """Run the full golden-dataset eval suite and persist results."""
    config = _load_config()
    items = _load_dataset(config["dataset_path"])
    if sample_limit:
        items = items[:sample_limit]

    run_id = str(uuid.uuid4())
    logger.info("eval_run_start run_id={} items={}", run_id, len(items))

    rows = await _collect_agent_outputs(items)
    scored = _score_with_ragas(rows, config["metrics"])
    summary = scored["summary"]

    baselines = config.get("baselines", {})
    passed = all(summary.get(name, 0.0) >= threshold for name, threshold in baselines.items())

    record = {
        "run_id": run_id,
        "dataset_name": config["dataset"],
        "faithfulness": summary.get("faithfulness"),
        "answer_relevancy": summary.get("answer_relevancy"),
        "context_recall": summary.get("context_recall"),
        "context_precision": summary.get("context_precision"),
        "per_question": scored["per_question"],
        "status": "completed",
    }

    try:
        get_supabase().table(TABLE).insert(record).execute()
    except Exception as exc:  # noqa: BLE001 - eval results are best-effort to persist
        logger.error("eval_result_persist_failed run_id={} error={}", run_id, exc)

    logger.info("eval_run_complete run_id={} passed_baseline={} summary={}", run_id, passed, summary)
    return {"run_id": run_id, "summary": summary, "passed_baseline": passed, "baselines": baselines}
