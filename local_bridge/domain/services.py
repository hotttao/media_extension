"""Domain services — HTTP upload/save, migrated from server.py and media_ai_client.py."""
from __future__ import annotations

import json
import mimetypes
import pathlib
import re
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from loguru import logger

from local_bridge.domain.models import ensure_text, sha256_bytes, write_json


def request_json(method: str, url: str, *, cookie: str | None, body: dict[str, Any] | None = None, timeout: int = 120) -> Any:
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    if cookie:
        headers["Cookie"] = cookie
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed with HTTP {error.code}: {raw}") from error
    except URLError as error:
        raise RuntimeError(f"{method} {url} failed: {error.reason}") from error


def guess_mime_type(path: pathlib.Path) -> str:
    mime_type, _ = mimetypes.guess_type(path.name)
    return mime_type or "application/octet-stream"


def extension_from_url(url: str, fallback: str = ".png") -> str:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    suffix = pathlib.Path(parsed.path).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
        return suffix
    mime_type, _ = mimetypes.guess_type(parsed.path)
    if mime_type == "image/jpeg":
        return ".jpg"
    if mime_type == "image/webp":
        return ".webp"
    return fallback


def resolve_media_url(base_url: str, value: str) -> str:
    from urllib.parse import urljoin
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return urljoin(base_url.rstrip("/") + "/", value.lstrip("/"))


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff_-]+", "-", value).strip("-")
    return cleaned or "product"


def upload_file_multipart(url: str, *, cookie: str | None, file_path: pathlib.Path, sub_dir: str, timeout: int = 120) -> dict[str, Any]:
    boundary = f"----codex-{uuid.uuid4().hex}"
    file_bytes = file_path.read_bytes()
    mime_type = guess_mime_type(file_path)
    fields = [
        (f"--{boundary}\r\nContent-Disposition: form-data; name=\"subDir\"\r\n\r\n{sub_dir}\r\n").encode("utf-8"),
        (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{file_path.name}\"\r\nContent-Type: {mime_type}\r\n\r\n").encode("utf-8"),
        file_bytes,
        f"\r\n--{boundary}--\r\n".encode("utf-8"),
    ]
    body = b"".join(fields)
    headers = {
        "Accept": "application/json",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }
    if cookie:
        headers["Cookie"] = cookie
    request = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"POST {url} failed with HTTP {error.code}: {raw}") from error
    except URLError as error:
        raise RuntimeError(f"POST {url} failed: {error.reason}") from error




def save_media_ai_first_frame_upload(
    job, output_path: pathlib.Path, ip_id: str, style_image_id: str | None, *, base_url: str, cookie: str | None
) -> dict[str, Any]:
    """Upload and save a first-frame image via multipart (Jimeng path)."""
    boundary = f"----codex-{uuid.uuid4().hex}"
    file_bytes = output_path.read_bytes()
    mime_type = guess_mime_type(output_path)
    fields = [
        (f"--{boundary}\r\nContent-Disposition: form-data; name=\"ipId\"\r\n\r\n{ip_id}\r\n").encode("utf-8"),
        (f"--{boundary}\r\nContent-Disposition: form-data; name=\"generationPath\"\r\n\r\njimeng\r\n").encode("utf-8"),
    ]
    if style_image_id:
        fields.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"styleImageId\"\r\n\r\n{style_image_id}\r\n").encode("utf-8"))
    fields.extend([
        (f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"{output_path.name}\"\r\nContent-Type: {mime_type}\r\n\r\n").encode("utf-8"),
        file_bytes,
        f"\r\n--{boundary}--\r\n".encode("utf-8"),
    ])
    body = b"".join(fields)
    headers = {
        "Accept": "application/json",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }
    if cookie:
        headers["Cookie"] = cookie
    save_url = f"{base_url}/api/products/{job.media_ai.get('productId')}/first-frame-upload"
    logger.info("[first-frame-upload] POST {url} ipId={ipId} file={file}", url=save_url, ipId=ip_id, file=output_path.name)
    request = Request(save_url, data=body, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
            result = json.loads(raw) if raw else {}
            logger.info("[first-frame-upload] OK result={result}", result=result)
            return result
    except HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"POST {save_url} failed with HTTP {error.code}: {raw}") from error
    except URLError as error:
        raise RuntimeError(f"POST {save_url} failed: {error.reason}") from error


