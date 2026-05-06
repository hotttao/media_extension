from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import mimetypes
import os
import pathlib
import re
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


from local_bridge.media_ai_client import (
    MediaAIClient,
    resolve_media_url,
    extension_from_url,
    slugify,
    _scene_key,
    _scene_name,
    _scene_url,
)
from local_bridge.domain.services import (
    guess_mime_type,
    request_json,
    save_media_ai_generated_image,
    save_media_ai_generated_video,
    upload_file_multipart,
)


MEDIA_AI_BASE_URL = os.environ.get("MEDIA_AI_BASE_URL", "http://localhost:3000")
MEDIA_AI_MEDIA_BASE_URL = os.environ.get("MEDIA_AI_MEDIA_BASE_URL", "http://192.168.2.38")

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


# ---------------------------------------------------------------------------
# Structured Logging (Loguru)
# ---------------------------------------------------------------------------

from loguru import logger as _logger
logger = _logger  # for external imports

_LOG_DIR = pathlib.Path("logs")
_LOG_DIR.mkdir(exist_ok=True)
_LOG_FILE = _LOG_DIR / "server.log"

# Remove default handler, add file + stderr
_logger.remove()
logger_id_file = _logger.add(
    _LOG_FILE,
    format="{time:HH:mm:ss} | {level} | {message}",
    level=os.environ.get("LOG_LEVEL", "DEBUG").upper(),
    rotation="100 MB",
    retention="7 days",
    encoding="utf-8",
    enqueue=True,
    backtrace=True,
    diagnose=True,
)
logger_id_console = _logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | <level>{message}</level>",
    level=os.environ.get("LOG_LEVEL", "DEBUG").upper(),
    colorize=True,
)


def log_info(msg: str, *args: Any, **kwargs: Any) -> None:
    _logger.info(msg, *args, **kwargs)


def log_debug(msg: str, *args: Any, **kwargs: Any) -> None:
    _logger.debug(msg, *args, **kwargs)


def log_error(msg: str, *args: Any, **kwargs: Any) -> None:
    _logger.error(msg, *args, **kwargs)


def log_warning(msg: str, *args: Any, **kwargs: Any) -> None:
    _logger.warning(msg, *args, **kwargs)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_slug(value: str) -> str:
    lowered = value.lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return cleaned or "job"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ensure_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def asset_from_path(path: pathlib.Path, label: str) -> dict[str, Any]:
    return {
        "label": label,
        "path": path,
        "name": path.name,
        "mimeType": guess_mime_type(path),
        "sha256": sha256_bytes(path.read_bytes()),
    }


def replace_image_links(markdown_text: str, case_dir: pathlib.Path) -> tuple[str, list[dict[str, Any]]]:
    assets: list[dict[str, Any]] = []
    seen_paths: set[pathlib.Path] = set()
    asset_positions: dict[pathlib.Path, int] = {}
    link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

    def replacer(match: re.Match[str]) -> str:
        label = match.group(1).strip() or "参考图"
        raw_target = match.group(2).strip()
        target_without_anchor = raw_target.split("#", 1)[0]
        resolved = (case_dir / target_without_anchor).resolve()
        if resolved.suffix.lower() not in IMAGE_SUFFIXES or not resolved.exists():
            return match.group(0)

        if resolved not in seen_paths:
            seen_paths.add(resolved)
            asset_positions[resolved] = len(assets) + 1
            assets.append(asset_from_path(resolved, label))

        asset_index = asset_positions[resolved]
        return f"{label}（见附件{asset_index}）"

    prompt = link_pattern.sub(replacer, markdown_text).strip()
    return prompt, assets


def load_case_file(case_path: pathlib.Path) -> tuple[str, list[dict[str, Any]]]:
    markdown_text = case_path.read_text(encoding="utf-8")
    prompt, assets = replace_image_links(markdown_text, case_path.parent)
    return prompt, assets


def load_video_assets(case_path: pathlib.Path) -> list[dict[str, Any]]:
    assets_dir = case_path.parent / "assets"
    if not assets_dir.exists():
        return []

    assets: list[dict[str, Any]] = []
    for stem, label in (("first-frame", "firstFrame"), ("last-frame", "lastFrame")):
        matches = sorted(
            path for path in assets_dir.iterdir()
            if path.is_file() and path.stem.lower() == stem and path.suffix.lower() in IMAGE_SUFFIXES
        )
        if matches:
            assets.append(asset_from_path(matches[0].resolve(), label))
    return assets


@dataclass
class Job:
    id: str
    case_file: pathlib.Path
    prompt: str
    assets: list[dict[str, Any]]
    output_dir: pathlib.Path
    status: str = "pending"
    created_at: str = field(default_factory=utc_now_iso)
    claimed_at: str | None = None
    finished_at: str | None = None
    failure_reason: str | None = None
    worker_id: str | None = None
    progress: list[dict[str, Any]] = field(default_factory=list)
    media_ai: dict[str, Any] | None = None
    platform: str | None = None
    target_url: str | None = None

    def to_public_dict(self, base_url: str) -> dict[str, Any]:
        result = {
            "id": self.id,
            "caseFile": str(self.case_file),
            "prompt": self.prompt,
            "assets": [
                {
                    "index": index,
                    "label": asset["label"],
                    "name": asset["name"],
                    "mimeType": asset["mimeType"],
                    "url": f"{base_url}/v1/assets/{self.id}/{index}",
                }
                for index, asset in enumerate(self.assets)
            ],
            "timeoutSeconds": 900,
        }
        # Add platform and targetUrl if set on the job
        if self.platform:
            result["platform"] = self.platform
        if self.target_url:
            result["targetUrl"] = self.target_url
        # Add styleImageId and sceneId from media_ai sidecar for job tracking
        if self.media_ai:
            if self.media_ai.get("styleImageId"):
                result["styleImageId"] = self.media_ai["styleImageId"]
            if self.media_ai.get("sceneId"):
                result["sceneId"] = self.media_ai["sceneId"]
        return result


