"""Router for POST /v1/single/model-image."""
from fastapi import APIRouter, HTTPException, Request
from local_bridge.api.schemas import (
    ModelImageCreateRequest,
    SingleJobCreatedResponse,
)
from local_bridge.infrastructure.media_ai_client import MediaAIClient

router = APIRouter(tags=["single"])

MEDIA_AI_BASE_URL = "http://localhost:3000"


@router.post("/single/model-image", response_model=SingleJobCreatedResponse, responses={400: {"model": dict}, 404: {"model": dict}})
def create_model_image(body: ModelImageCreateRequest, request: Request):
    from pathlib import Path
    from local_bridge.domain.models import load_media_ai_sidecar, build_jobs, public_media_ai

    client: MediaAIClient = request.app.state.media_ai_client
    cookie_header = request.headers.get("Cookie")
    client.resolve_cookie(cookie_header)

    model_image_id = body.modelImageId
    product_id = body.productId
    ip_id = body.ipId
    force = body.force

    if not model_image_id and not (product_id and ip_id):
        raise HTTPException(status_code=400, detail="modelImageId or (productId + ipId) is required")

    if model_image_id and not (product_id and ip_id):
        model_image = client.fetch_model_image(str(model_image_id))
        if not model_image:
            raise HTTPException(status_code=404, detail=f"modelImage {model_image_id} not found")
        product_id = model_image.get("productId")
        ip_id = model_image.get("ipId")
        if not product_id or not ip_id:
            raise HTTPException(status_code=400, detail=f"modelImage {model_image_id} has no productId or ipId")

    prompt_path = Path("D:/Code/media/gpt_image2/prompts/03_模特图.md")
    prompt = prompt_path.read_text(encoding="utf-8").strip() if prompt_path.exists() else ""

    try:
        case_path, status = client.build_model_image_task(
            product_id=str(product_id or ""),
            ip_id=str(ip_id or ""),
            output_root=Path("runs"),
            prompt=prompt,
            force=force,
        )
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))

    if status == "exists":
        raise HTTPException(status_code=409, detail="model image already exists for this product/IP pair")
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