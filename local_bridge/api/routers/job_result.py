"""Router for /v1/job/{job_id}/result."""
import base64
from fastapi import APIRouter, HTTPException, Request
from local_bridge.api.schemas import (
    ResultSubmitRequest,
    ResultSubmitResponse,
)
from local_bridge.domain.models import sha256_bytes, write_json
from local_bridge.domain.services import save_media_ai_generated_image, save_media_ai_generated_video

router = APIRouter(tags=["job"])


@router.post("/job/{job_id}/result", response_model=ResultSubmitResponse, responses={404: {"model": dict}})
def submit_result(job_id: str, body: ResultSubmitRequest, request: Request):
    import pathlib
    store = request.app.state.store
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job_not_found")

    job.output_dir.mkdir(parents=True, exist_ok=True)
    (job.output_dir / "prompt.md").write_text(job.prompt, encoding="utf-8")
    if job.progress:
        write_json(job.output_dir / "logs.json", job.progress)

    images = body.images or []
    videos = body.videos or []
    saved_files: list[str] = []
    skipped_files: list[dict] = []
    media_ai_results: list[dict] = []
    asset_hashes = {asset["sha256"] for asset in job.assets}

    # Process images
    for index, image in enumerate(images, start=1):
        base64_data = image.base64Data or ""
        if not base64_data:
            continue
        try:
            binary = base64.b64decode(base64_data)
        except Exception:
            continue
        image_hash = sha256_bytes(binary)
        if image_hash in asset_hashes:
            skipped_files.append({
                "filename": image.filename or f"result-{index:02d}.png",
                "reason": "matches_input_asset",
                "sha256": image_hash,
                "sourceUrl": image.sourceUrl,
            })
            continue
        original_name = image.filename or f"result-{index:02d}.png"
        suffix = pathlib.Path(original_name).suffix or ".png"
        output_name = f"result-{len(saved_files) + 1:02d}{suffix}"
        output_path = job.output_dir / output_name
        output_path.write_bytes(binary)
        saved_files.append(output_name)
        if job.media_ai:
            try:
                result = save_media_ai_generated_image(job, output_path)
                if result:
                    media_ai_results.append(result)
            except Exception as e:
                media_ai_results.append({"error": str(e)})

    # Process videos
    for index, video in enumerate(videos, start=1):
        base64_data = video.base64Data or ""
        if not base64_data:
            continue
        try:
            binary = base64.b64decode(base64_data)
        except Exception:
            continue
        original_name = video.filename or f"result-{index:02d}.mp4"
        suffix = pathlib.Path(original_name).suffix or ".mp4"
        output_name = f"video-{len(saved_files) + 1:02d}{suffix}"
        output_path = job.output_dir / output_name
        output_path.write_bytes(binary)
        saved_files.append(output_name)
        if job.media_ai:
            try:
                result = save_media_ai_generated_video(job, output_path)
                if result:
                    media_ai_results.append(result)
            except Exception as e:
                media_ai_results.append({"error": str(e)})

    # Write metadata
    write_json(job.output_dir / "metadata.json", {
        "jobId": job.id,
        "caseFile": str(job.case_file),
        "status": "completed",
        "createdAt": job.created_at,
        "claimedAt": job.claimed_at,
        "finishedAt": job.finished_at,
        "savedFiles": saved_files,
        "skippedFiles": skipped_files,
        "mediaAi": job.media_ai,
        "mediaAiResults": media_ai_results,
    })

    media_ai_failed = any("error" in item for item in media_ai_results)
    if saved_files and not media_ai_failed:
        store.mark_completed(job_id)
    else:
        reason = "Media AI save failed" if media_ai_failed else "No generated images found"
        store.mark_failed(job_id, reason)

    return ResultSubmitResponse(
        ok=bool(saved_files),
        savedFiles=saved_files,
        skippedFiles=skipped_files,
        mediaAiResults=media_ai_results,
    )