from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Any

from local_bridge.media_ai_client import MediaAIClient
from local_bridge.single_task import (
    resolve_media_url,
    extension_from_url,
    slugify,
)
from local_bridge.utils import (
    request_json,
    can_reach_bridge,
    ensure_bridge_running,
    wait_for_jobs,
    read_cookie,
    load_ids,
)

DEFAULT_BASE_URL = "http://localhost:3000"
DEFAULT_BRIDGE_URL = "http://127.0.0.1:8765"
DEFAULT_PROMPT_FILE = "prompts/06_文生视频提示词.md"


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
    parser.add_argument("--output-root", default="runs")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Print job preview without enqueueing or downloading assets.")
    parser.add_argument("--no-auto-bridge", action="store_true")
    parser.add_argument("--no-wait", action="store_true")
    parser.add_argument("--poll-interval", type=int, default=15)
    parser.add_argument("--wait-timeout", type=int, default=0, help="Seconds to wait. 0 means no timeout.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    import pathlib

    # Resolve cookie — delegates to utils.read_cookie which handles all sources
    cookie = read_cookie(args)

    base_url = args.base_url.rstrip("/")
    prompt = pathlib.Path(args.prompt_file).read_text(encoding="utf-8").strip()
    output_root = pathlib.Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    client = MediaAIClient(base_url=base_url, cookie=cookie, timeout=args.timeout)
    client.resolve_cookie()  # auto-login via .env if needed

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
        job_id = f"jimeng-vid-{first_frame_id[:8]}"
        task_dir = output_root / job_id
        input_dir = task_dir / "input"
        assets_dir = input_dir / "assets"
        task_dir.mkdir(parents=True, exist_ok=True)
        input_dir.mkdir(parents=True, exist_ok=True)
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
            f"[首帧图]({first_frame_path.relative_to(input_dir).as_posix()})",
            "",
            f"**动作描述**: {movement_display}",
            "",
            prompt,
            "",
        ]
        case_path = input_dir / "task.md"
        case_path.write_text("\n".join(lines), encoding="utf-8")

        # Write .media-ai.json sidecar (kind="video" + platform="jimeng")
        sidecar: dict[str, Any] = {
            "kind": "video",
            "platform": "jimeng",
            "baseUrl": base_url,
            "productId": product_id,
            "ipId": ip_id,
            "firstFrameId": first_frame_id,
            "firstFrameUrl": media_url,
            "uploadSubDir": "videos",
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
    if args.dry_run:
        print(f"[DRY-RUN] Would enqueue {len(task_paths)} task(s):")
        for path in task_paths:
            print(f"  - {path}")
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