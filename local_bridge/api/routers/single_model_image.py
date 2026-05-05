"""Router for POST /v1/single/model-image."""
from fastapi import APIRouter, HTTPException, Request
from local_bridge.api.schemas import (
    ModelImageCreateRequest,
    SingleJobCreatedResponse,
)
from local_bridge.infrastructure.media_ai_client import MediaAIClient, slugify
from loguru import logger

router = APIRouter(tags=["single"])


@router.post("/single/model-image", response_model=SingleJobCreatedResponse, responses={400: {"model": dict}, 404: {"model": dict}})
def create_model_image(body: ModelImageCreateRequest, request: Request):
    from pathlib import Path
    from local_bridge.domain.models import load_media_ai_sidecar, public_media_ai

    client: MediaAIClient = request.app.state.media_ai_client
    cookie_header = request.headers.get("Cookie")
    client.resolve_cookie(cookie_header)

    product_id = body.productId
    ip_id = body.ipId
    model_image_id = body.modelImageId

    if not model_image_id and not (product_id and ip_id):
        raise HTTPException(status_code=400, detail="modelImageId or (productId + ipId) is required")

    # Resolve product/IP from model_image or use provided values
    resolved_product_id = str(product_id) if product_id else ""
    resolved_ip_id = str(ip_id) if ip_id else ""

    if model_image_id:
        model_image = client.fetch_model_image(str(model_image_id))
        if not model_image:
            raise HTTPException(status_code=404, detail=f"modelImage {model_image_id} not found")
        resolved_product_id = str(model_image.get("productId") or "")
        resolved_ip_id = str(model_image.get("ipId") or "")
        if not resolved_product_id or not resolved_ip_id:
            raise HTTPException(status_code=400, detail=f"modelImage {model_image_id} has no productId or ipId")
        model_image_id = str(model_image_id)

    product = client.fetch_product(resolved_product_id)
    if not product:
        raise HTTPException(status_code=404, detail=f"product {resolved_product_id} not found")
    product_name = str(product.get("name") or resolved_product_id)

    ip = client.fetch_ip(resolved_ip_id)
    if not ip:
        raise HTTPException(status_code=404, detail=f"IP {resolved_ip_id} not found")

    job_id = f"{slugify(product_name)}-{resolved_product_id[:8]}__model-{model_image_id}__ip-{resolved_ip_id}"

    prompt_path = Path("D:/Code/media/gpt_image2/prompts/03_模特图.md")
    prompt = prompt_path.read_text(encoding="utf-8").strip() if prompt_path.exists() else ""

    store = request.app.state.store
    output_root = store.output_root / job_id

    try:
        case_path, status = client.build_model_image_task(
            product_id=resolved_product_id,
            ip_id=resolved_ip_id,
            output_root=output_root,
            job_id=job_id,
            prompt=prompt,
            force=force,
        )
    except Exception:
        logger.exception("[model-image] exception")
        raise HTTPException(status_code=500, detail="internal error")

    if status == "exists":
        raise HTTPException(status_code=409, detail="model image already exists for this product/IP pair")
    if case_path is None:
        logger.error("[model-image] build failed status={status}", status=status)
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