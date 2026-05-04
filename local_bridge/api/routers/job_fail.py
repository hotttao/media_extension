"""Router for /v1/job/{job_id}/fail."""
from fastapi import APIRouter, HTTPException, Request
from local_bridge.api.schemas import FailSubmitRequest, SuccessResponse
from local_bridge.domain.models import write_json

router = APIRouter(prefix="/v1", tags=["job"])


@router.post("/job/{job_id}/fail", response_model=SuccessResponse, responses={404: {"model": dict}})
def fail_job(job_id: str, body: FailSubmitRequest, request: Request):
    store = request.app.state.store
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job_not_found")
    job.output_dir.mkdir(parents=True, exist_ok=True)
    (job.output_dir / "prompt.md").write_text(job.prompt, encoding="utf-8")
    if job.progress:
        write_json(job.output_dir / "logs.json", job.progress)
    write_json(
        job.output_dir / "failure.json",
        {
            "jobId": job.id,
            "caseFile": str(job.case_file),
            "status": "failed",
            "createdAt": job.created_at,
            "claimedAt": job.claimed_at,
            "finishedAt": job.finished_at,
            "reason": body.reason,
            "logs": job.progress or body.logs or [],
        },
    )
    store.mark_failed(job_id, body.reason)
    return SuccessResponse(ok=True)