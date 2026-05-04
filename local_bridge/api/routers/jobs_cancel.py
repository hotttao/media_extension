"""Router for /v1/jobs/cancel."""
from fastapi import APIRouter, Request
from local_bridge.api.schemas import CancelAllResponse

router = APIRouter(tags=["jobs"])


@router.post("/jobs/cancel", response_model=CancelAllResponse)
def cancel_all_jobs(request: Request):
    store = request.app.state.store
    canceled = store.cancel_all()
    return CancelAllResponse(
        ok=True,
        canceled=[{"jobId": j.id, "status": j.status} for j in canceled],
    )