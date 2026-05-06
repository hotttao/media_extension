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


def asset_from_path(path: pathlib.Path, label: str) -> dict[str, Any]:
    return {
        "label": label,
        "path": path,
        "name": path.name,
        "mimeType": guess_mime_type(path),
        "sha256": sha256_bytes(path.read_bytes()),
    }


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


# ---------------------------------------------------------------------------
# Job builder
# ---------------------------------------------------------------------------
def build_jobs(case_paths: list[pathlib.Path], output_root: pathlib.Path, start_index: int = 1) -> list[Job]:
    jobs: list[Job] = []
    for case_path in case_paths:
        # job_id is the directory name (submit scripts write to output_root/job_id/input/task.md)
        job_id = case_path.parent.parent.name  # case_path = output_root/job_id/input/task.md
        case_file = case_path.resolve()
        prompt, assets = load_case_file(case_path)
        media_ai = load_media_ai_sidecar(case_path)

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
                # platform can be set explicitly in sidecar (Jimeng sets platform="jimeng")
                # otherwise default to GPT
                platform = media_ai.get("platform") or "gpt"
                if platform == "jimeng":
                    target_url = "https://jimeng.jianying.com/ai-tool/home/?type=image&workspace=0"

        jobs.append(
            Job(
                id=job_id,
                case_file=case_file,
                prompt=prompt,
                assets=assets,
                output_dir=(output_root / job_id / "output").resolve(),
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
