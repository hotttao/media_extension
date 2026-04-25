from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import os
import pathlib
import re
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


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_slug(value: str) -> str:
    lowered = value.lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return cleaned or "job"


def guess_mime_type(path: pathlib.Path) -> str:
    mime_type, _ = mimetypes.guess_type(path.name)
    return mime_type or "application/octet-stream"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ensure_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


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
            assets.append(
                {
                    "label": label,
                    "path": resolved,
                    "name": resolved.name,
                    "mimeType": guess_mime_type(resolved),
                    "sha256": sha256_bytes(resolved.read_bytes()),
                }
            )

        asset_index = asset_positions[resolved]
        return f"{label}（见附件{asset_index}）"

    prompt = link_pattern.sub(replacer, markdown_text).strip()
    return prompt, assets


def load_case_file(case_path: pathlib.Path) -> tuple[str, list[dict[str, Any]]]:
    markdown_text = case_path.read_text(encoding="utf-8")
    prompt, assets = replace_image_links(markdown_text, case_path.parent)
    return prompt, assets


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

    def to_public_dict(self, base_url: str) -> dict[str, Any]:
        return {
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
    return json.loads(sidecar_path.read_text(encoding="utf-8"))


def build_jobs(case_paths: list[pathlib.Path], output_root: pathlib.Path, start_index: int = 1) -> list[Job]:
    jobs: list[Job] = []
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for index, case_path in enumerate(case_paths, start=start_index):
        prompt, assets = load_case_file(case_path)
        media_ai = load_media_ai_sidecar(case_path)
        job_id = f"{index:03d}-{sanitize_slug(case_path.stem)}-{timestamp}"
        job_output_dir = output_root / job_id
        jobs.append(
            Job(
                id=job_id,
                case_file=case_path.resolve(),
                prompt=prompt,
                assets=assets,
                output_dir=job_output_dir,
                media_ai=media_ai,
            )
        )
    return jobs


def parse_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    content_length = int(handler.headers.get("Content-Length", "0"))
    raw_body = handler.rfile.read(content_length) if content_length else b"{}"
    return json.loads(raw_body.decode("utf-8"))


def request_json(
    method: str,
    url: str,
    *,
    cookie: str | None,
    body: dict[str, Any] | None = None,
    timeout: int = 120,
) -> Any:
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


def upload_file_multipart(
    url: str,
    *,
    cookie: str | None,
    file_path: pathlib.Path,
    sub_dir: str,
    timeout: int = 120,
) -> dict[str, Any]:
    boundary = f"----codex-{uuid.uuid4().hex}"
    file_bytes = file_path.read_bytes()
    mime_type = guess_mime_type(file_path)
    fields = [
        (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="subDir"\r\n\r\n'
            f"{sub_dir}\r\n"
        ).encode("utf-8"),
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode("utf-8"),
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


def save_media_ai_generated_image(job: Job, output_path: pathlib.Path) -> dict[str, Any] | None:
    if not job.media_ai:
        return None

    base_url = ensure_text(job.media_ai.get("baseUrl") or "http://localhost:3000").rstrip("/")
    cookie = ensure_text(job.media_ai.get("cookie") or os.environ.get("MEDIA_AI_COOKIE") or "") or None
    kind = ensure_text(job.media_ai.get("kind") or "model-image")
    product_id = ensure_text(job.media_ai.get("productId") or "")
    sub_dir = ensure_text(job.media_ai.get("uploadSubDir") or f"{kind}s")
    if not product_id:
        raise RuntimeError("Media AI sidecar requires productId.")

    upload_result = upload_file_multipart(
        f"{base_url}/api/upload",
        cookie=cookie,
        file_path=output_path,
        sub_dir=sub_dir,
    )
    image_url = ensure_text(upload_result.get("url") or "")
    if not image_url:
        raise RuntimeError(f"Media AI upload response did not include url: {upload_result}")

    if kind == "style-image":
        model_image_id = ensure_text(job.media_ai.get("modelImageId") or "")
        if not model_image_id:
            raise RuntimeError("Media AI style-image sidecar requires modelImageId.")
        save_body = {
            "modelImageId": model_image_id,
            "poseId": job.media_ai.get("poseId"),
            "makeupId": job.media_ai.get("makeupId"),
            "accessoryId": job.media_ai.get("accessoryId"),
            "imageUrl": image_url,
        }
        save_url = f"{base_url}/api/products/{product_id}/style-image/save"
    else:
        ip_id = ensure_text(job.media_ai.get("ipId") or "")
        if not ip_id:
            raise RuntimeError("Media AI model-image sidecar requires ipId.")
        save_body = {"ipId": ip_id, "imageUrl": image_url}
        save_url = f"{base_url}/api/products/{product_id}/model-image/save"

    save_result = request_json("POST", save_url, cookie=cookie, body=save_body)
    return {
        "kind": kind,
        "uploaded": upload_result,
        "saved": save_result,
    }


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


class RequestHandler(BaseHTTPRequestHandler):
    server: AppServer

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_OPTIONS(self) -> None:
        send_json(self, HTTPStatus.NO_CONTENT, {})

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
                print(f"[{job.id}] claimed by {worker_id or 'unknown-worker'}", flush=True)
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

            print(f"Enqueued {len(jobs)} job(s).", flush=True)
            for job in jobs:
                print(f"- {job.id}: {job.case_file}", flush=True)
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
            print(f"[{updated_job.id}] {message}", flush=True)
            send_json(self, HTTPStatus.OK, {"ok": True})
            return

        result_match = re.fullmatch(r"/v1/job/([^/]+)/result", path)
        if result_match:
            job_id = result_match.group(1)
            job = self.server.store.get_job(job_id)
            if not job:
                send_json(self, HTTPStatus.NOT_FOUND, {"error": "job_not_found"})
                return

            payload = parse_json_body(self)
            job.output_dir.mkdir(parents=True, exist_ok=True)
            (job.output_dir / "prompt.md").write_text(job.prompt, encoding="utf-8")
            if job.progress:
                write_json(job.output_dir / "logs.json", job.progress)

            images = payload.get("images", [])
            saved_files: list[str] = []
            media_ai_results: list[dict[str, Any]] = []
            skipped_files: list[dict[str, Any]] = []
            asset_hashes = {asset["sha256"] for asset in job.assets}
            for index, image in enumerate(images, start=1):
                base64_data = image.get("base64Data", "")
                binary = base64.b64decode(base64_data)
                image_hash = sha256_bytes(binary)
                if image_hash in asset_hashes:
                    skipped_files.append(
                        {
                            "filename": ensure_text(image.get("filename") or f"result-{index:02d}.png"),
                            "reason": "matches_input_asset",
                            "sha256": image_hash,
                            "sourceUrl": image.get("sourceUrl"),
                        }
                    )
                    continue
                original_name = ensure_text(image.get("filename") or f"result-{index:02d}.png")
                suffix = pathlib.Path(original_name).suffix or ".png"
                output_name = f"result-{len(saved_files) + 1:02d}{suffix}"
                output_path = job.output_dir / output_name
                output_path.write_bytes(binary)
                saved_files.append(output_name)
                if len(saved_files) == 1 and job.media_ai:
                    try:
                        media_ai_result = save_media_ai_generated_image(job, output_path)
                        if media_ai_result:
                            media_ai_results.append(media_ai_result)
                            print(f"[{job.id}] saved model image to Media AI", flush=True)
                    except Exception as error:
                        media_ai_results.append({"error": str(error)})
                        print(f"[{job.id}] Media AI save failed: {error}", flush=True)

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
                print(f"[{job.id}] saved {len(saved_files)} generated image(s)", flush=True)
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
            print(f"[{job.id}] {reason}", flush=True)
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
            print(f"[{job.id}] failed: {reason}", flush=True)
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

    print(f"Loaded {len(jobs)} job(s).", flush=True)
    for job in jobs:
        print(f"- {job.id}: {job.case_file}", flush=True)
    print(f"Output directory: {output_root.resolve()}", flush=True)
    print(f"Listening on http://{host}:{port}", flush=True)

    server = AppServer((host, port), RequestHandler, store)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.", flush=True)


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
