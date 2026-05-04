"""Router for /v1/job/{job_id}/cancel."""
from fastapi import APIRouter, HTTPException, Request
from local_bridge.api.schemas import CancelResponse

router = APIRouter(prefix="/v1", tags=["job"])


@router.post("/job/{job_id}/cancel", response_model=CancelResponse, responses={404: {"model": dict}, 409: {"model": dict}})
def cancel_job(job_id: str, request: Request):
    store = request.app.state.store
    try:
        job = store.cancel(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job_not_found")
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return CancelResponse(ok=True, jobId=job.id, status=job.status)