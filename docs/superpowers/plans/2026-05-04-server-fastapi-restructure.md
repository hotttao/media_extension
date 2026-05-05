# local_bridge FastAPI 重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `server.py` 从手写 `BaseHTTPRequestHandler` 重构为 FastAPI + 轻量 DDD，所有输入输出通过 Pydantic 强校验，OpenAPI 文档自动生成。

**Architecture:** HTTP 层用 FastAPI（路由 + Pydantic Request/Response），业务逻辑迁移到 `domain/services.py`，持久化在 `infrastructure/persistence.py`，`media_ai_client.py` 独立保持。

**Tech Stack:** FastAPI, uvicorn, Pydantic v2（已有）

---

## 依赖变更

在 `pyproject.toml` 的 `dependencies` 中新增：
```python
"fastapi>=0.115.0",
"uvicorn[standard]>=0.30.0",
```

---

## 文件结构

```
local_bridge/
├── __init__.py
├── main.py                      # FastAPI app + lifespan（新增）
├── domain/
│   ├── __init__.py
│   ├── models.py                # Job dataclass、sidecar 模型（从 server.py 迁移）
│   └── services.py              # build_jobs、load_case_file、upload 等（从 server.py 迁移）
├── api/
│   ├── __init__.py
│   ├── schemas.py               # 所有 Pydantic Request/Response 模型（新增）
│   └── routers/
│       ├── __init__.py
│       ├── jobs.py              # GET /v1/state, POST /v1/jobs
│       ├── job_claim.py         # GET /v1/job/claim
│       ├── job_progress.py      # POST /v1/job/{id}/progress
│       ├── job_result.py        # POST /v1/job/{id}/result
│       ├── job_fail.py          # POST /v1/job/{id}/fail
│       ├── job_requeue.py       # POST /v1/job/{id}/requeue
│       ├── job_cancel.py        # POST /v1/job/{id}/cancel
│       ├── jobs_cancel.py       # POST /v1/jobs/cancel
│       ├── single_model_image.py # POST /v1/single/model-image
│       ├── single_style_image.py# POST /v1/single/style-image
│       ├── single_first_frame.py# POST /v1/single/first-frame-image
│       └── single_jimeng.py    # POST /v1/single/jimeng-image, /v1/single/jimeng-video
├── infrastructure/
│   ├── __init__.py
│   ├── persistence.py           # JobStore 类（从 server.py JobStore 迁移）
│   └── media_ai_client.py      # 复制自上层 media_ai_client.py（不变）
├── utils.py                    # 保持不变
└── cli/
    └── commands.py              # serve / inspect CLI（从 server.py 迁移）
```

---

## Task 1: 添加依赖

**文件:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 添加 FastAPI 和 uvicorn 依赖**

在 `pyproject.toml` 的 `dependencies` 数组中新增：
```python
"fastapi>=0.115.0",
"uvicorn[standard]>=0.30.0",
```

运行: `uv sync`
预期: 无报错，FastAPI 和 uvicorn 安装成功

- [ ] **Step 2: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add fastapi and uvicorn dependencies

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 2: 创建目录结构

**文件:**
- Create: `local_bridge/domain/__init__.py`
- Create: `local_bridge/domain/models.py`
- Create: `local_bridge/domain/services.py`
- Create: `local_bridge/api/__init__.py`
- Create: `local_bridge/api/schemas.py`
- Create: `local_bridge/api/routers/__init__.py`
- Create: `local_bridge/api/routers/jobs.py`
- Create: `local_bridge/api/routers/job_claim.py`
- Create: `local_bridge/api/routers/job_progress.py`
- Create: `local_bridge/api/routers/job_result.py`
- Create: `local_bridge/api/routers/job_fail.py`
- Create: `local_bridge/api/routers/job_requeue.py`
- Create: `local_bridge/api/routers/job_cancel.py`
- Create: `local_bridge/api/routers/jobs_cancel.py`
- Create: `local_bridge/api/routers/single_model_image.py`
- Create: `local_bridge/api/routers/single_style_image.py`
- Create: `local_bridge/api/routers/single_first_frame.py`
- Create: `local_bridge/api/routers/single_jimeng.py`
- Create: `local_bridge/infrastructure/__init__.py`
- Create: `local_bridge/infrastructure/persistence.py`
- Create: `local_bridge/infrastructure/media_ai_client.py`
- Create: `local_bridge/cli/__init__.py`
- Create: `local_bridge/cli/commands.py`
- Modify: `local_bridge/__init__.py`

