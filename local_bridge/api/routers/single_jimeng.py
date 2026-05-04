"""Routers for /v1/single/jimeng-image and /v1/single/jimeng-video."""
from fastapi import APIRouter, HTTPException, Request
from local_bridge.api.schemas import (
    JimengImageCreateRequest,
    JimengVideoCreateRequest,
    SingleJobCreatedResponse,
)
from local_bridge.domain.services import resolve_media_url, extension_from_url, slugify

router = APIRouter(prefix="/v1", tags=["single"])

MEDIA_AI_BASE_URL = "http://localhost:3000"


def _is_dry_run(request: Request) -> bool:
    return "dry-run" in request.query_params or "dry_run" in request.query_params


@router.post("/single/jimeng-image", response_model=SingleJobCreatedResponse, responses={400: {"model": dict}, 404: {"model": dict}})
def create_jimeng_image(body: JimengImageCreateRequest, request: Request):
    from pathlib import Path
    import json
    from local_bridge.domain.models import load_media_ai_sidecar, public_media_ai
    from local_bridge.infrastructure.media_ai_client import MediaAIClient
    from local_bridge.infrastructure.media_ai_client import _scene_key, _scene_name, _scene_url

    client: MediaAIClient = request.app.state.media_ai_client
    cookie = client.resolve_cookie(request.headers.get("Cookie"))

    style_image_id = body.styleImageId
    if not style_image_id:
        raise HTTPException(status_code=400, detail="styleImageId is required")

    style_image = client.fetch_style_image(str(style_image_id))
    if not style_image:
        raise HTTPException(status_code=404, detail=f"style image {style_image_id} not found")

    resolved_product_id = str(style_image.get("productId") or "") or (body.productId and str(body.productId))
    resolved_ip_id = str(style_image.get("ipId") or "") or (body.ipId and str(body.ipId))
    if not resolved_product_id or not resolved_ip_id:
        raise HTTPException(status_code=400, detail="style image has no productId or ipId")

    resolved_scene_id = body.sceneId and str(body.sceneId)
    resolved_scene_name = ""
    resolved_scene_url = ""
    if resolved_scene_id:
        scene = client.fetch_scene(resolved_scene_id)
        if scene:
            resolved_scene_id = _scene_key(scene)
            resolved_scene_name = _scene_name(scene)
            resolved_scene_url = _scene_url(scene)

    ip = client.fetch_ip(resolved_ip_id)
    if not ip:
        raise HTTPException(status_code=404, detail=f"IP {resolved_ip_id} not found")
    ip_full_body_url = ip.get("fullBodyUrl")
    if not ip_full_body_url:
        raise HTTPException(status_code=400, detail=f"IP {resolved_ip_id} has no fullBodyUrl")

    product = client.fetch_product(resolved_product_id)
    if not product:
        raise HTTPException(status_code=404, detail=f"product {resolved_product_id} not found")
    product_name = str(product.get("name") or resolved_product_id)
    images = product.get("images") or []
    if not isinstance(images, list) or not images:
        raise HTTPException(status_code=400, detail=f"product {resolved_product_id} has no images")
    image_items = [item for item in images if isinstance(item, dict) and item.get("url")]
    if not image_items:
        raise HTTPException(status_code=400, detail=f"product {resolved_product_id} has no valid image URLs")
    main_image = next((item for item in image_items if item.get("isMain") is True), None)
    if main_image is None:
        main_image = sorted(image_items, key=lambda x: int(x.get("order") or 999999))[0]
    main_image_url = str(main_image.get("url") or "")

    task_dir = request.app.state.store.output_root / (
        f"jimeng-img-{slugify(product_name)}-{resolved_product_id[:8]}__"
        f"style-{style_image_id[:8]}__scene-{slugify(resolved_scene_name)}-{resolved_scene_id[:8] if resolved_scene_id else 'none'}"
    )
    assets_dir = task_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    ip_media_url = resolve_media_url(client.media_base_url, str(ip_full_body_url))
    main_media_url = resolve_media_url(client.media_base_url, main_image_url)
    scene_media_url = resolve_media_url(client.media_base_url, resolved_scene_url) if resolved_scene_url else ""

    ip_path = assets_dir / f"ip-full-body{extension_from_url(ip_media_url)}"
    main_path = assets_dir / f"product-main{extension_from_url(main_media_url)}"
    scene_path = assets_dir / f"scene-reference{extension_from_url(scene_media_url)}"

    try:
        client.download_file(ip_media_url, ip_path, cookie=cookie)
        client.download_file(main_media_url, main_path, cookie=cookie)
        if scene_media_url:
            client.download_file(scene_media_url, scene_path, cookie=cookie)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"download failed: {e}")

    if body.prompt:
        prompt_text = body.prompt
    else:
        prompt_path = Path("D:/Code/media/gpt_image2/prompts/08_即梦文生图")
        prompt_text = prompt_path.read_text(encoding="utf-8").strip() if prompt_path.exists() else ""

    case_path = task_dir / "task.md"
    lines = [
        f"# {product_name} / jimeng / {resolved_scene_name} 即梦生图",
        "",
        f"[图片一：人物]({ip_path.relative_to(task_dir).as_posix()})",
        f"[图片二：服装]({main_path.relative_to(task_dir).as_posix()})",
    ]
    if scene_media_url:
        lines.append(f"[图片三：场景]({scene_path.relative_to(task_dir).as_posix()})")
    lines.extend(["", prompt_text, ""])
    case_path.write_text("\n".join(lines), encoding="utf-8")

    sidecar: dict = {
        "kind": "jimeng-image",
        "baseUrl": client.base_url,
        "productId": resolved_product_id,
        "productName": product_name,
        "ipId": resolved_ip_id,
        "styleImageId": style_image_id,
        "styleImageUrl": ip_media_url,
        "uploadSubDir": "first-frames",
    }
    if resolved_scene_id:
        sidecar["sceneId"] = resolved_scene_id
    if resolved_scene_name:
        sidecar["sceneName"] = resolved_scene_name
    if resolved_scene_url:
        sidecar["sceneUrl"] = resolved_scene_url
    if cookie and not body.noEmbedCookie:
        sidecar["cookie"] = cookie
    case_path.with_suffix(".media-ai.json").write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")

    dry_run = _is_dry_run(request)
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


