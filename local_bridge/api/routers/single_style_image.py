"""Router for POST /v1/single/style-image."""
from fastapi import APIRouter, HTTPException, Request
from local_bridge.api.schemas import (
    StyleImageCreateRequest,
    SingleJobCreatedResponse,
)
from local_bridge.infrastructure.media_ai_client import MediaAIClient, slugify
from loguru import logger

router = APIRouter(tags=["single"])


@router.post("/single/style-image", response_model=SingleJobCreatedResponse, responses={400: {"model": dict}, 404: {"model": dict}})
def create_style_image(body: StyleImageCreateRequest, request: Request):
    from pathlib import Path
    from local_bridge.domain.models import load_media_ai_sidecar, public_media_ai
    from local_bridge.infrastructure.media_ai_client import MediaAIClient

    client: MediaAIClient = request.app.state.media_ai_client
    cookie_header = request.headers.get("Cookie")
    client.resolve_cookie(cookie_header)

    model_image_id = body.modelImageId
    pose_id = body.poseId
    force = body.force

    if not model_image_id or not pose_id:
        raise HTTPException(status_code=400, detail="modelImageId and poseId are required")

    model_image_id_str = str(model_image_id)
    pose_id_str = str(pose_id)

    # Fetch metadata for job_id computation
    model_image = client.fetch_model_image(model_image_id_str)
    if not model_image:
        raise HTTPException(status_code=404, detail=f"model image {model_image_id} not found")
    product_id = str(model_image.get("productId") or "")
    product_name = str(model_image.get("productName") or product_id)

    pose = client.fetch_pose(pose_id_str)
    if not pose:
        raise HTTPException(status_code=404, detail=f"pose {pose_id} not found")
    pose_name = str(pose.get("name") or pose_id)

    job_id = f"{slugify(product_name)}-{product_id[:8]}__model-{model_image_id_str}__pose-{slugify(pose_name)}-{pose_id_str[:8]}"

    prompt_path = Path("D:/Code/media/gpt_image2/prompts/04_定妆图.md")
    prompt = prompt_path.read_text(encoding="utf-8").strip() if prompt_path.exists() else ""

    store = request.app.state.store
    output_root = store.output_root / job_id

    try:
        case_path, status = client.build_style_image_task(
            model_image_id=model_image_id_str,
            pose_id=pose_id_str,
            output_root=output_root,
            prompt=prompt,
            force=force,
        )
    except Exception:
        logger.exception("[style-image] exception")
        raise HTTPException(status_code=500, detail="internal error")

    if status == "exists":
        raise HTTPException(status_code=409, detail="style image already exists for this model image/pose pair")
    if case_path is None:
        logger.error("[style-image] build failed status={status}", status=status)
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