class JobStore:
    def __init__(self, jobs: list[Job], output_root: pathlib.Path):
        self.jobs = jobs
        self.output_root = output_root
        self.lock = threading.Lock()

    def add_jobs(self, case_paths: list[pathlib.Path]) -> list[Job]:
        with self.lock:
            jobs = build_jobs(case_paths, self.output_root, start_index=len(self.jobs) + 1)
            self.jobs.extend(jobs)
            return jobs

    def claim_next_job(self, worker_id: str | None) -> Job | None:
        with self.lock:
            for job in self.jobs:
                if job.status != "pending":
                    continue
                job.status = "running"
                job.claimed_at = utc_now_iso()
                job.worker_id = worker_id
                job.output_dir.mkdir(parents=True, exist_ok=True)
                (job.output_dir / "prompt.md").write_text(job.prompt, encoding="utf-8")
                return job
        return None

    def get_job(self, job_id: str) -> Job | None:
        with self.lock:
            for job in self.jobs:
                if job.id == job_id:
                    return job
        return None

    def mark_completed(self, job_id: str) -> Job:
        with self.lock:
            job = self.get_job_or_raise(job_id)
            job.status = "completed"
            job.finished_at = utc_now_iso()
            return job

    def mark_failed(self, job_id: str, reason: str) -> Job:
        with self.lock:
            job = self.get_job_or_raise(job_id)
            job.status = "failed"
            job.finished_at = utc_now_iso()
            job.failure_reason = reason
            return job

    def requeue(self, job_id: str) -> Job:
        with self.lock:
            job = self.get_job_or_raise(job_id)
            job.status = "pending"
            job.claimed_at = None
            job.finished_at = None
            job.failure_reason = None
            job.worker_id = None
            return job

    def cancel(self, job_id: str) -> Job:
        with self.lock:
            job = self.get_job_or_raise(job_id)
            if job.status == "running":
                raise RuntimeError("Running jobs cannot be canceled from the local bridge.")
            if job.status in {"completed", "failed"}:
                raise RuntimeError(f"Terminal job cannot be canceled: {job.status}")
            job.status = "canceled"
            job.finished_at = utc_now_iso()
            job.failure_reason = "canceled"
            return job

    def cancel_all(self) -> list[Job]:
        with self.lock:
            canceled = []
            for job in self.jobs:
                if job.status == "pending":
                    job.status = "canceled"
                    job.finished_at = utc_now_iso()
                    job.failure_reason = "canceled"
                    canceled.append(job)
            return canceled

    def heartbeat(self, job_id: str) -> Job:
        with self.lock:
            job = self.get_job_or_raise(job_id)
            job.claimed_at = utc_now_iso()
            return job

    def add_progress(self, job_id: str, message: str, at: str | None = None, details: Any | None = None) -> Job:
        with self.lock:
            job = self.get_job_or_raise(job_id)
            event = {
                "at": at or utc_now_iso(),
                "message": message,
            }
            if details is not None:
                event["details"] = details
            job.progress.append(event)
            job.output_dir.mkdir(parents=True, exist_ok=True)
            (job.output_dir / "prompt.md").write_text(job.prompt, encoding="utf-8")
            write_json(job.output_dir / "logs.json", job.progress)
            return job

    def get_job_or_raise(self, job_id: str) -> Job:
        for job in self.jobs:
            if job.id == job_id:
                return job
        raise KeyError(job_id)

    def summary(self) -> dict[str, Any]:
        with self.lock:
            return {
                "jobs": [
                    {
                        "id": job.id,
                        "caseFile": str(job.case_file),
                        "status": job.status,
                        "createdAt": job.created_at,
                        "claimedAt": job.claimed_at,
                        "finishedAt": job.finished_at,
                        "failureReason": job.failure_reason,
                        "outputDir": str(job.output_dir),
                        "latestProgress": job.progress[-1] if job.progress else None,
                        "mediaAi": public_media_ai(job.media_ai),
                    }
                    for job in self.jobs
                ]
            }


def write_json(path: pathlib.Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def public_media_ai(media_ai: dict[str, Any] | None) -> dict[str, Any] | None:
    if media_ai is None:
        return None
    payload = dict(media_ai)
    if "cookie" in payload:
        payload["cookie"] = "<redacted>"
    return payload


def load_media_ai_sidecar(case_path: pathlib.Path) -> dict[str, Any] | None:
    sidecar_path = case_path.with_suffix(".media-ai.json")
    if not sidecar_path.exists():
        return None
    try:
        return json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def build_jobs(case_paths: list[pathlib.Path], output_root: pathlib.Path, start_index: int = 1) -> list[Job]:
    jobs: list[Job] = []
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for index, case_path in enumerate(case_paths, start=start_index):
        prompt, assets = load_case_file(case_path)
        media_ai = load_media_ai_sidecar(case_path)
        job_id = f"{index:03d}-{sanitize_slug(case_path.stem)}-{timestamp}"
        job_output_dir = output_root / job_id

        # Determine platform and targetUrl from media_ai kind
        platform: str | None = None
        target_url: str | None = None
        if media_ai:
            kind = media_ai.get("kind") or ""
            if kind == "video":
                platform = "jimeng"
                target_url = "https://jimeng.jianying.com/ai-tool/home/?type=video&workspace=0"
                if not assets:
                    assets = load_video_assets(case_path)
            elif kind in ("first-frame-image", "style-image", "model-image"):
                platform = media_ai.get("platform") or "gpt"
                if platform == "jimeng":
                    target_url = "https://jimeng.jianying.com/ai-tool/home/?type=image&workspace=0"

        jobs.append(
            Job(
                id=job_id,
                case_file=case_path.resolve(),
                prompt=prompt,
                assets=assets,
                output_dir=job_output_dir,
                media_ai=media_ai,
                platform=platform,
                target_url=target_url,
            )
        )
    return jobs


def parse_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    content_length = int(handler.headers.get("Content-Length", "0"))
    raw_body = handler.rfile.read(content_length) if content_length else b"{}"
    return json.loads(raw_body.decode("utf-8"))


def send_json(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.end_headers()
    handler.wfile.write(body)


class AppServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], handler_class: type[BaseHTTPRequestHandler], store: JobStore):
        super().__init__(server_address, handler_class)
        self.store = store
        self.media_ai_client = MediaAIClient(base_url=MEDIA_AI_BASE_URL, media_base_url=MEDIA_AI_MEDIA_BASE_URL)