def save_media_ai_first_frame_upload_batch(
    job, output_paths: list[pathlib.Path], ip_id: str, style_image_id: str | None, *, base_url: str, cookie: str | None
) -> dict[str, Any]:
    """Upload and save multiple first-frame images in a single multipart request (Jimeng batch path)."""
    if not output_paths:
        raise RuntimeError("No files provided for batch upload")
    boundary = f"----codex-{uuid.uuid4().hex}"
    fields: list[bytes] = [
        (f"--{boundary}\r\nContent-Disposition: form-data; name=\"ipId\"\r\n\r\n{ip_id}\r\n").encode("utf-8"),
        (f"--{boundary}\r\nContent-Disposition: form-data; name=\"generationPath\"\r\n\r\njimeng\r\n").encode("utf-8"),
    ]
    if style_image_id:
        fields.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"styleImageId\"\r\n\r\n{style_image_id}\r\n").encode("utf-8"))
    for output_path in output_paths:
        file_bytes = output_path.read_bytes()
        mime_type = guess_mime_type(output_path)
        fields.extend([
            f"--{boundary}\r\n".encode("utf-8"),
            (f"Content-Disposition: form-data; name=\"files\"; filename=\"{output_path.name}\"\r\nContent-Type: {mime_type}\r\n\r\n").encode("utf-8"),
            file_bytes,
            b"\r\n",
        ])
    fields.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(fields)
    headers = {
        "Accept": "application/json",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }
    if cookie:
        headers["Cookie"] = cookie
    save_url = f"{base_url}/api/products/{job.media_ai.get('productId')}/first-frame-upload"
    file_names = ", ".join(p.name for p in output_paths)
    logger.info("[first-frame-upload:batch] POST {url} ipId={ipId} files={files}", url=save_url, ipId=ip_id, files=file_names)
    request = Request(save_url, data=body, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
            result = json.loads(raw) if raw else {}
            logger.info("[first-frame-upload:batch] OK result={result}", result=result)
            return result
    except HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"POST {save_url} failed with HTTP {error.code}: {raw}") from error
    except URLError as error:
        raise RuntimeError(f"POST {save_url} failed: {error.reason}") from error




