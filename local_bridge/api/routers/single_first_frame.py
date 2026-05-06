from fastapi import APIRouter, HTTPException, Request
from local_bridge.api.schemas import (
    FirstFrameImageCreateRequest,
    SingleJobCreatedResponse,
)
from local_bridge.infrastructure.media_ai_client import MediaAIClient, _scene_key, _scene_name
from loguru import logger

router = APIRouter(tags=["single"])


def _build_job_id(style_image_id: str, scene_id: str, product_name: str, scene_name: str) -> str:
    """Build a job_id matching the submit_media_ai_first_frame_images.py convention."""
    from local_bridge.infrastructure.media_ai_client import slugify
    return f"{slugify(product_name)}-{style_image_id[:8]}__style-{style_image_id}__scene-{slugify(scene_name)}-{scene_id[:8]}"


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

    style_image_id_str = str(style_image_id)
    scene_id_str = str(scene_id)

    # Fetch metadata for job_id computation
    style_image = client.fetch_style_image(style_image_id_str)
    if not style_image:
        raise HTTPException(status_code=404, detail=f"style image {style_image_id} not found")
    product_name = str(style_image.get("productName") or style_image.get("productId") or style_image_id_str)

    scene = client.fetch_scene(scene_id_str)
    if not scene:
        raise HTTPException(status_code=404, detail=f"scene {scene_id} not found")
    scene_name = _scene_name(scene) or scene_id_str

    job_id = _build_job_id(style_image_id_str, scene_id_str, product_name, scene_name)

    prompt_path = Path("D:/Code/media/gpt_image2/prompts/05_首帧图.md")
    prompt = prompt_path.read_text(encoding="utf-8").strip() if prompt_path.exists() else ""

    store = request.app.state.store
    output_root = store.output_root / job_id

    try:
        case_path, status = client.build_first_frame_task(
            style_image_id=style_image_id_str,
            scene_id=scene_id_str,
            output_root=output_root,
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

    jobs = store.add_jobs([case_path])
    job = jobs[0]
    return SingleJobCreatedResponse(
        ok=True,
        job={"id": job.id, "caseFile": str(job.case_file), "mediaAi": public_media_ai(job.media_ai)},
    )