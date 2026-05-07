"""Router for /v1/jobs/cancel."""
from fastapi import APIRouter, Query, Request
from local_bridge.api.schemas import CancelAllResponse

router = APIRouter(tags=["jobs"])


@router.post("/jobs/cancel", response_model=CancelAllResponse)
def cancel_all_jobs(request: Request, platform: str | None = Query(None)):
    store = request.app.state.store
    canceled = store.cancel_all(platform_id=platform)
    return CancelAllResponse(
        ok=True,
        canceled=[{"jobId": j.id, "status": j.status} for j in canceled],
    )
