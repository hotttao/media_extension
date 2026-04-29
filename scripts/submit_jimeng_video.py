from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from local_bridge.media_ai_client import MediaAIClient
from local_bridge.single_task import (
    resolve_media_url,
    extension_from_url,
    download_file,
    slugify,
)

DEFAULT_BASE_URL = "http://localhost:3000"
DEFAULT_BRIDGE_URL = "http://127.0.0.1:8765"
DEFAULT_PROMPT_FILE = "prompts/06_文生视频提示词.md"


# ---------------------------------------------------------------------------
# Shared utilities (same pattern as submit_jimeng_image.py)
# ---------------------------------------------------------------------------

def request_json(
    method: str,
    url: str,
    *,
    body: dict[str, Any] | None = None,
    timeout: int = 120,
) -> Any:
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
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


def can_reach_bridge(bridge_url: str, timeout: int = 3) -> bool:
    try:
        request_json("GET", f"{bridge_url.rstrip('/')}/health", timeout=timeout)
        return True
    except Exception:
        return False


def ensure_bridge_running(args: argparse.Namespace) -> None:
    if can_reach_bridge(args.bridge_url):
        return
    import subprocess
    if args.no_auto_bridge:
        raise RuntimeError(
            f"local_bridge is not running at {args.bridge_url}. "
            "Start it with: python local_bridge/server.py serve"
        )
    import pathlib
    log_dir = pathlib.Path(args.output_root)
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / "auto-local-bridge.log"
    log_file = log_path.open("a", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "local_bridge/server.py", "serve", "--output-root", "runs"],
        cwd=pathlib.Path.cwd(),
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    for _ in range(20):
        if proc.poll() is not None:
            raise RuntimeError(f"Failed to start local bridge. See {log_path}.")
        if can_reach_bridge(args.bridge_url):
            print(f"[BRIDGE] started local queue bridge at {args.bridge_url}. Log: {log_path}")
            return
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for local bridge to start. See {log_path}.")


def wait_for_jobs(
    bridge_url: str,
    job_ids: set[str],
    *,
    poll_interval: int,
    timeout_seconds: int,
) -> bool:
    started = time.time()
    last_status_line = ""
    while True:
        payload = request_json("GET", f"{bridge_url.rstrip('/')}/v1/state", timeout=120)
        jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
        tracked = [job for job in jobs if str(job.get("id")) in job_ids]
        counts: dict[str, int] = {}
        for job in tracked:
            status = str(job.get("status") or "unknown")
            counts[status] = counts.get(status, 0) + 1
        status_line = ", ".join(f"{key}={counts[key]}" for key in sorted(counts)) or "no tracked jobs"
        if status_line != last_status_line:
            print(f"[WAIT] {status_line}")
            last_status_line = status_line
        terminal_count = sum(1 for job in tracked if job.get("status") in {"completed", "failed"})
        if len(tracked) == len(job_ids) and terminal_count == len(job_ids):
            failed = [job for job in tracked if job.get("status") == "failed"]
            if failed:
                print(f"[DONE] {len(failed)} job(s) failed.")
                return False
            print("[DONE] all jobs completed.")
            return True
        if timeout_seconds > 0 and time.time() - started > timeout_seconds:
            print("[TIMEOUT] waiting for jobs timed out.", file=sys.stderr)
            return False
        time.sleep(max(1, poll_interval))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare Media AI Jimeng (即梦) video generation tasks and submit them to the local queue."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--bridge-url", default=DEFAULT_BRIDGE_URL)
    parser.add_argument("--prompt-file", default=DEFAULT_PROMPT_FILE)
    parser.add_argument("--cookie")
    parser.add_argument("--cookie-file")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--no-embed-cookie", action="store_true")
    parser.add_argument("--first-frame-id", action="append", help="First frame ID. Can be passed multiple times.")
    parser.add_argument("--first-frame-ids-file")
    parser.add_argument("--pose-id", action="append", help="Pose/movement ID. Can be passed multiple times.")
    parser.add_argument("--pose-ids-file")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--output-root", default=f"runs/media-ai-jimeng-video-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--no-auto-bridge", action="store_true")
    parser.add_argument("--no-wait", action="store_true")
    parser.add_argument("--poll-interval", type=int, default=15)
    parser.add_argument("--wait-timeout", type=int, default=0, help="Seconds to wait. 0 means no timeout.")
    return parser


def load_ids(path: str) -> list[str]:
    import pathlib
    text = pathlib.Path(path).read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text.startswith("["):
        payload = json.loads(text)
        if not isinstance(payload, list):
            raise ValueError(f"{path} must contain a JSON array or one id per line.")
        return [str(item).strip() for item in payload if str(item).strip()]
    ids: list[str] = []
    for line in text.splitlines():
        value = line.split("#", 1)[0].strip()
        if value:
            ids.append(value)
    return ids


