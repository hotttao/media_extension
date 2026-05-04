"""Router for /v1/job/{job_id}/requeue."""
from fastapi import APIRouter, HTTPException, Request
from local_bridge.api.schemas import RequeueResponse

router = APIRouter(tags=["job"])


@router.post("/job/{job_id}/requeue", response_model=RequeueResponse, responses={404: {"model": dict}})
def requeue_job(job_id: str, request: Request):
    store = request.app.state.store
    try:
        job = store.requeue(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job_not_found")
    return RequeueResponse(ok=True, jobId=job.id, status=job.status)