def save_media_ai_generated_image(job, output_path: pathlib.Path) -> dict[str, Any] | None:
    """Upload and save a generated image to Media AI."""
    if not job.media_ai:
        return None
    job.output_dir.mkdir(parents=True, exist_ok=True)
    base_url = ensure_text(job.media_ai.get("baseUrl") or "http://localhost:3000").rstrip("/")
    cookie = ensure_text(job.media_ai.get("cookie") or "").strip() or None
    kind = ensure_text(job.media_ai.get("kind") or "model-image")
    product_id = ensure_text(job.media_ai.get("productId") or "")
    sub_dir = ensure_text(job.media_ai.get("uploadSubDir") or f"{kind}s")
    if not product_id:
        raise RuntimeError("Media AI sidecar requires productId.")

    upload_url = f"{base_url}/api/upload"
    logger.info("[upload] POST {url} sub_dir={sub_dir} file={file}", url=upload_url, sub_dir=sub_dir, file=output_path.name)
    upload_result = upload_file_multipart(upload_url, cookie=cookie, file_path=output_path, sub_dir=sub_dir)
    image_url = ensure_text(upload_result.get("url") or "")
    if not image_url:
        logger.error("[upload] response missing url: {result}", result=upload_result)
        raise RuntimeError(f"Media AI upload response did not include url: {upload_result}")
    logger.info("[upload] OK url={url}", url=image_url)

    if kind == "style-image":
        model_image_id = ensure_text(job.media_ai.get("modelImageId") or "")
        if not model_image_id:
            raise RuntimeError("style-image sidecar requires modelImageId.")
        save_body = {
            "modelImageId": model_image_id,
            "poseId": job.media_ai.get("poseId"),
            "makeupId": job.media_ai.get("makeupId"),
            "accessoryId": job.media_ai.get("accessoryId"),
            "imageUrl": image_url,
        }
        save_url = f"{base_url}/api/products/{product_id}/style-image/save"
    elif kind == "first-frame-image":
        if job.media_ai.get("platform") == "jimeng":
            # Jimeng first-frame: multipart upload directly to /first-frame-upload
            ip_id = ensure_text(job.media_ai.get("ipId") or "")
            if not ip_id:
                raise RuntimeError("jimeng first-frame requires ipId.")
            style_image_id = ensure_text(job.media_ai.get("styleImageId") or None)
            save_payload_file = job.output_dir / "media-ai-save.json"
            write_json(save_payload_file, {
                "kind": kind,
                "platform": "jimeng",
                "save_url": f"{base_url}/api/products/{product_id}/first-frame-upload",
                "save_body": {"ipId": ip_id, "generationPath": "jimeng", "styleImageId": style_image_id},
                "output_path": str(output_path),
                "image_url": image_url,
            })
            saved = save_media_ai_first_frame_upload(job, output_path, ip_id, style_image_id, base_url=base_url, cookie=cookie)
            return {"kind": kind, "uploaded": {}, "saved": saved}
        else:
            # GPT first-frame: styleImageId-based save via JSON
            style_image_id = ensure_text(job.media_ai.get("styleImageId") or "")
            if not style_image_id:
                raise RuntimeError("first-frame sidecar requires styleImageId.")
            save_body = {
                "styleImageId": style_image_id,
                "sceneId": job.media_ai.get("sceneId"),
                "composition": job.media_ai.get("composition"),
                "imageUrl": image_url,
                "generationPath": "gpt",
            }
            save_url = f"{base_url}/api/products/{product_id}/first-frame"
    else:
        ip_id = ensure_text(job.media_ai.get("ipId") or "")
        if not ip_id:
            raise RuntimeError("model-image sidecar requires ipId.")
        save_body = {"ipId": ip_id, "imageUrl": image_url}
        save_url = f"{base_url}/api/products/{product_id}/model-image/save"

    save_payload_file = job.output_dir / "media-ai-save.json"
    write_json(save_payload_file, {
        "kind": kind,
        "save_url": save_url,
        "save_body": save_body,
        "output_path": str(output_path),
        "image_url": image_url,
    })
    logger.info("[save] POST {url} body={body}", url=save_url, body=save_body)
    save_result = request_json("POST", save_url, cookie=cookie, body=save_body)
    logger.info("[save] OK result={result}", result=save_result)
    return {"kind": kind, "uploaded": upload_result, "saved": save_result}


