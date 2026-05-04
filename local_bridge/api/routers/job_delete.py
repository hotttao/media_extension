"""Router for /v1/job/{job_id}/delete."""
from fastapi import APIRouter, HTTPException, Request
from local_bridge.api.schemas import DeleteResponse

router = APIRouter(tags=["job"])


@router.delete("/job/{job_id}", response_model=DeleteResponse, responses={404: {"model": dict}, 409: {"model": dict}})
def delete_job(job_id: str, request: Request):
    store = request.app.state.store
    try:
        job = store.delete(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job_not_found")
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return DeleteResponse(ok=True, jobId=job.id)