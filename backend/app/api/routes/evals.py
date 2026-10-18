import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import CurrentUser, get_current_user, require_admin
from app.core.database import get_async_supabase
from app.evals.ragas_runner import run_eval_suite

router = APIRouter(prefix="/evals", tags=["evals"])

# Tracks jobs kicked off via POST /evals/run for this process's lifetime.
_jobs: dict[str, dict] = {}


async def _run_job(job_id: str) -> None:
    _jobs[job_id]["status"] = "running"
    try:
        result = await run_eval_suite()
        _jobs[job_id] = {
            "status": "completed",
            "result": {
                "run_id": result.run_id,
                "dataset_path": str(result.dataset_path),
                "scores": result.scores,
                "baselines": result.baselines,
                "passed": result.passed,
                "per_question": result.per_question,
            },
        }
    except Exception as exc:  # noqa: BLE001 - surface failure to the poller
        _jobs[job_id] = {"status": "failed", "error": str(exc)}


@router.post("/run", status_code=202)
async def trigger_eval_run(user: CurrentUser = Depends(require_admin)) -> dict:
    """Kick off the RAGAS golden-dataset eval suite asynchronously.

    Admin-only: an eval run burns real Azure OpenAI spend, so any
    authenticated account must not be able to trigger it in a loop.
    """
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "queued", "triggered_by": user.user_id}
    asyncio.create_task(_run_job(job_id))
    return {"job_id": job_id, "status": "queued"}


@router.get("/run/{job_id}")
async def get_job_status(job_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Eval job not found") from None
    return {"job_id": job_id, **job}


@router.get("/results")
async def list_eval_results(
    limit: int = 20,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """List past eval run summaries, newest first."""
    client = await get_async_supabase()
    result = await (
        client.table("eval_results")
        .select("id, run_id, dataset_name, faithfulness, answer_relevancy, "
                "context_recall, context_precision, status, created_at")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return {"runs": result.data or []}


@router.get("/results/{run_id}")
async def get_eval_result(
    run_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    client = await get_async_supabase()
    result = await client.table("eval_results").select("*").eq("run_id", run_id).limit(1).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Eval run not found") from None
    return result.data[0]