def save_media_ai_generated_images_batch(job, output_paths: list[pathlib.Path]) -> dict[str, Any] | None:
    """Upload and save multiple generated images to Media AI in a single batch.

    Jimeng first-frame path: each file is uploaded individually to /api/upload,
    then all files are saved together via one multipart /first-frame-upload call.
    """
    if not job.media_ai:
        return None
    if not output_paths:
        return None
    job.output_dir.mkdir(parents=True, exist_ok=True)
    base_url = ensure_text(job.media_ai.get("baseUrl") or "http://localhost:3000").rstrip("/")
    cookie = ensure_text(job.media_ai.get("cookie") or "").strip() or None
    kind = ensure_text(job.media_ai.get("kind") or "model-image")
    product_id = ensure_text(job.media_ai.get("productId") or "")
    sub_dir = ensure_text(job.media_ai.get("uploadSubDir") or f"{kind}s")
    if not product_id:
        raise RuntimeError("Media AI sidecar requires productId.")

    # Only Jimeng first-frame-image supports batch multipart save
    if kind == "first-frame-image" and job.media_ai.get("platform") == "jimeng":
        ip_id = ensure_text(job.media_ai.get("ipId") or "")
        if not ip_id:
            raise RuntimeError("jimeng first-frame requires ipId.")
        style_image_id = ensure_text(job.media_ai.get("styleImageId") or None)

        # Upload each file individually to /api/upload
        upload_url = f"{base_url}/api/upload"
        image_urls = []
        for path in output_paths:
            logger.info("[upload] POST {url} sub_dir={sub_dir} file={file}", url=upload_url, sub_dir=sub_dir, file=path.name)
            result = upload_file_multipart(upload_url, cookie=cookie, file_path=path, sub_dir=sub_dir)
            url = ensure_text(result.get("url") or "")
            if not url:
                raise RuntimeError(f"Media AI upload response did not include url: {result}")
            image_urls.append(url)
            logger.info("[upload] OK url={url}", url=url)

        # Batch save all images via one multipart /first-frame-upload with all files
        saved = save_media_ai_first_frame_upload_batch(job, output_paths, ip_id, style_image_id, base_url=base_url, cookie=cookie)

        # Write complete save record with all files
        save_payload_file = job.output_dir / "media-ai-save.json"
        write_json(save_payload_file, {
            "kind": kind,
            "platform": "jimeng",
            "save_url": f"{base_url}/api/products/{product_id}/first-frame-upload",
            "save_body": {"ipId": ip_id, "generationPath": "jimeng", "styleImageId": style_image_id},
            "output_paths": [str(p) for p in output_paths],
            "image_urls": image_urls,
            "saved": saved,
        })
        return {"kind": kind, "uploaded": {"urls": image_urls}, "saved": saved}

    # Fallback: other kinds or non-jimeng — process individually
    results = []
    for output_path in output_paths:
        result = save_media_ai_generated_image(job, output_path)
        if result:
            results.append(result)
    return results[0] if results else None


def save_media_ai_generated_video(job, output_path: pathlib.Path) -> dict[str, Any] | None:
    """Upload and save a generated video to Media AI."""
    if not job.media_ai:
        return None
    job.output_dir.mkdir(parents=True, exist_ok=True)
    base_url = ensure_text(job.media_ai.get("baseUrl") or "http://localhost:3000").rstrip("/")
    cookie = ensure_text(job.media_ai.get("cookie") or "").strip() or None
    product_id = ensure_text(job.media_ai.get("productId") or "")
    if not product_id:
        raise RuntimeError("Media AI video sidecar requires productId.")

    upload_result = upload_file_multipart(
        f"{base_url}/api/upload", cookie=cookie, file_path=output_path, sub_dir="videos"
    )
    video_url = ensure_text(upload_result.get("url") or "")
    if not video_url:
        raise RuntimeError(f"Media AI upload response did not include url: {upload_result}")

    ip_id = ensure_text(job.media_ai.get("ipId") or "") or None
    first_frame_id = ensure_text(job.media_ai.get("firstFrameId") or "") or None
    movement = ensure_text(job.media_ai.get("movement") or "") or None

    save_body: dict[str, Any] = {"url": video_url}
    if ip_id:
        save_body["ipId"] = ip_id
    if first_frame_id:
        save_body["firstFrameId"] = first_frame_id
    if movement:
        save_body["movement"] = movement

    save_url = f"{base_url}/api/products/{product_id}/videos"
    save_payload_file = job.output_dir / "media-ai-save.json"
    write_json(save_payload_file, {
        "kind": "video",
        "save_url": save_url,
        "save_body": save_body,
        "output_path": str(output_path),
        "video_url": video_url,
    })
    save_result = request_json("POST", save_url, cookie=cookie, body=save_body)
    return {"kind": "video", "uploaded": upload_result, "saved": save_result}
