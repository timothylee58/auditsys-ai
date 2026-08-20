import asyncio
import uuid

from fastapi import APIRouter, HTTPException

from app.core.database import get_supabase
from app.evals.ragas_runner import run_eval_suite

router = APIRouter(prefix="/evals", tags=["evals"])

# Tracks jobs kicked off via POST /evals/run for this process's lifetime.
_jobs: dict[str, dict] = {}


async def _run_job(job_id: str) -> None:
    _jobs[job_id]["status"] = "running"
    try:
        result = await run_eval_suite()
        _jobs[job_id] = {"status": "completed", "result": result}
    except Exception as exc:  # noqa: BLE001 - surface failure to the poller
        _jobs[job_id] = {"status": "failed", "error": str(exc)}


@router.post("/run", status_code=202)
async def trigger_eval_run() -> dict:
    """Kick off the RAGAS golden-dataset eval suite asynchronously."""
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "queued"}
    asyncio.create_task(_run_job(job_id))
    return {"job_id": job_id, "status": "queued"}


@router.get("/run/{job_id}")
async def get_job_status(job_id: str) -> dict:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Eval job not found")
    return {"job_id": job_id, **job}


@router.get("/results")
async def list_eval_results(limit: int = 20) -> dict:
    """List past eval run summaries, newest first."""
    client = get_supabase()
    result = (
        client.table("eval_results")
        .select("id, run_id, dataset_name, faithfulness, answer_relevancy, "
                "context_recall, context_precision, status, created_at")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return {"runs": result.data or []}


@router.get("/results/{run_id}")
async def get_eval_result(run_id: str) -> dict:
    client = get_supabase()
    result = client.table("eval_results").select("*").eq("run_id", run_id).limit(1).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Eval run not found")
    return result.data[0]