def main() -> int:
    args = build_parser().parse_args()
    import pathlib

    # Resolve cookie
    cookie = args.cookie
    if not cookie and args.cookie_file:
        cookie = pathlib.Path(args.cookie_file).read_text(encoding="utf-8").strip()
    if not cookie:
        import os
        cookie = os.environ.get("MEDIA_AI_COOKIE")

    base_url = args.base_url.rstrip("/")
    prompt = pathlib.Path(args.prompt_file).read_text(encoding="utf-8").strip()
    output_root = pathlib.Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    client = MediaAIClient(base_url=base_url, cookie=cookie, timeout=args.timeout)

    # Resolve first frame IDs
    first_frame_ids: list[str] = list(args.first_frame_id or [])
    if args.first_frame_ids_file:
        first_frame_ids.extend(load_ids(args.first_frame_ids_file))

    # Resolve pose IDs
    pose_ids: list[str] = list(args.pose_id or [])
    if args.pose_ids_file:
        pose_ids.extend(load_ids(args.pose_ids_file))

    task_paths: list[pathlib.Path] = []
    skipped: list[dict[str, Any]] = []

    # Build first_frame -> pose mapping if both provided
    pose_map: dict[str, dict] = {}
    for pose_id in pose_ids:
        pose = client.fetch_pose(pose_id)
        if pose:
            pose_map[pose_id] = pose
        else:
            print(f"[WARN] Pose {pose_id} not found.")

    for first_frame_id in first_frame_ids:
        first_frame = client.fetch_first_frame(first_frame_id)
        if not first_frame:
            skipped.append({"firstFrameId": first_frame_id, "reason": "first_frame_not_found"})
            print(f"[SKIP] {first_frame_id} first frame not found.")
            continue

        # Get image URL
        first_frame_url = str(first_frame.get("url") or "")
        if not first_frame_url:
            skipped.append({"firstFrameId": first_frame_id, "reason": "missing_url"})
            print(f"[SKIP] {first_frame_id} first frame has no URL.")
            continue

        # Get associated product/IP info if available (for naming)
        product_id = str(first_frame.get("productId") or "")
        ip_id = str(first_frame.get("ipId") or "")
        product_name = product_id or first_frame_id

        # Determine which pose to use
        pose: dict | None = None
        movement_text = ""

        # Try to use pose_ids in order, cycling through if fewer poses than frames
        if pose_ids:
            # Use pose in round-robin fashion
            idx = first_frame_ids.index(first_frame_id)
            pose_id = pose_ids[idx % len(pose_ids)]
            pose = pose_map.get(pose_id)
            if pose:
                # Extract movement text from pose
                movement_text = _extract_movement(pose)
        elif product_id:
            # Try to find a pose from the product
            pass  # No automatic pose matching for now

        # Build task directory
        task_dir = output_root / (
            f"jimeng-video-{first_frame_id[:8]}"
        )
        assets_dir = task_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        # Download first frame image
        media_url = resolve_media_url(client.media_base_url, first_frame_url)
        ext = extension_from_url(media_url)
        first_frame_path = assets_dir / f"first-frame{ext}"

        try:
            client.download_file(media_url, first_frame_path, cookie=cookie)
        except Exception as e:
            skipped.append({
                "firstFrameId": first_frame_id,
                "reason": f"download_failed: {e}",
            })
            print(f"[SKIP] {first_frame_id} download failed: {e}")
            continue

        # Build movement display text for task.md
        movement_display = movement_text if movement_text else "[动作描述待填入]"

        # Write task.md
        lines = [
            f"# 即梦视频生成 / {product_name}",
            "",
            f"[首帧图]({first_frame_path.relative_to(task_dir).as_posix()})",
            "",
            f"**动作描述**: {movement_display}",
            "",
            prompt,
            "",
        ]
        case_path = task_dir / "task.md"
        case_path.write_text("\n".join(lines), encoding="utf-8")

        # Write .media-ai.json sidecar
        sidecar: dict[str, Any] = {
            "kind": "jimeng_video",
            "baseUrl": base_url,
            "productId": product_id,
            "ipId": ip_id,
            "firstFrameId": first_frame_id,
            "firstFrameUrl": media_url,
            "movement": movement_text,
        }
        if pose_ids:
            sidecar["poseId"] = pose_ids[first_frame_ids.index(first_frame_id) % len(pose_ids)]
        if cookie and not args.no_embed_cookie:
            sidecar["cookie"] = cookie
        case_path.with_suffix(".media-ai.json").write_text(
            json.dumps(sidecar, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        task_paths.append(case_path)
        print(f"[TASK] {first_frame_id} -> {case_path}")

    manifest = {
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "baseUrl": base_url,
        "bridgeUrl": args.bridge_url,
        "firstFrameCount": len(first_frame_ids),
        "promptFile": args.prompt_file,
        "taskFiles": [str(path) for path in task_paths],
        "skipped": skipped,
    }
    (output_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    if not task_paths:
        print("No new tasks to enqueue.")
        return 0
    if args.prepare_only:
        print(f"Prepared {len(task_paths)} task(s).")
        return 0

    ensure_bridge_running(args)
    response = request_json(
        "POST",
        f"{args.bridge_url.rstrip('/')}/v1/jobs",
        body={"caseFiles": [str(path) for path in task_paths]},
        timeout=args.timeout,
    )
    print(json.dumps(response, ensure_ascii=False, indent=2))
    print(f"Enqueued {len(task_paths)} task(s). Skipped {len(skipped)} item(s).")
    if args.no_wait:
        return 0

    jobs = response.get("jobs", []) if isinstance(response, dict) else []
    job_ids = {str(job.get("id")) for job in jobs if job.get("id")}
    if not job_ids:
        print("Bridge response did not include job ids; cannot wait for completion.", file=sys.stderr)
        return 1

    return 0 if wait_for_jobs(
        args.bridge_url,
        job_ids,
        poll_interval=args.poll_interval,
        timeout_seconds=args.wait_timeout,
    ) else 1


def _extract_movement(pose: dict) -> str:
    """Extract movement description from a pose dict."""
    # Try common fields
    for key in ("name", "title", "description", "movement", "action"):
        value = pose.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    # Fall back to material.name
    material = pose.get("material")
    if isinstance(material, dict):
        for key in ("name", "title", "description"):
            value = material.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


if __name__ == "__main__":
    raise SystemExit(main())