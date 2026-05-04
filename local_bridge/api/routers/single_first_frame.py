from fastapi import APIRouter, HTTPException, Request
from local_bridge.api.schemas import (
    FirstFrameImageCreateRequest,
    SingleJobCreatedResponse,
)
from loguru import logger

router = APIRouter(tags=["single"])


@router.post("/single/first-frame-image", response_model=SingleJobCreatedResponse, responses={400: {"model": dict}, 404: {"model": dict}})
def create_first_frame_image(body: FirstFrameImageCreateRequest, request: Request):
    from pathlib import Path
    from local_bridge.domain.models import load_media_ai_sidecar, public_media_ai
    from local_bridge.infrastructure.media_ai_client import MediaAIClient

    client: MediaAIClient = request.app.state.media_ai_client
    cookie_header = request.headers.get("Cookie")
    client.resolve_cookie(cookie_header)

    style_image_id = body.styleImageId
    scene_id = body.sceneId
    force = body.force

    if not style_image_id or not scene_id:
        raise HTTPException(status_code=400, detail="styleImageId and sceneId are required")

    prompt_path = Path("D:/Code/media/gpt_image2/prompts/05_首帧图.md")
    prompt = prompt_path.read_text(encoding="utf-8").strip() if prompt_path.exists() else ""

    try:
        case_path, status = client.build_first_frame_task(
            style_image_id=str(style_image_id),
            scene_id=str(scene_id),
            output_root=Path("runs"),
            prompt=prompt,
            force=force,
        )
    except Exception:
        logger.exception("[first-frame] exception")
        raise HTTPException(status_code=500, detail="internal error")

    if status == "exists":
        raise HTTPException(status_code=409, detail="first frame already exists for this style image/scene pair")
    if case_path is None:
        logger.error("[first-frame] build failed status={status}", status=status)
        raise HTTPException(status_code=500, detail=f"task build failed: {status}")

    dry_run = "dry-run" in request.query_params or "dry_run" in request.query_params
    if dry_run:
        return SingleJobCreatedResponse(
            ok=True,
            dryRun=True,
            caseFile=str(case_path),
            mediaAi=public_media_ai(load_media_ai_sidecar(case_path)),
            message="Dry-run: task built but not enqueued",
        )

    store = request.app.state.store
    jobs = store.add_jobs([case_path])
    job = jobs[0]
    return SingleJobCreatedResponse(
        ok=True,
        job={"id": job.id, "caseFile": str(job.case_file), "mediaAi": public_media_ai(job.media_ai)},
    )