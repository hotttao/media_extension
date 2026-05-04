"""Router for /v1/assets/{job_id}/{index} — serve job asset files."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from local_bridge.infrastructure.persistence import JobStore

router = APIRouter(tags=["assets"])


@router.get("/assets/{job_id}/{index}")
async def serve_asset(job_id: str, index: int, request: Request):
    store: JobStore | None = getattr(request.app.state, "store", None)
    if store is None:
        raise HTTPException(status_code=404, detail="store_not_initialized")

    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job_not_found")

    if index < 0 or index >= len(job.assets):
        raise HTTPException(status_code=404, detail="asset_not_found")

    import pathlib
    asset = job.assets[index]
    file_path: pathlib.Path = asset["path"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="asset_file_not_found")

    content = file_path.read_bytes()
    mime_type = asset.get("mimeType", "application/octet-stream")
    return Response(content=content, media_type=mime_type)