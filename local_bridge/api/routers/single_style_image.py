"""Router for POST /v1/single/style-image."""
from fastapi import APIRouter, HTTPException, Request
from local_bridge.api.schemas import (
    StyleImageCreateRequest,
    SingleJobCreatedResponse,
)

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

    prompt_path = Path("D:/Code/media/gpt_image2/prompts/04_定妆图.md")
    prompt = prompt_path.read_text(encoding="utf-8").strip() if prompt_path.exists() else ""

    try:
        case_path, status = client.build_style_image_task(
            model_image_id=str(model_image_id),
            pose_id=str(pose_id),
            output_root=Path("runs"),
            prompt=prompt,
            force=force,
        )
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))

    if status == "exists":
        raise HTTPException(status_code=409, detail="style image already exists for this model image/pose pair")
    if case_path is None:
        raise HTTPException(status_code=500, detail="task build failed")

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