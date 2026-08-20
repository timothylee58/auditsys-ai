"""RAGAS evaluation runner.

Scores the golden Q&A dataset with RAGAS and persists a summary (plus
per-question detail) to Supabase `eval_results` and, when configured, to
`ml/evals/results/`. Used by both the `/evals/run` API route and
`backend/scripts/run_evals.py` (CI gate).

Two modes:
  - use_live_agent=False (default): scores the dataset's own precomputed
    `answer`/`contexts` fields. Fast, no agent/DB calls — good for a CI
    smoke test of the eval pipeline, but only as good as the precomputed
    answers checked into the dataset (see the dataset file's own
    `description` for how trustworthy those currently are).
  - use_live_agent=True (--live): runs each question through the live
    `run_agent()` RAG pipeline and scores what it actually returns today.
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from app.agents.rag_agent import run_agent
from app.core.database import get_supabase

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = REPO_ROOT / "ml" / "evals" / "ragas_config.yaml"
DEFAULT_DATASET_PATH = REPO_ROOT / "ml" / "golden_datasets" / "financial_qa_v1.json"
TABLE = "eval_results"


@dataclass
class EvalResult:
    run_id: str
    dataset_path: Path
    scores: dict[str, float]
    baselines: dict[str, float]
    per_question: list[dict[str, Any]] = field(default_factory=list)
    passed: bool = False

    def summary(self) -> str:
        lines = [f"Run ID: {self.run_id}", f"Dataset: {self.dataset_path}", ""]
        lines.append(f"{'metric':<20}{'score':<10}{'baseline':<10}{'status'}")
        for name, score in self.scores.items():
            threshold = self.baselines.get(name)
            ok = threshold is None or score >= threshold
            status = "PASS" if ok else "FAIL"
            baseline_str = f"{threshold:.2f}" if threshold is not None else "-"
            lines.append(f"{name:<20}{score:<10.3f}{baseline_str:<10}{status}")
        lines.append("")
        lines.append("All metrics above baseline" if self.passed else "Eval regression detected")
        return "\n".join(lines)


def _load_config(config_path: Path) -> dict[str, Any]:
    with open(config_path) as f:
        return yaml.safe_load(f)


def _load_dataset(dataset_path: Path) -> list[dict[str, Any]]:
    with open(dataset_path) as f:
        return json.load(f)["items"]


async def _collect_rows(
    items: list[dict[str, Any]], *, use_live_agent: bool
) -> list[dict[str, Any]]:
    if not use_live_agent:
        return [
            {
                "id": item["id"],
                "question": item["question"],
                "answer": item.get("answer", ""),
                "contexts": item.get("contexts") or [""],
                "ground_truth": item["ground_truth"],
            }
            for item in items
        ]

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


def _persist_to_supabase(record: dict[str, Any]) -> None:
    try:
        get_supabase().table(TABLE).insert(record).execute()
    except Exception as exc:  # noqa: BLE001 - eval results are best-effort to persist
        logger.error("eval_result_persist_failed run_id={} error={}", record["run_id"], exc)


def _save_results_file(result: EvalResult, results_dir: Path) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    out_path = results_dir / f"{result.run_id}.json"
    payload = {
        "run_id": result.run_id,
        "dataset_path": str(result.dataset_path),
        "scores": result.scores,
        "baselines": result.baselines,
        "passed": result.passed,
        "per_question": result.per_question,
        "created_at": datetime.now(UTC).isoformat(),
    }
    out_path.write_text(json.dumps(payload, indent=2))
    logger.info("eval_results_saved path={}", out_path)


def _write_github_step_summary(result: EvalResult) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    lines = ["## ❌ RAGAS eval regression", "", f"Run `{result.run_id}` fell below baseline.", ""]
    lines.append("| metric | score | baseline | status |")
    lines.append("|---|---|---|---|")
    for name, score in result.scores.items():
        threshold = result.baselines.get(name)
        ok = threshold is None or score >= threshold
        status = "✅" if ok else "❌"
        baseline_str = f"{threshold:.2f}" if threshold is not None else "-"
        lines.append(f"| {name} | {score:.3f} | {baseline_str} | {status} |")
    with open(summary_path, "a") as f:
        f.write("\n".join(lines) + "\n")


async def run_eval_suite(
    *,
    dataset_path: Path = DEFAULT_DATASET_PATH,
    config_path: Path = DEFAULT_CONFIG_PATH,
    use_live_agent: bool = False,
) -> EvalResult:
    """Run the golden-dataset eval suite and persist results."""
    config = _load_config(config_path)
    baselines: dict[str, float] = config.get("baselines", {})
    metric_names = list(baselines.keys())

    dataset_cfg = config.get("dataset", {})
    min_samples = dataset_cfg.get("min_samples")

    items = _load_dataset(dataset_path)
    if min_samples and len(items) < min_samples:
        raise ValueError(
            f"Dataset {dataset_path} has {len(items)} samples, below the configured "
            f"min_samples={min_samples}"
        )

    run_id = str(uuid.uuid4())
    logger.info(
        "eval_run_start run_id={} items={} live_agent={}", run_id, len(items), use_live_agent
    )

    rows = await _collect_rows(items, use_live_agent=use_live_agent)
    scored = _score_with_ragas(rows, metric_names)
    summary = scored["summary"]
    passed = all(summary.get(name, 0.0) >= threshold for name, threshold in baselines.items())

    result = EvalResult(
        run_id=run_id,
        dataset_path=dataset_path,
        scores=summary,
        baselines=baselines,
        per_question=scored["per_question"],
        passed=passed,
    )

    _persist_to_supabase(
        {
            "run_id": run_id,
            "dataset_name": dataset_path.stem,
            "faithfulness": summary.get("faithfulness"),
            "answer_relevancy": summary.get("answer_relevancy"),
            "context_recall": summary.get("context_recall"),
            "context_precision": summary.get("context_precision"),
            "per_question": result.per_question,
            "status": "completed",
        }
    )

    reporting = config.get("reporting", {})
    if reporting.get("save_results"):
        results_path = reporting.get("results_path", "ml/evals/results/")
        _save_results_file(result, REPO_ROOT / results_path)
    if reporting.get("notify_on_failure") and not passed:
        _write_github_step_summary(result)

    logger.info("eval_run_complete run_id={} passed={} summary={}", run_id, passed, summary)
    return result
