"""Router for /v1/state and /v1/jobs."""
from fastapi import APIRouter, HTTPException, Request
from local_bridge.api.schemas import (
    ErrorResponse,
    JobCreatedResponse,
    JobsCreateRequest,
    StateResponse,
)
from local_bridge.infrastructure.persistence import JobStore

router = APIRouter(tags=["jobs"])


@router.get("/state", response_model=StateResponse)
def get_state(request: Request):
    store: JobStore | None = getattr(request.app.state, "store", None)
    if store is None:
        return StateResponse(jobs=[])
    return StateResponse(**store.summary())


@router.post("/jobs", response_model=JobCreatedResponse, responses={400: {"model": ErrorResponse}})
def create_jobs(body: JobsCreateRequest, request: Request):
    from pathlib import Path
    from local_bridge.domain.models import build_jobs

    store: JobStore | None = getattr(request.app.state, "store", None)
    raw_paths = body.caseFiles or body.tasks or []
    if not isinstance(raw_paths, list):
        raise HTTPException(status_code=400, detail="caseFiles must be an array")

    try:
        case_paths = [Path(str(item)).resolve() for item in raw_paths]
        for p in case_paths:
            if not p.exists():
                raise HTTPException(status_code=400, detail=f"File not found: {p}")
            if p.suffix.lower() != ".md":
                raise HTTPException(status_code=400, detail=f"Only Markdown task files are supported: {p}")

        if store is None:
            output_root = Path("runs")
            output_root.mkdir(parents=True, exist_ok=True)
            existing_jobs = build_jobs(case_paths, output_root.resolve())
            store = JobStore(jobs=existing_jobs, output_root=output_root.resolve())
            request.app.state.store = store

        jobs = store.add_jobs(case_paths)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))

    return JobCreatedResponse(
        ok=True,
        jobs=[
            {"id": j.id, "caseFile": str(j.case_file), "mediaAi": j.media_ai}
            for j in jobs
        ],
    )