@router.post("/single/jimeng-video", response_model=SingleJobCreatedResponse, responses={400: {"model": dict}})
def create_jimeng_video(body: JimengVideoCreateRequest, request: Request):
    from pathlib import Path
    import json
    from local_bridge.domain.models import load_media_ai_sidecar, public_media_ai
    from local_bridge.infrastructure.media_ai_client import MediaAIClient

    client: MediaAIClient = request.app.state.media_ai_client
    cookie = client.resolve_cookie(request.headers.get("Cookie"))

    product_id = body.productId
    if not product_id:
        raise HTTPException(status_code=400, detail="productId is required")

    resolved_product_id = str(product_id)
    resolved_ip_id = str(body.ipId) if body.ipId else None
    resolved_first_frame_id = str(body.firstFrameId) if body.firstFrameId else None

    first_frame_url = ""
    first_frame_path = None
    if resolved_first_frame_id:
        first_frame = client.fetch_first_frame(resolved_first_frame_id)
        if first_frame:
            first_frame_url = str(first_frame.get("url") or "")

    task_dir = request.app.state.store.output_root / (
        f"jimeng-vid-{resolved_product_id[:8]}"
        f"{f'-ip-{resolved_ip_id[:8]}' if resolved_ip_id else ''}"
        f"{f'-ff-{resolved_first_frame_id[:8]}' if resolved_first_frame_id else ''}"
    )
    assets_dir = task_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    if first_frame_url:
        first_frame_media_url = resolve_media_url(client.media_base_url, first_frame_url)
        first_frame_path = assets_dir / f"first-frame{extension_from_url(first_frame_media_url)}"
        try:
            client.download_file(first_frame_media_url, first_frame_path, cookie=cookie)
        except Exception:
            pass

    if body.prompt:
        prompt_text = body.prompt
    else:
        prompt_path = Path("D:/Code/media/gpt_image2/prompts/09_即梦文生视频")
        prompt_text = prompt_path.read_text(encoding="utf-8").strip() if prompt_path.exists() else ""

    case_path = task_dir / "task.md"
    lines = [f"# jimeng video / product {resolved_product_id}"]
    if first_frame_path and first_frame_path.exists():
        lines.extend(["", f"[首帧图]({first_frame_path.relative_to(task_dir).as_posix()})", ""])
    lines.extend(["", prompt_text, ""])
    case_path.write_text("\n".join(lines), encoding="utf-8")

    sidecar: dict = {
        "kind": "jimeng-video",
        "baseUrl": client.base_url,
        "productId": resolved_product_id,
        "uploadSubDir": "videos",
    }
    if resolved_ip_id:
        sidecar["ipId"] = resolved_ip_id
    if resolved_first_frame_id:
        sidecar["firstFrameId"] = resolved_first_frame_id
    if body.movementId:
        sidecar["movementId"] = body.movementId
    if cookie and not body.noEmbedCookie:
        sidecar["cookie"] = cookie
    case_path.with_suffix(".media-ai.json").write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")

    dry_run = _is_dry_run(request)
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