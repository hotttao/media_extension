"""Router for /v1/job/{job_id}/progress."""
from fastapi import APIRouter, HTTPException, Request
from local_bridge.api.schemas import ProgressUpdateRequest, SuccessResponse

router = APIRouter(tags=["job"])


@router.post("/job/{job_id}/progress", response_model=SuccessResponse, responses={404: {"model": dict}})
def update_progress(job_id: str, body: ProgressUpdateRequest, request: Request):
    store = request.app.state.store
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job_not_found")
    store.add_progress(job_id, body.message, at=body.at, details=body.details)
    return SuccessResponse(ok=True)