class RequestHandler(BaseHTTPRequestHandler):
    server: AppServer

    def log_message(self, format: str, *args: Any) -> None:
        log_debug("HTTP %s", format % args)

    def do_OPTIONS(self) -> None:
        send_json(self, HTTPStatus.NO_CONTENT, {})

    def _is_dry_run(self) -> bool:
        parsed = urlparse(self.path)
        qs = parsed.query
        return "dry-run" in qs or "dry_run" in qs

    def _strip_dry_run_query(self, path: str) -> str:
        """Remove dry-run query params before routing."""
        parsed = urlparse(path)
        qs = [p for p in parsed.query.split("&") if p and not p.startswith("dry-") and not p.startswith("dry_")]
        return str(urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, "&".join(qs), parsed.fragment)))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/health":
            send_json(self, HTTPStatus.OK, {"ok": True, "now": utc_now_iso()})
            return

        if path == "/v1/state":
            send_json(self, HTTPStatus.OK, self.server.store.summary())
            return

        if path == "/v1/job/claim":
            worker_id = self.headers.get("X-Worker-Id")
            host = self.headers.get("Host", "127.0.0.1:8765")
            base_url = f"http://{host}"
            job = self.server.store.claim_next_job(worker_id)
            if job:
                log_info("job claimed job_id=%s worker_id=%s", job.id, worker_id or "unknown")
            send_json(self, HTTPStatus.OK, {"job": job.to_public_dict(base_url) if job else None})
            return

        asset_match = re.fullmatch(r"/v1/assets/([^/]+)/(\d+)", path)
        if asset_match:
            job_id = asset_match.group(1)
            asset_index = int(asset_match.group(2))
            job = self.server.store.get_job(job_id)
            if not job:
                send_json(self, HTTPStatus.NOT_FOUND, {"error": "job_not_found"})
                return
            if asset_index < 0 or asset_index >= len(job.assets):
                send_json(self, HTTPStatus.NOT_FOUND, {"error": "asset_not_found"})
                return
            asset = job.assets[asset_index]
            content = pathlib.Path(asset["path"]).read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", asset["mimeType"])
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(content)
            return

        send_json(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        log_debug("do_POST path=%s", path)

        if path == "/v1/jobs":
            payload = parse_json_body(self)
            raw_paths = payload.get("caseFiles") or payload.get("tasks") or []
            if not isinstance(raw_paths, list):
                send_json(self, HTTPStatus.BAD_REQUEST, {"error": "caseFiles must be an array"})
                return

            try:
                case_paths = resolve_case_paths([ensure_text(item) for item in raw_paths])
                jobs = self.server.store.add_jobs(case_paths)
            except Exception as error:
                send_json(self, HTTPStatus.BAD_REQUEST, {"error": str(error)})
                return

            log_info("enqueued job_count=%d", len(jobs))
            for job in jobs:
                log_info("  job_id=%s case_file=%s", job.id, job.case_file)
            send_json(
                self,
                HTTPStatus.OK,
                {
                    "ok": True,
                    "jobs": [
                        {
                            "id": job.id,
                            "caseFile": str(job.case_file),
                            "mediaAi": public_media_ai(job.media_ai),
                        }
                        for job in jobs
                    ],
                },
            )
            return

        heartbeat_match = re.fullmatch(r"/v1/job/([^/]+)/heartbeat", path)
        if heartbeat_match:
            job_id = heartbeat_match.group(1)
            try:
                job = self.server.store.heartbeat(job_id)
            except KeyError:
                send_json(self, HTTPStatus.NOT_FOUND, {"error": "job_not_found"})
                return
            send_json(self, HTTPStatus.OK, {"ok": True, "jobId": job.id})
            return

        progress_match = re.fullmatch(r"/v1/job/([^/]+)/progress", path)
        if progress_match:
            job_id = progress_match.group(1)
            job = self.server.store.get_job(job_id)
            if not job:
                send_json(self, HTTPStatus.NOT_FOUND, {"error": "job_not_found"})
                return

            payload = parse_json_body(self)
            message = ensure_text(payload.get("message") or "Progress updated")
            at = payload.get("at")
            details = payload.get("details")
            updated_job = self.server.store.add_progress(job_id, message, at=at, details=details)
            log_info("progress job_id=%s message=%s", updated_job.id, message)
            send_json(self, HTTPStatus.OK, {"ok": True})
            return

        result_match = re.fullmatch(r"/v1/job/([^/]+)/result", path)
        if result_match:
            job_id = result_match.group(1)
            log_info("[/result] received job_id=%s", job_id)
            job = self.server.store.get_job(job_id)
            if not job:
                log_warning("[/result] job not found job_id=%s", job_id)
                send_json(self, HTTPStatus.NOT_FOUND, {"error": "job_not_found"})
                return

            log_info("[/result] job found job_id=%s output_dir=%s", job_id, job.output_dir)
            payload = parse_json_body(self)
            log_info("[/result] payload has %s images, %s logs", len(payload.get("images", [])), len(payload.get("logs", [])))
            job.output_dir.mkdir(parents=True, exist_ok=True)
            (job.output_dir / "prompt.md").write_text(job.prompt, encoding="utf-8")
            if job.progress:
                write_json(job.output_dir / "logs.json", job.progress)

            images = payload.get("images", [])
            log_info("[/result] processing %s images", len(images))
            saved_files: list[str] = []
            media_ai_results: list[dict[str, Any]] = []
            skipped_files: list[dict[str, Any]] = []
            asset_hashes = {asset["sha256"] for asset in job.assets}
            for index, image in enumerate(images, start=1):
                base64_data = image.get("base64Data", "")
                log_info("[/result] image %s base64 length=%s filename=%s", index, len(base64_data), image.get("filename"))
                try:
                    binary = base64.b64decode(base64_data)
                    image_hash = sha256_bytes(binary)
                    log_info("[/result] image %s decoded binary size=%s sha256=%s", index, len(binary), image_hash.hex()[:16])
                except Exception as e:
                    log_error("[/result] image %s base64 decode failed: %s", index, e)
                    raise
                if image_hash in asset_hashes:
                    skipped_files.append(
                        {
                            "filename": ensure_text(image.get("filename") or f"result-{index:02d}.png"),
                            "reason": "matches_input_asset",
                            "sha256": image_hash,
                            "sourceUrl": image.get("sourceUrl"),
                        }
                    )
                    log_info("[/result] image %s SKIPPED (matches input asset)", index)
                    continue
                original_name = ensure_text(image.get("filename") or f"result-{index:02d}.png")
                suffix = pathlib.Path(original_name).suffix or ".png"
                output_name = f"result-{len(saved_files) + 1:02d}{suffix}"
                output_path = job.output_dir / output_name
                log_info("[/result] writing image %s bytes to %s", len(binary), output_path)
                output_path.write_bytes(binary)
                saved_files.append(output_name)
                log_info("[/result] image %s saved as %s total=%s", index, output_name, len(saved_files))
                if len(saved_files) == 1 and job.media_ai:
                    try:
                        media_ai_result = save_media_ai_generated_image(job, output_path)
                        if media_ai_result:
                            media_ai_results.append(media_ai_result)
                            log_info("saved generated image to Media AI job_id=%s", job.id)
                    except Exception as error:
                        media_ai_results.append({"error": str(error)})
                        log_error("Media AI save failed job_id=%s error=%s", job.id, error)

            # Handle video results (Jimeng video generation)
            videos = payload.get("videos", [])
            for index, video in enumerate(videos, start=1):
                base64_data = video.get("base64Data", "")
                if not base64_data:
                    continue
                binary = base64.b64decode(base64_data)
                original_name = ensure_text(video.get("filename") or f"result-{index:02d}.mp4")
                suffix = pathlib.Path(original_name).suffix or ".mp4"
                output_name = f"video-{len(saved_files) + 1:02d}{suffix}"
                output_path = job.output_dir / output_name
                output_path.write_bytes(binary)
                saved_files.append(output_name)
                if job.media_ai:
                    try:
                        media_ai_result = save_media_ai_generated_video(job, output_path)
                        if media_ai_result:
                            media_ai_results.append(media_ai_result)
                            log_info("saved generated video to Media AI job_id=%s", job.id)
                    except Exception as error:
                        media_ai_results.append({"error": str(error)})
                        log_error("Media AI video save failed job_id=%s error=%s", job.id, error)

            media_ai_failed = any("error" in item for item in media_ai_results)
            status = "failed" if media_ai_failed else ("completed" if saved_files else "failed")
            finished_at = utc_now_iso()
            metadata = {
                "jobId": job.id,
                "caseFile": str(job.case_file),
                "status": status,
                "createdAt": job.created_at,
                "claimedAt": job.claimed_at,
                "finishedAt": finished_at,
                "savedFiles": saved_files,
                "skippedFiles": skipped_files,
                "mediaAi": public_media_ai(job.media_ai),
                "mediaAiResults": media_ai_results,
                "inputAssets": [
                    {
                        "label": asset["label"],
                        "name": asset["name"],
                        "mimeType": asset["mimeType"],
                        "sha256": asset["sha256"],
                    }
                    for asset in job.assets
                ],
                "images": payload.get("images", []),
                "assistantResponse": payload.get("assistantResponse"),
                "logs": job.progress or payload.get("logs", []),
            }
            write_json(job.output_dir / "metadata.json", metadata)
            if saved_files and not media_ai_failed:
                self.server.store.mark_completed(job_id)
                log_info("[/result] job COMPLETED saved_files=%s", saved_files)
                log_info("[/result] final status=%s saved_files=%s skipped=%s media_ai_failed=%s", status, saved_files, len(skipped_files), media_ai_failed)
            log_info("[/result] sending OK response to client")
            send_json(
                self,
                HTTPStatus.OK,
                {
                    "ok": True,
                    "savedFiles": saved_files,
                    "skippedFiles": skipped_files,
                    "mediaAiResults": media_ai_results,
                },
            )
            return

            reason = (
                f"Media AI save failed: {media_ai_results}"
                if media_ai_failed
                else "Only input assets were detected; no generated images were saved."
            )
            self.server.store.mark_failed(job_id, reason)
            log_error("job failed job_id=%s reason=%s", job.id, reason)
            send_json(
                self,
                HTTPStatus.OK,
                {
                    "ok": False,
                    "savedFiles": saved_files,
                    "skippedFiles": skipped_files,
                    "reason": reason,
                },
            )
            return

        fail_match = re.fullmatch(r"/v1/job/([^/]+)/fail", path)
        if fail_match:
            job_id = fail_match.group(1)
            job = self.server.store.get_job(job_id)
            if not job:
                send_json(self, HTTPStatus.NOT_FOUND, {"error": "job_not_found"})
                return

            payload = parse_json_body(self)
            reason = ensure_text(payload.get("reason") or "Unknown failure")
            job.output_dir.mkdir(parents=True, exist_ok=True)
            (job.output_dir / "prompt.md").write_text(job.prompt, encoding="utf-8")
            if job.progress:
                write_json(job.output_dir / "logs.json", job.progress)
            write_json(
                job.output_dir / "failure.json",
                {
                    "jobId": job.id,
                    "caseFile": str(job.case_file),
                    "status": "failed",
                    "createdAt": job.created_at,
                    "claimedAt": job.claimed_at,
                    "finishedAt": utc_now_iso(),
                    "reason": reason,
                    "logs": job.progress or payload.get("logs", []),
                },
            )
            self.server.store.mark_failed(job_id, reason)
            log_error("job failed job_id=%s reason=%s", job.id, reason)
            send_json(self, HTTPStatus.OK, {"ok": True})
            return

        requeue_match = re.fullmatch(r"/v1/job/([^/]+)/requeue", path)
        if requeue_match:
            job_id = requeue_match.group(1)
            try:
                job = self.server.store.requeue(job_id)
            except KeyError:
                send_json(self, HTTPStatus.NOT_FOUND, {"error": "job_not_found"})
                return
            send_json(self, HTTPStatus.OK, {"ok": True, "jobId": job.id, "status": job.status})
            return

        if path == "/v1/jobs/cancel":
            canceled = self.server.store.cancel_all()
            log_info("canceled %d job(s)", len(canceled))
            send_json(
                self,
                HTTPStatus.OK,
                {
                    "ok": True,
                    "canceled": [
                        {"jobId": job.id, "status": job.status} for job in canceled
                    ],
                },
            )
            return

        cancel_match = re.fullmatch(r"/v1/job/([^/]+)/cancel", path)
        if cancel_match:
            job_id = cancel_match.group(1)
            try:
                job = self.server.store.cancel(job_id)
            except KeyError:
                send_json(self, HTTPStatus.NOT_FOUND, {"error": "job_not_found"})
                return
            except RuntimeError as error:
                send_json(self, HTTPStatus.CONFLICT, {"error": str(error)})
                return
            send_json(self, HTTPStatus.OK, {"ok": True, "jobId": job.id, "status": job.status})
            return

        # ---- Single model-image endpoint ----------------------------------------
        model_image_match = re.fullmatch(r"/v1/single/model-image", path)
        if model_image_match:
            log_info(">>> POST /v1/single/model-image")
            log_debug("media_base_url=%s", self.server.media_ai_client.media_base_url)
            cookie_header = self.headers.get("Cookie")
            client = self.server.media_ai_client
            cookie = client.resolve_cookie(cookie_header)
            log_debug("has_session_token=%s", "session-token" in (cookie or ""))

            payload = parse_json_body(self)
            model_image_id = payload.get("modelImageId")
            product_id = payload.get("productId")
            ip_id = payload.get("ipId")
            force = bool(payload.get("force", False))
            log_info("request modelImageId=%s productId=%s ipId=%s force=%s", model_image_id, product_id, ip_id, force)
            dry_run = self._is_dry_run()
            if dry_run:
                log_info("dry-run: returning job preview without enqueue")

            if not model_image_id and not (product_id and ip_id):
                log_error("missing required params")
                send_json(self, HTTPStatus.BAD_REQUEST, {"error": "modelImageId or (productId + ipId) is required"})
                return

            # If only modelImageId is provided, fetch it to resolve productId and ipId
            if model_image_id and not (product_id and ip_id):
                log_debug("resolving productId/ipId from modelImageId=%s", model_image_id)
                model_image = client.fetch_model_image(str(model_image_id))
                if not model_image:
                    log_error("modelImage not found id=%s", model_image_id)
                    send_json(self, HTTPStatus.NOT_FOUND, {"error": f"modelImage {model_image_id} not found"})
                    return
                product_id = model_image.get("productId")
                ip_id = model_image.get("ipId")
                log_debug("resolved productId=%s ipId=%s", product_id, ip_id)
                if not product_id or not ip_id:
                    log_error("modelImage has no productId or ipId id=%s", model_image_id)
                    send_json(self, HTTPStatus.BAD_REQUEST, {"error": f"modelImage {model_image_id} has no productId or ipId"})
                    return

            prompt_path = pathlib.Path("D:/Code/media/gpt_image2/prompts/03_模特图.md")
            prompt = prompt_path.read_text(encoding="utf-8").strip() if prompt_path.exists() else ""

            log_debug("calling build_model_image_task product_id=%s ip_id=%s force=%s", product_id, ip_id, force)
            try:
                case_path, status = client.build_model_image_task(
                    product_id=str(product_id or ""),
                    ip_id=str(ip_id or ""),
                    output_root=self.server.store.output_root,
                    prompt=prompt,
                    force=force,
                )
                log_debug("build_model_image_task returned case_path=%s status=%s", case_path, status)
            except Exception as error:
                log_error("build failed error=%s", error)
                send_json(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})
                return

            if status == "exists":
                log_info("skipping - model image already exists product_id=%s ip_id=%s", product_id, ip_id)
                send_json(self, HTTPStatus.CONFLICT, {"error": "model image already exists for this product/IP pair"})
                return
            if case_path is None:
                log_error("build returned None case_path=%s status=%s", case_path, status)
                send_json(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "task build failed"})
                return

            try:
                if not dry_run:
                    jobs = self.server.store.add_jobs([case_path])
                    job = jobs[0]
                    log_info("<<< OK %s", json.dumps({
                        "jobId": job.id,
                        "caseFile": str(job.case_file),
                        "prompt": job.prompt,
                        "mediaAi": public_media_ai(job.media_ai),
                    }, ensure_ascii=False))
                    send_json(
                        self,
                        HTTPStatus.OK,
                        {
                            "ok": True,
                            "job": {
                                "id": job.id,
                                "caseFile": str(job.case_file),
                                "mediaAi": public_media_ai(job.media_ai),
                            },
                        },
                    )
                else:
                    log_info("<<< DRY-RUN %s", case_path)
                    send_json(
                        self,
                        HTTPStatus.OK,
                        {
                            "ok": True,
                            "dryRun": True,
                            "caseFile": str(case_path),
                            "mediaAi": public_media_ai(load_media_ai_sidecar(case_path)),
                            "message": "Dry-run: task built but not enqueued",
                        },
                    )
                return
            except Exception as error:
                log_error("enqueue failed error=%s", error)
                send_json(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})
                return

        # ---- Single style-image endpoint ----------------------------------------
        style_image_match = re.fullmatch(r"/v1/single/style-image", path)
        if style_image_match:
            log_info(">>> POST /v1/single/style-image")
            cookie_header = self.headers.get("Cookie")
            client = self.server.media_ai_client
            client.resolve_cookie(cookie_header)

            payload = parse_json_body(self)
            model_image_id = payload.get("modelImageId")
            pose_id = payload.get("poseId")
            force = bool(payload.get("force", False))
            log_info("request modelImageId=%s poseId=%s force=%s", model_image_id, pose_id, force)
            dry_run = self._is_dry_run()
            if dry_run:
                log_info("dry-run: returning job preview without enqueue")

            if not model_image_id or not pose_id:
                log_error("missing required params")
                send_json(self, HTTPStatus.BAD_REQUEST, {"error": "modelImageId and poseId are required"})
                return

            prompt_path = pathlib.Path("D:/Code/media/gpt_image2/prompts/04_定妆图.md")
            prompt = prompt_path.read_text(encoding="utf-8").strip() if prompt_path.exists() else ""

            log_debug("calling build_style_image_task model_image_id=%s pose_id=%s force=%s", model_image_id, pose_id, force)
            try:
                case_path, status = client.build_style_image_task(
                    model_image_id=str(model_image_id),
                    pose_id=str(pose_id),
                    output_root=self.server.store.output_root,
                    prompt=prompt,
                    force=force,
                )
                log_debug("build_style_image_task returned case_path=%s status=%s", case_path, status)
            except Exception as error:
                log_error("build failed error=%s", error)
                send_json(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})
                return

            if status == "exists":
                log_info("skipping - style image already exists modelImageId=%s poseId=%s", model_image_id, pose_id)
                send_json(self, HTTPStatus.CONFLICT, {"error": "style image already exists for this model image/pose pair"})
                return
            if case_path is None:
                log_error("build returned None case_path=%s status=%s", case_path, status)
                send_json(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "task build failed"})
                return

            try:
                if not dry_run:
                    jobs = self.server.store.add_jobs([case_path])
                    job = jobs[0]
                    log_info("<<< OK %s", json.dumps({
                        "jobId": job.id,
                        "caseFile": str(job.case_file),
                        "prompt": job.prompt,
                        "mediaAi": public_media_ai(job.media_ai),
                    }, ensure_ascii=False))
                    send_json(
                        self,
                        HTTPStatus.OK,
                        {
                            "ok": True,
                            "job": {
                                "id": job.id,
                                "caseFile": str(job.case_file),
                                "mediaAi": public_media_ai(job.media_ai),
                            },
                        },
                    )
                else:
                    log_info("<<< DRY-RUN %s", case_path)
                    send_json(
                        self,
                        HTTPStatus.OK,
                        {
                            "ok": True,
                            "dryRun": True,
                            "caseFile": str(case_path),
                            "mediaAi": public_media_ai(load_media_ai_sidecar(case_path)),
                            "message": "Dry-run: task built but not enqueued",
                        },
                    )
                return
            except Exception as error:
                log_error("enqueue failed error=%s", error)
                send_json(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})
                return

        # ---- Single first-frame-image endpoint -----------------------------------
        first_frame_match = re.fullmatch(r"/v1/single/first-frame-image", path)
        if first_frame_match:
            log_info(">>> POST /v1/single/first-frame-image")
            cookie_header = self.headers.get("Cookie")
            client = self.server.media_ai_client
            client.resolve_cookie(cookie_header)

            payload = parse_json_body(self)
            style_image_id = payload.get("styleImageId")
            scene_id = payload.get("sceneId")
            force = bool(payload.get("force", False))
            log_info("request styleImageId=%s sceneId=%s force=%s", style_image_id, scene_id, force)
            dry_run = self._is_dry_run()
            if dry_run:
                log_info("dry-run: returning job preview without enqueue")

            if not style_image_id or not scene_id:
                log_error("missing required params")
                send_json(self, HTTPStatus.BAD_REQUEST, {"error": "styleImageId and sceneId are required"})
                return

            prompt_path = pathlib.Path("D:/Code/media/gpt_image2/prompts/05_首帧图.md")
            prompt = prompt_path.read_text(encoding="utf-8").strip() if prompt_path.exists() else ""

            log_debug("calling build_first_frame_task style_image_id=%s scene_id=%s force=%s", style_image_id, scene_id, force)
            try:
                case_path, status = client.build_first_frame_task(
                    style_image_id=str(style_image_id),
                    scene_id=str(scene_id),
                    output_root=self.server.store.output_root,
                    prompt=prompt,
                    force=force,
                )
                log_debug("build_first_frame_task returned case_path=%s status=%s", case_path, status)
            except Exception as error:
                log_error("build failed error=%s", error)
                send_json(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})
                return

            if status == "exists":
                log_info("skipping - first frame already exists styleImageId=%s sceneId=%s", style_image_id, scene_id)
                send_json(self, HTTPStatus.CONFLICT, {"error": "first frame already exists for this style image/scene pair"})
                return
            if case_path is None:
                log_error("build returned None case_path=%s status=%s", case_path, status)
                send_json(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "task build failed"})
                return

            try:
                if not dry_run:
                    jobs = self.server.store.add_jobs([case_path])
                    job = jobs[0]
                    log_info("<<< OK %s", json.dumps({
                        "jobId": job.id,
                        "caseFile": str(job.case_file),
                        "prompt": job.prompt,
                        "mediaAi": public_media_ai(job.media_ai),
                    }, ensure_ascii=False))
                    send_json(
                        self,
                        HTTPStatus.OK,
                        {
                            "ok": True,
                            "job": {
                                "id": job.id,
                                "caseFile": str(job.case_file),
                                "mediaAi": public_media_ai(job.media_ai),
                            },
                        },
                    )
                else:
                    log_info("<<< DRY-RUN %s", case_path)
                    send_json(
                        self,
                        HTTPStatus.OK,
                        {
                            "ok": True,
                            "dryRun": True,
                            "caseFile": str(case_path),
                            "mediaAi": public_media_ai(load_media_ai_sidecar(case_path)),
                            "message": "Dry-run: task built but not enqueued",
                        },
                    )
                return
            except Exception as error:
                log_error("enqueue failed error=%s", error)
                send_json(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})
                return

        # ---- Single jimeng-image endpoint ------------------------------------
        jimeng_image_match = re.fullmatch(r"/v1/single/jimeng-image", path)
        if jimeng_image_match:
            log_info(">>> POST /v1/single/jimeng-image")
            cookie_header = self.headers.get("Cookie")
            client = self.server.media_ai_client
            cookie = client.resolve_cookie(cookie_header)

            payload = parse_json_body(self)
            style_image_id = payload.get("styleImageId")
            scene_id = payload.get("sceneId")
            product_id = payload.get("productId")
            ip_id = payload.get("ipId")
            force = bool(payload.get("force", False))
            prompt_text = payload.get("prompt", "").strip() or None
            log_info("request styleImageId=%s sceneId=%s productId=%s ipId=%s force=%s",
                style_image_id, scene_id, product_id, ip_id, force)

            if not style_image_id:
                send_json(self, HTTPStatus.BAD_REQUEST, {"error": "styleImageId is required"})
                return

            # Resolve style image
            style_image = client.fetch_style_image(str(style_image_id))
            if not style_image:
                send_json(self, HTTPStatus.NOT_FOUND, {"error": f"style image {style_image_id} not found"})
                return

            resolved_product_id = str(style_image.get("productId") or "") or (product_id and str(product_id))
            resolved_ip_id = str(style_image.get("ipId") or "") or (ip_id and str(ip_id))
            if not resolved_product_id or not resolved_ip_id:
                send_json(self, HTTPStatus.BAD_REQUEST, {"error": "style image has no productId or ipId"})
                return

            # Resolve scene if not provided
            resolved_scene_id = scene_id and str(scene_id)
            resolved_scene_name = ""
            resolved_scene_url = ""
            if resolved_scene_id:
                scene = client.fetch_scene(resolved_scene_id)
                if scene:
                    resolved_scene_id = _scene_key(scene)
                    resolved_scene_name = _scene_name(scene)
                    resolved_scene_url = _scene_url(scene)

            # Fetch IP for person image
            ip = client.fetch_ip(resolved_ip_id)
            if not ip:
                send_json(self, HTTPStatus.NOT_FOUND, {"error": f"IP {resolved_ip_id} not found"})
                return
            ip_full_body_url = ip.get("fullBodyUrl")
            if not ip_full_body_url:
                send_json(self, HTTPStatus.BAD_REQUEST, {"error": f"IP {resolved_ip_id} has no fullBodyUrl"})
                return

            # Fetch product for main clothing image
            product = client.fetch_product(resolved_product_id)
            if not product:
                send_json(self, HTTPStatus.NOT_FOUND, {"error": f"product {resolved_product_id} not found"})
                return
            product_name = str(product.get("name") or resolved_product_id)
            images = product.get("images") or []
            if not isinstance(images, list) or not images:
                send_json(self, HTTPStatus.BAD_REQUEST, {"error": f"product {resolved_product_id} has no images"})
                return
            image_items = [item for item in images if isinstance(item, dict) and item.get("url")]
            if not image_items:
                send_json(self, HTTPStatus.BAD_REQUEST, {"error": f"product {resolved_product_id} has no valid image URLs"})
                return
            main_image = next((item for item in image_items if item.get("isMain") is True), None)
            if main_image is None:
                main_image = sorted(image_items, key=lambda x: int(x.get("order") or 999999))[0]
            main_image_url = str(main_image.get("url") or "")

            # Build task directory
            task_dir = self.server.store.output_root / (
                f"jimeng-img-{slugify(product_name)}-{resolved_product_id[:8]}__"
                f"style-{style_image_id[:8]}__scene-{slugify(resolved_scene_name)}-{resolved_scene_id[:8]}"
            )
            assets_dir = task_dir / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)

            # Download reference images
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
                log_error("download failed: %s", e)
                send_json(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"download failed: {e}"})
                return

            # Prompt
            if prompt_text is None:
                prompt_path = pathlib.Path("D:/Code/media/gpt_image2/prompts/08_即梦文生图")
                prompt_text = prompt_path.read_text(encoding="utf-8").strip() if prompt_path.exists() else ""

            # Write task.md
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

            # Write .media-ai.json sidecar (kebab-case kind)
            sidecar: dict[str, Any] = {
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
            if cookie and not payload.get("noEmbedCookie"):
                sidecar["cookie"] = cookie
            case_path.with_suffix(".media-ai.json").write_text(
                json.dumps(sidecar, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            dry_run = self._is_dry_run()
            if dry_run:
                log_info("dry-run: returning job preview without enqueue")

            try:
                if not dry_run:
                    jobs = self.server.store.add_jobs([case_path])
                    job = jobs[0]
                    log_info("<<< OK jimeng-image job_id=%s", job.id)
                    send_json(self, HTTPStatus.OK, {
                        "ok": True,
                        "job": {
                            "id": job.id,
                            "caseFile": str(job.case_file),
                            "mediaAi": public_media_ai(job.media_ai),
                        },
                    })
                else:
                    log_info("<<< DRY-RUN %s", case_path)
                    send_json(self, HTTPStatus.OK, {
                        "ok": True,
                        "dryRun": True,
                        "caseFile": str(case_path),
                        "mediaAi": public_media_ai(load_media_ai_sidecar(case_path)),
                        "message": "Dry-run: task built but not enqueued",
                    })
                return
            except Exception as error:
                log_error("enqueue failed: %s", error)
                send_json(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})
                return

        # ---- Single jimeng-video endpoint ------------------------------------
        jimeng_video_match = re.fullmatch(r"/v1/single/jimeng-video", path)
        if jimeng_video_match:
            log_info(">>> POST /v1/single/jimeng-video")
            cookie_header = self.headers.get("Cookie")
            client = self.server.media_ai_client
            cookie = client.resolve_cookie(cookie_header)

            payload = parse_json_body(self)
            product_id = payload.get("productId")
            ip_id = payload.get("ipId")
            first_frame_id = payload.get("firstFrameId")
            movement_id = payload.get("movementId")
            force = bool(payload.get("force", False))
            prompt_text = payload.get("prompt", "").strip() or None
            log_info("request productId=%s ipId=%s firstFrameId=%s movementId=%s", product_id, ip_id, first_frame_id, movement_id)
            dry_run = self._is_dry_run()
            if dry_run:
                log_info("dry-run: returning job preview without enqueue")

            if not product_id:
                send_json(self, HTTPStatus.BAD_REQUEST, {"error": "productId is required"})
                return

            resolved_product_id = str(product_id)
            resolved_ip_id = str(ip_id) if ip_id else None
            resolved_first_frame_id = str(first_frame_id) if first_frame_id else None

            # Fetch first frame image if provided
            first_frame_url = ""
            first_frame_path = None
            if resolved_first_frame_id:
                first_frame = client.fetch_first_frame(resolved_first_frame_id)
                if first_frame:
                    first_frame_url = str(first_frame.get("url") or "")

            # Build task directory
            task_dir = self.server.store.output_root / (
                f"jimeng-vid-{resolved_product_id[:8]}"
                f"{f'-ip-{resolved_ip_id[:8]}' if resolved_ip_id else ''}"
                f"{f'-ff-{resolved_first_frame_id[:8]}' if resolved_first_frame_id else ''}"
            )
            assets_dir = task_dir / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)

            # Download first frame image if available
            if first_frame_url:
                first_frame_media_url = resolve_media_url(client.media_base_url, first_frame_url)
                first_frame_path = assets_dir / f"first-frame{extension_from_url(first_frame_media_url)}"
                try:
                    client.download_file(first_frame_media_url, first_frame_path, cookie=cookie)
                except Exception as e:
                    log_info("download first frame failed: %s", e)

            # Prompt
            if prompt_text is None:
                prompt_path = pathlib.Path("D:/Code/media/gpt_image2/prompts/09_即梦文生视频")
                prompt_text = prompt_path.read_text(encoding="utf-8").strip() if prompt_path.exists() else ""

            # Write task.md
            case_path = task_dir / "task.md"
            lines = [f"# jimeng video / product {resolved_product_id}"]
            if first_frame_path and first_frame_path.exists():
                lines.extend(["", f"[首帧图]({first_frame_path.relative_to(task_dir).as_posix()})", ""])
            lines.extend(["", prompt_text, ""])
            case_path.write_text("\n".join(lines), encoding="utf-8")

            # Write .media-ai.json sidecar (kebab-case kind)
            sidecar: dict[str, Any] = {
                "kind": "video",
                "baseUrl": client.base_url,
                "productId": resolved_product_id,
                "uploadSubDir": "videos",
            }
            if resolved_ip_id:
                sidecar["ipId"] = resolved_ip_id
            if resolved_first_frame_id:
                sidecar["firstFrameId"] = resolved_first_frame_id
            if movement_id:
                sidecar["movementId"] = movement_id
            if cookie and not payload.get("noEmbedCookie"):
                sidecar["cookie"] = cookie
            case_path.with_suffix(".media-ai.json").write_text(
                json.dumps(sidecar, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            try:
                if not dry_run:
                    jobs = self.server.store.add_jobs([case_path])
                    job = jobs[0]
                    log_info("<<< OK jimeng-video job_id=%s", job.id)
                    send_json(self, HTTPStatus.OK, {
                        "ok": True,
                        "job": {
                            "id": job.id,
                            "caseFile": str(job.case_file),
                            "mediaAi": public_media_ai(job.media_ai),
                        },
                    })
                else:
                    log_info("<<< DRY-RUN %s", case_path)
                    send_json(self, HTTPStatus.OK, {
                        "ok": True,
                        "dryRun": True,
                        "caseFile": str(case_path),
                        "mediaAi": public_media_ai(load_media_ai_sidecar(case_path)),
                        "message": "Dry-run: task built but not enqueued",
                    })
                return
            except Exception as error:
                log_error("enqueue failed: %s", error)
                send_json(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})
                return

        send_json(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})


def resolve_case_paths(task_arguments: list[str]) -> list[pathlib.Path]:
    paths = [pathlib.Path(item).resolve() for item in task_arguments]
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(path)
        if path.suffix.lower() != ".md":
            raise ValueError(f"Only Markdown task files are supported: {path}")
    return paths


def run_server(host: str, port: int, task_arguments: list[str], output_root: pathlib.Path) -> None:
    case_paths = resolve_case_paths(task_arguments)
    jobs = build_jobs(case_paths, output_root.resolve())
    store = JobStore(jobs=jobs, output_root=output_root.resolve())
    output_root.mkdir(parents=True, exist_ok=True)

    log_info("server startup loaded_jobs=%d", len(jobs))
    for job in jobs:
        log_info("  job_id=%s case_file=%s", job.id, job.case_file)
    log_info("output_directory=%s", output_root.resolve())
    log_info("listening on http://%s:%d", host, port)

    server = AppServer((host, port), RequestHandler, store)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log_info("server stopped")


def inspect_case(task_argument: str) -> None:
    case_path = pathlib.Path(task_argument).resolve()
    prompt, assets = load_case_file(case_path)
    payload = {
        "caseFile": str(case_path),
        "prompt": prompt,
        "assets": [
            {
                "label": asset["label"],
                "name": asset["name"],
                "path": str(asset["path"]),
                "mimeType": asset["mimeType"],
            }
            for asset in assets
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local bridge for ChatGPT web image generation tasks.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="Start the local task server.")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--task", action="append", default=[], help="Path to a Markdown task file.")
    serve_parser.add_argument("--output-root", default="runs", help="Directory for generated outputs.")

    inspect_parser = subparsers.add_parser("inspect", help="Inspect a Markdown task file.")
    inspect_parser.add_argument("task", help="Path to a Markdown task file.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "serve":
        run_server(
            host=args.host,
            port=args.port,
            task_arguments=args.task,
            output_root=pathlib.Path(args.output_root),
        )
        return

    if args.command == "inspect":
        inspect_case(args.task)
        return

    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