- [ ] **Step 1: 创建所有目录和空文件**

```bash
mkdir -p local_bridge/domain
mkdir -p local_bridge/api/routers
mkdir -p local_bridge/infrastructure
mkdir -p local_bridge/cli

# 创建 __init__.py 文件（空）
touch local_bridge/domain/__init__.py
touch local_bridge/api/__init__.py
touch local_bridge/api/routers/__init__.py
touch local_bridge/infrastructure/__init__.py
touch local_bridge/cli/__init__.py
```

- [ ] **Step 2: Commit**

```bash
git add local_bridge/domain local_bridge/api local_bridge/infrastructure local_bridge/cli
git commit -m "chore: scaffold DDD directory structure

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 3: 迁移 domain/models.py（Job dataclass + 工具函数）

**文件:**
- Create: `local_bridge/domain/models.py`
- 参考: `server.py:1-145`（Job dataclass、JobStore、load_case_file、replace_image_links、build_jobs）

- [ ] **Step 1: 写入 domain/models.py**

文件内容：

```python
"""Domain models — Job dataclass and related types. Migrated from server.py."""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import mimetypes
import pathlib
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = "DEBUG"
_LOG_DIR = pathlib.Path("logs")
_LOG_DIR.mkdir(exist_ok=True, parents=True)
_logger = logging.getLogger("local_bridge.domain")
_logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
_fh = logging.FileHandler(_LOG_DIR / "server.log", encoding="utf-8")
_fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
_logger.addHandler(_fh)


def _log(level: int, msg: str, *args: Any, **kwargs: Any) -> None:
    extra: dict[str, Any] = {}
    for k, v in kwargs.items():
        extra[f"extra_{k}"] = v
    formatted = msg % args if args else msg
    _logger.log(level, formatted, extra=extra if extra else None)


def log_info(msg: str, *args: Any, **kwargs: Any) -> None:
    _log(logging.INFO, msg, *args, **kwargs)


def log_debug(msg: str, *args: Any, **kwargs: Any) -> None:
    _log(logging.DEBUG, msg, *args, **kwargs)


def log_error(msg: str, *args: Any, **kwargs: Any) -> None:
    _log(logging.ERROR, msg, *args, **kwargs)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
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


