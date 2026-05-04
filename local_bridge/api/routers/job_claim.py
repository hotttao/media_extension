"""Router for /v1/job/claim."""
from fastapi import APIRouter, Request, Header
from local_bridge.api.schemas import ClaimResponse

router = APIRouter(prefix="/v1", tags=["job"])


@router.get("/job/claim", response_model=ClaimResponse)
def claim_job(request: Request, x_worker_id: str | None = Header(None)):
    store = request.app.state.store
    host = request.headers.get("Host", "127.0.0.1:8765")
    base_url = f"http://{host}"
    job = store.claim_next_job(x_worker_id)
    if job:
        return ClaimResponse(job=job.to_public_dict(base_url))
    return ClaimResponse(job=None)