def write_json(path: pathlib.Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Job Model
# ---------------------------------------------------------------------------
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
        if self.platform:
            result["platform"] = self.platform
        if self.target_url:
            result["targetUrl"] = self.target_url
        if self.media_ai:
            if self.media_ai.get("styleImageId"):
                result["styleImageId"] = self.media_ai["styleImageId"]
            if self.media_ai.get("sceneId"):
                result["sceneId"] = self.media_ai["sceneId"]
        return result


# ---------------------------------------------------------------------------
# Sidecar loading
# ---------------------------------------------------------------------------
def load_media_ai_sidecar(case_path: pathlib.Path) -> dict[str, Any] | None:
    sidecar_path = case_path.with_suffix(".media-ai.json")
    if not sidecar_path.exists():
        return None
    try:
        return json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# Case file processing
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Job builder
# ---------------------------------------------------------------------------
def build_jobs(case_paths: list[pathlib.Path], output_root: pathlib.Path, start_index: int = 1) -> list[Job]:
    jobs: list[Job] = []
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for index, case_path in enumerate(case_paths, start=start_index):
        prompt, assets = load_case_file(case_path)
        media_ai = load_media_ai_sidecar(case_path)
        job_id = f"{index:03d}-{sanitize_slug(case_path.stem)}-{timestamp}"
        job_output_dir = output_root / job_id

        platform: str | None = None
        target_url: str | None = None
        if media_ai:
            kind = media_ai.get("kind") or ""
            if kind == "jimeng-image":
                platform = "jimeng"
                target_url = "https://jimeng.jianying.com/ai-tool/home/?type=image&workspace=0"
            elif kind == "jimeng-video":
                platform = "jimeng"
                target_url = "https://jimeng.jianying.com/ai-tool/home/?type=video&workspace=0"
            elif kind in ("first-frame-image", "style-image", "model-image"):
                platform = "gpt"

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


# ---------------------------------------------------------------------------
# Public media_ai (redacted)
# ---------------------------------------------------------------------------
def public_media_ai(media_ai: dict[str, Any] | None) -> dict[str, Any] | None:
    if media_ai is None:
        return None
    payload = dict(media_ai)
    if "cookie" in payload:
        payload["cookie"] = "<redacted>"
    return payload
```

- [ ] **Step 2: 运行导入测试**

运行: `uv run python -c "from local_bridge.domain.models import Job, build_jobs, load_case_file, public_media_ai; print('OK')"`
预期: 输出 `OK`，无报错

- [ ] **Step 3: Commit**

```bash
git add local_bridge/domain/models.py
git commit -m "feat(domain): migrate Job dataclass, build_jobs, and utilities from server.py

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 4: 迁移 infrastructure/persistence.py（JobStore）

**文件:**
- Create: `local_bridge/infrastructure/persistence.py`
- 参考: `server.py:196-335`（JobStore class）

- [ ] **Step 1: 写入 infrastructure/persistence.py**

```python
"""JobStore persistence layer. Migrated from server.py."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from local_bridge.domain.models import Job, build_jobs, utc_now_iso, write_json


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
            job = self._get_job_or_raise(job_id)
            job.status = "completed"
            job.finished_at = utc_now_iso()
            return job

    def mark_failed(self, job_id: str, reason: str) -> Job:
        with self.lock:
            job = self._get_job_or_raise(job_id)
            job.status = "failed"
            job.finished_at = utc_now_iso()
            job.failure_reason = reason
            return job

    def requeue(self, job_id: str) -> Job:
        with self.lock:
            job = self._get_job_or_raise(job_id)
            job.status = "pending"
            job.claimed_at = None
            job.finished_at = None
            job.failure_reason = None
            job.worker_id = None
            return job

    def cancel(self, job_id: str) -> Job:
        with self.lock:
            job = self._get_job_or_raise(job_id)
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
            job = self._get_job_or_raise(job_id)
            job.claimed_at = utc_now_iso()
            return job

    def add_progress(self, job_id: str, message: str, at: str | None = None, details: Any | None = None) -> Job:
        with self.lock:
            job = self._get_job_or_raise(job_id)
            event: dict[str, Any] = {
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

    def summary(self) -> dict[str, Any]:
        with self.lock:
            from local_bridge.domain.models import public_media_ai
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

    def _get_job_or_raise(self, job_id: str) -> Job:
        for job in self.jobs:
            if job.id == job_id:
                return job
        raise KeyError(job_id)
```

- [ ] **Step 2: 运行导入测试**

运行: `uv run python -c "from local_bridge.infrastructure.persistence import JobStore; print('OK')"`
预期: 输出 `OK`

- [ ] **Step 3: Commit**

```bash
git add local_bridge/infrastructure/persistence.py
git commit -m "feat(infrastructure): migrate JobStore from server.py

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 5: 迁移 infrastructure/media_ai_client.py

**文件:**
- Create: `local_bridge/infrastructure/media_ai_client.py`
- Copy from: `local_bridge/media_ai_client.py`（全文复制，不改内容）

- [ ] **Step 1: 复制 media_ai_client.py 到 infrastructure/**

```bash
cp local_bridge/media_ai_client.py local_bridge/infrastructure/media_ai_client.py
```

- [ ] **Step 2: Commit**

```bash
git add local_bridge/infrastructure/media_ai_client.py
git commit -m "chore(infrastructure): copy media_ai_client.py as-is into infrastructure layer

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 6: 定义 Pydantic Schemas（api/schemas.py）

**文件:**
- Create: `local_bridge/api/schemas.py`
- 参考: `server.py` 中所有 HTTP 请求/响应结构

- [ ] **Step 1: 写入 api/schemas.py**

```python
"""Pydantic schemas for all API request/response models."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------
class ErrorResponse(BaseModel):
    ok: bool = False
    error: str
    detail: str | None = None


# ---------------------------------------------------------------------------
# /v1/jobs
# ---------------------------------------------------------------------------
class JobsCreateRequest(BaseModel):
    caseFiles: list[str] = Field(..., description="List of .md case file paths")
    tasks: list[str] | None = None  # backward compat alias


class AssetResponse(BaseModel):
    index: int
    label: str
    name: str
    mimeType: str
    url: str


class JobInfo(BaseModel):
    id: str
    caseFile: str
    prompt: str | None = None
    mediaAi: dict[str, Any] | None = None


class JobCreatedResponse(BaseModel):
    ok: bool = True
    jobs: list[JobInfo]


# ---------------------------------------------------------------------------
# /v1/state
# ---------------------------------------------------------------------------
class JobStatusResponse(BaseModel):
    id: str
    caseFile: str
    status: str
    createdAt: str | None = None
    claimedAt: str | None = None
    finishedAt: str | None = None
    failureReason: str | None = None
    outputDir: str | None = None
    latestProgress: dict[str, Any] | None = None
    mediaAi: dict[str, Any] | None = None


class StateResponse(BaseModel):
    jobs: list[JobStatusResponse]


# ---------------------------------------------------------------------------
# /v1/job/claim
# ---------------------------------------------------------------------------
class ClaimResponse(BaseModel):
    job: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# /v1/job/{id}/progress
# ---------------------------------------------------------------------------
class ProgressUpdateRequest(BaseModel):
    message: str
    at: str | None = None
    details: Any | None = None


class SuccessResponse(BaseModel):
    ok: bool = True


# ---------------------------------------------------------------------------
# /v1/job/{id}/result
# ---------------------------------------------------------------------------
class ImageResult(BaseModel):
    filename: str | None = None
    mimeType: str | None = None
    base64Data: str | None = None
    sourceUrl: str | None = None


class VideoResult(BaseModel):
    filename: str | None = None
    base64Data: str | None = None
    sourceUrl: str | None = None


class ResultSubmitRequest(BaseModel):
    images: list[ImageResult] = []
    videos: list[VideoResult] = []
    assistantResponse: str | None = None
    logs: list[dict[str, Any]] | None = None


class ResultSubmitResponse(BaseModel):
    ok: bool
    savedFiles: list[str] = []
    skippedFiles: list[dict[str, Any]] = []
    mediaAiResults: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# /v1/job/{id}/fail
# ---------------------------------------------------------------------------
class FailSubmitRequest(BaseModel):
    reason: str
    logs: list[dict[str, Any]] | None = None


# ---------------------------------------------------------------------------
# /v1/job/{id}/requeue
# ---------------------------------------------------------------------------
class RequeueResponse(BaseModel):
    ok: bool = True
    jobId: str
    status: str


# ---------------------------------------------------------------------------
# /v1/job/{id}/cancel
# ---------------------------------------------------------------------------
class CancelResponse(BaseModel):
    ok: bool = True
    jobId: str
    status: str


# ---------------------------------------------------------------------------
# /v1/jobs/cancel
# ---------------------------------------------------------------------------
class CancelAllResponse(BaseModel):
    ok: bool = True
    canceled: list[dict[str, str]] = []


# ---------------------------------------------------------------------------
# Single task endpoints
# ---------------------------------------------------------------------------
class SingleJobCreatedResponse(BaseModel):
    ok: bool
    job: JobInfo | None = None
    dryRun: bool | None = None
    caseFile: str | None = None
    message: str | None = None


class JimengImageCreateRequest(BaseModel):
    styleImageId: str
    sceneId: str | None = None
    productId: str | None = None
    ipId: str | None = None
    force: bool = False
    prompt: str | None = None
    noEmbedCookie: bool = False


class JimengVideoCreateRequest(BaseModel):
    productId: str
    ipId: str | None = None
    firstFrameId: str | None = None
    movementId: str | None = None
    force: bool = False
    prompt: str | None = None
    noEmbedCookie: bool = False


class ModelImageCreateRequest(BaseModel):
    modelImageId: str | None = None
    productId: str | None = None
    ipId: str | None = None
    force: bool = False


class StyleImageCreateRequest(BaseModel):
    modelImageId: str
    poseId: str
    force: bool = False


class FirstFrameImageCreateRequest(BaseModel):
    styleImageId: str
    sceneId: str
    force: bool = False
```

- [ ] **Step 2: 运行导入测试**

运行: `uv run python -c "from local_bridge.api.schemas import *; print('OK')"`
预期: 输出 `OK`

- [ ] **Step 3: Commit**

```bash
git add local_bridge/api/schemas.py
git commit -m "feat(api): define all Pydantic request/response schemas

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 7x: 迁移 domain/services.py（上传/保存函数）

**文件:**
- Create: `local_bridge/domain/services.py`
- 参考: `server.py:417-571`（`request_json`、`upload_file_multipart`、`save_media_ai_generated_image`、`save_media_ai_generated_video`）

**必须先于 job_result.py 完成。**

- [ ] **Step 1: 写入 domain/services.py**

关键函数：
- `request_json()` — HTTP POST/GET，带 cookie
- `upload_file_multipart()` — 文件上传 multipart
- `save_media_ai_generated_image()` — 图片上传并保存到 Media AI
- `save_media_ai_generated_video()` — 视频上传并保存到 Media AI
- `resolve_media_url()`、`extension_from_url()`、`slugify()` — 工具函数（从 media_ai_client.py 复制）

```python
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

from local_bridge.domain.models import ensure_text, sha256_bytes


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


def save_media_ai_generated_image(job, output_path: pathlib.Path) -> dict[str, Any] | None:
    """Upload and save a generated image to Media AI."""
    if not job.media_ai:
        return None
    base_url = ensure_text(job.media_ai.get("baseUrl") or "http://localhost:3000").rstrip("/")
    cookie = ensure_text(job.media_ai.get("cookie") or "").strip() or None
    kind = ensure_text(job.media_ai.get("kind") or "model-image")
    product_id = ensure_text(job.media_ai.get("productId") or "")
    sub_dir = ensure_text(job.media_ai.get("uploadSubDir") or f"{kind}s")
    if not product_id:
        raise RuntimeError("Media AI sidecar requires productId.")

    upload_result = upload_file_multipart(
        f"{base_url}/api/upload", cookie=cookie, file_path=output_path, sub_dir=sub_dir
    )
    image_url = ensure_text(upload_result.get("url") or "")
    if not image_url:
        raise RuntimeError(f"Media AI upload response did not include url: {upload_result}")

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
        style_image_id = ensure_text(job.media_ai.get("styleImageId") or "")
        if not style_image_id:
            raise RuntimeError("first-frame sidecar requires styleImageId.")
        save_body = {
            "styleImageId": style_image_id,
            "sceneId": job.media_ai.get("sceneId"),
            "composition": job.media_ai.get("composition"),
            "imageUrl": image_url,
        }
        save_url = f"{base_url}/api/products/{product_id}/first-frame"
    elif kind == "jimeng-image":
        ip_id = ensure_text(job.media_ai.get("ipId") or "")
        if not ip_id:
            raise RuntimeError("jimeng-image sidecar requires ipId.")
        save_body = {"ipId": ip_id, "imageUrl": image_url}
        save_url = f"{base_url}/api/products/{product_id}/first-frame"
    else:
        ip_id = ensure_text(job.media_ai.get("ipId") or "")
        if not ip_id:
            raise RuntimeError("model-image sidecar requires ipId.")
        save_body = {"ipId": ip_id, "imageUrl": image_url}
        save_url = f"{base_url}/api/products/{product_id}/model-image/save"

    save_result = request_json("POST", save_url, cookie=cookie, body=save_body)
    return {"kind": kind, "uploaded": upload_result, "saved": save_result}


def save_media_ai_generated_video(job, output_path: pathlib.Path) -> dict[str, Any] | None:
    """Upload and save a generated video to Media AI."""
    if not job.media_ai:
        return None
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
    save_result = request_json("POST", save_url, cookie=cookie, body=save_body)
    return {"kind": "video", "uploaded": upload_result, "saved": save_result}
```

- [ ] **Step 2: 运行导入测试**

运行: `uv run python -c "from local_bridge.domain.services import save_media_ai_generated_image, save_media_ai_generated_video, request_json; print('OK')"`
预期: 输出 `OK`

- [ ] **Step 3: Commit**

```bash
git add local_bridge/domain/services.py
git commit -m "feat(domain): migrate upload/save services from server.py

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 7: 实现 API Routers

### Task 7a: jobs.py（GET /v1/state, POST /v1/jobs）

**文件:**
- Modify: `local_bridge/api/routers/jobs.py`
- 依赖注入: `JobStore` via `Depends`

```python
"""Router for /v1/state and /v1/jobs."""
from fastapi import APIRouter, Depends, HTTPException, Request
from local_bridge.api.schemas import (
    ClaimResponse,
    ErrorResponse,
    JobCreatedResponse,
    JobsCreateRequest,
    StateResponse,
)
from local_bridge.domain.models import Job

router = APIRouter(prefix="/v1", tags=["jobs"])


def get_store(request: Request) -> "JobStore":
    return request.app.state.store


@router.get("/state", response_model=StateResponse)
def get_state(request: Request):
    store: "JobStore" = request.app.state.store
    return StateResponse(**store.summary())


@router.post("/jobs", response_model=JobCreatedResponse, responses={400: {"model": ErrorResponse}})
def create_jobs(body: JobsCreateRequest, request: Request):
    from pathlib import Path
    from local_bridge.domain.models import build_jobs

    store: "JobStore" = request.app.state.store
    raw_paths = body.caseFiles or body.tasks or []
    if not isinstance(raw_paths, list):
        raise HTTPException(status_code=400, detail="caseFiles must be an array")

    try:
        case_paths = [Path(str(item)).resolve() for item in raw_paths]
        for p in case_paths:
            if not p.exists():
                raise HTTPException(status_code=400, detail=f"File not found: {p}")
            if p.suffix.lower() != ".md":
                raise HTTPException(status_code=400, detail=f"Only Markdown task files are supported: {p}")
        jobs = store.add_jobs(case_paths)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))

    return JobCreatedResponse(
        ok=True,
        jobs=[
            {"id": j.id, "caseFile": str(j.case_file), "mediaAi": j.media_ai}
            for j in jobs
        ],
    )
```

### Task 7b: job_claim.py（GET /v1/job/claim）

**文件:**
- Create: `local_bridge/api/routers/job_claim.py`

```python
"""Router for /v1/job/claim."""
from fastapi import APIRouter, Request, Header
from local_bridge.api.schemas import ClaimResponse

router = APIRouter(prefix="/v1", tags=["job"])


@router.get("/job/claim", response_model=ClaimResponse)
def claim_job(request: Request, x_worker_id: str | None = Header(None)):
    store = request.app.state.store
    host = request.headers.get("Host", "127.0.0.1:8765")
    base_url = f"http://{host}"
    job = store.claim_next_job(x_worker_id)
    if job:
        from local_bridge.domain.models import public_media_ai
        return ClaimResponse(job=job.to_public_dict(base_url))
    return ClaimResponse(job=None)
```

### Task 7c: job_progress.py（POST /v1/job/{id}/progress）

**文件:**
- Create: `local_bridge/api/routers/job_progress.py`

```python
"""Router for /v1/job/{id}/progress."""
from fastapi import APIRouter, HTTPException, Request
from local_bridge.api.schemas import ProgressUpdateRequest, SuccessResponse

router = APIRouter(prefix="/v1", tags=["job"])


@router.post("/job/{job_id}/progress", response_model=SuccessResponse, responses={404: {"model": dict}})
def update_progress(job_id: str, body: ProgressUpdateRequest, request: Request):
    store = request.app.state.store
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job_not_found")
    store.add_progress(job_id, body.message, at=body.at, details=body.details)
    return SuccessResponse(ok=True)
```

### Task 7d: job_result.py（POST /v1/job/{id}/result）

**文件:**
- Create: `local_bridge/api/routers/job_result.py`

这是最复杂的 router，包含了文件保存和 Media AI 上传逻辑。需要从 server.py 的 `/v1/job/{id}/result` handler 迁移。

**关键：** Media AI 保存逻辑（`save_media_ai_generated_image`、`save_media_ai_generated_video`）作为 service 函数迁移到 `domain/services.py`，然后在这里调用。

（由于 router 代码较长且依赖 domain/services.py 中的 upload 函数，此任务在 domain/services.py 完成后统一实现）

### Task 7e–7h: job_fail, job_requeue, job_cancel, jobs_cancel

逐个实现简单 router：

**job_fail.py:**
```python
@router.post("/job/{job_id}/fail", response_model=SuccessResponse, responses={404: {"model": dict}})
def fail_job(job_id: str, body: FailSubmitRequest, request: Request):
    store = request.app.state.store
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job_not_found")
    job.output_dir.mkdir(parents=True, exist_ok=True)
    (job.output_dir / "prompt.md").write_text(job.prompt, encoding="utf-8")
    from local_bridge.domain.models import write_json
    if job.progress:
        write_json(job.output_dir / "logs.json", job.progress)
    write_json(job.output_dir / "failure.json", {...})
    store.mark_failed(job_id, body.reason)
    return SuccessResponse(ok=True)
```

**job_requeue.py, job_cancel.py, jobs_cancel.py:** 类似结构。

### Task 7i: single_* routers（4个单任务端点）

从 server.py 的 `/v1/single/*` handler 迁移，调用 `infrastructure/media_ai_client.py` 的 MediaAIClient 实例。

**注意：** 每个 single router 需要注入 `MediaAIClient`。由于 `AppServer` 在 server.py 中持有 `media_ai_client`，FastAPI app 也在 `app.state` 中持有相同引用。

---

## Task 8: 实现 main.py（FastAPI app 组装）

**文件:**
- Create: `local_bridge/main.py`

```python
"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from local_bridge.api.routers import (
    jobs,
    job_claim,
    job_progress,
    job_result,
    job_fail,
    job_requeue,
    job_cancel,
    jobs_cancel,
    single_model_image,
    single_style_image,
    single_first_frame,
    single_jimeng,
)
from local_bridge.domain.models import build_jobs
from local_bridge.infrastructure.media_ai_client import MediaAIClient
from local_bridge.infrastructure.persistence import JobStore

MEDIA_AI_BASE_URL = "http://localhost:3000"
MEDIA_AI_MEDIA_BASE_URL = "http://192.168.2.38"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Default empty store; CLI overrides via app.state.store
    yield


def create_app(store: JobStore | None = None) -> FastAPI:
    app = FastAPI(
        title="local_bridge",
        description="Chrome extension bridge for Media AI job automation",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount routers
    for router in [
        jobs.router,
        job_claim.router,
        job_progress.router,
        job_result.router,
        job_fail.router,
        job_requeue.router,
        job_cancel.router,
        jobs_cancel.router,
        single_model_image.router,
        single_style_image.router,
        single_first_frame.router,
        single_jimeng.router,
    ]:
        app.include_router(router)

    # MediaAIClient on app state
    app.state.media_ai_client = MediaAIClient(
        base_url=MEDIA_AI_BASE_URL,
        media_base_url=MEDIA_AI_MEDIA_BASE_URL,
    )

    # JobStore on app state (set by CLI)
    app.state.store = store

    return app


app = create_app()
```

---

## Task 9: 迁移 CLI（cli/commands.py）

**文件:**
- Create: `local_bridge/cli/commands.py`
- 参考: `server.py:1522-1596`（`run_server`、`inspect_case`、`main`）

```python
"""CLI commands. Migrated from server.py main()."""
import argparse
import sys
from pathlib import Path

import uvicorn

from local_bridge.domain.models import build_jobs, load_case_file
from local_bridge.infrastructure.persistence import JobStore
from local_bridge.main import create_app


def run_server(host: str, port: int, task_arguments: list[str], output_root: Path) -> None:
    case_paths = [Path(item).resolve() for item in task_arguments]
    jobs = build_jobs(case_paths, output_root.resolve())
    store = JobStore(jobs=jobs, output_root=output_root.resolve())
    output_root.mkdir(parents=True, exist_ok=True)

    app = create_app(store)
    uvicorn.run(app, host=host, port=port)


def inspect_case(task_argument: str) -> None:
    import json
    case_path = Path(task_argument).resolve()
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


def main() -> None:
    parser = argparse.ArgumentParser(description="local_bridge serve/inspect CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="Start the local task server.")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--task", action="append", default=[], help="Path to a Markdown task file.")
    serve_parser.add_argument("--output-root", default="runs", help="Directory for generated outputs.")

    inspect_parser = subparsers.add_parser("inspect", help="Inspect a Markdown task file.")
    inspect_parser.add_argument("task", help="Path to a Markdown task file.")

    args = parser.parse_args()

    if args.command == "serve":
        run_server(
            host=args.host,
            port=args.port,
            task_arguments=args.task,
            output_root=Path(args.output_root),
        )
    elif args.command == "inspect":
        inspect_case(args.task)
    else:
        raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
```

---

## Task 10: 更新入口（__main__.py）

**文件:**
- Modify: `local_bridge/__init__.py`

在 `local_bridge/__main__.py` 中指向 CLI：

```python
"""Allow: python -m local_bridge serve ..."""
from local_bridge.cli.commands import main
main()
```

---

## Task 11: 端到端验证

- [ ] **Step 1: 导入验证**

运行: `uv run python -c "from local_bridge.main import app; print('OK')"`
预期: 输出 `OK`

- [ ] **Step 2: OpenAPI 验证**

运行: `uv run uvicorn local_bridge.main:app --host 127.0.0.1 --port 8765 &`
`curl -s http://localhost:8765/openapi.json | python -c "import sys,json; d=json.load(sys.stdin); print(d['info']['title'], d['info']['version'])"`
预期: 输出 `local_bridge 1.0.0`

- [ ] **Step 3: Swagger UI 验证**

运行: `curl -s -o /dev/null -w "%{http_code}" http://localhost:8765/docs`
预期: `200`

- [ ] **Step 4: Kill uvicorn**

运行: `pkill -f "uvicorn local_bridge.main:app"`（或 `taskkill` on Windows）

- [ ] **Step 5: Commit**

```bash
git add local_bridge/__init__.py local_bridge/__main__.py local_bridge/main.py local_bridge/cli/commands.py
git commit -m "feat: wire FastAPI app, CLI, and all routers

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## 验证步骤汇总

1. `uv run python -c "from local_bridge.main import app; print('OK')"` → `OK`
2. `uv run uvicorn local_bridge.main:app --port 8765 &` → 启动成功
3. `curl http://localhost:8765/docs` → HTTP 200
4. `curl http://localhost:8765/openapi.json | python -m json.tool | head -20` → 有效 JSON
5. 现有 submit 脚本端到端回归测试
