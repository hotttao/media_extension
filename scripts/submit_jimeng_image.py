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
DEFAULT_PROMPT_FILE = "prompts/08_即梦文生图"


# ---------------------------------------------------------------------------
# Shared utilities (copied from submit_media_ai_model_images.py for standalone use)
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
        description="Prepare Media AI Jimeng (即梦) image generation tasks and submit them to the local queue."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--bridge-url", default=DEFAULT_BRIDGE_URL)
    parser.add_argument("--prompt-file", default=DEFAULT_PROMPT_FILE)
    parser.add_argument("--cookie")
    parser.add_argument("--cookie-file")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--no-embed-cookie", action="store_true")
    parser.add_argument("--style-image-id", action="append", help="Style image ID. Can be passed multiple times.")
    parser.add_argument("--style-image-ids-file")
    parser.add_argument("--scene-id", action="append", help="Scene ID. Can be passed multiple times.")
    parser.add_argument("--scene-ids-file")
    parser.add_argument("--pose-id", action="append", help="Pose ID. Can be passed multiple times.")
    parser.add_argument("--pose-ids-file")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--output-root", default=f"runs/media-ai-jimeng-image-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
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

    # Resolve style image IDs
    style_image_ids: list[str] = list(args.style_image_id or [])
    if args.style_image_ids_file:
        style_image_ids.extend(load_ids(args.style_image_ids_file))

    # Resolve scene IDs
    scene_ids: set[str] = set(args.scene_id or [])
    if args.scene_ids_file:
        scene_ids.update(load_ids(args.scene_ids_file))

    # Resolve pose IDs
    pose_ids: set[str] = set(args.pose_id or [])
    if args.pose_ids_file:
        pose_ids.update(load_ids(args.pose_ids_file))

    # Fetch poses
    poses: dict[str, dict] = {}
    if pose_ids:
        for pose_id in pose_ids:
            pose = client.fetch_pose(pose_id)
            if pose:
                poses[str(pose.get("id") or "")] = pose

    task_paths: list[pathlib.Path] = []
    skipped: list[dict[str, Any]] = []

    for style_image_id in style_image_ids:
        style_image = client.fetch_style_image(style_image_id)
        if not style_image:
            skipped.append({"styleImageId": style_image_id, "reason": "style_image_not_found"})
            print(f"[SKIP] {style_image_id} style image not found.")
            continue

        product_id = str(style_image.get("productId") or "")
        ip_id = str(style_image.get("ipId") or "")
        style_image_url = str(style_image.get("url") or "")
        if not product_id or not ip_id or not style_image_url:
            skipped.append({"styleImageId": style_image_id, "reason": "missing_fields"})
            print(f"[SKIP] {style_image_id} missing productId, ipId, or url.")
            continue

        # Fetch IP for fullBodyUrl (person image)
        ip = client.fetch_ip(ip_id)
        if not ip:
            skipped.append({"styleImageId": style_image_id, "ipId": ip_id, "reason": "ip_not_found"})
            print(f"[SKIP] {style_image_id} IP {ip_id} not found.")
            continue
        ip_full_body_url = ip.get("fullBodyUrl")
        if not ip_full_body_url:
            skipped.append({"styleImageId": style_image_id, "ipId": ip_id, "reason": "ip_missing_full_body_url"})
            print(f"[SKIP] {style_image_id} IP {ip_id} missing fullBodyUrl.")
            continue

        # Fetch product for main image (clothing)
        product = client.fetch_product(product_id)
        if not product:
            skipped.append({"styleImageId": style_image_id, "productId": product_id, "reason": "product_not_found"})
            print(f"[SKIP] {style_image_id} Product {product_id} not found.")
            continue
        product_name = str(product.get("name") or product_id)
        images = product.get("images") or []
        if not isinstance(images, list) or not images:
            skipped.append({"styleImageId": style_image_id, "productId": product_id, "reason": "product_no_images"})
            print(f"[SKIP] {style_image_id} Product {product_id} has no images.")
            continue
        image_items = [item for item in images if isinstance(item, dict) and item.get("url")]
        if not image_items:
            skipped.append({"styleImageId": style_image_id, "productId": product_id, "reason": "product_no_valid_images"})
            print(f"[SKIP] {style_image_id} Product {product_id} has no valid image URLs.")
            continue
        main_image = next((item for item in image_items if item.get("isMain") is True), None)
        if main_image is None:
            main_image = sorted(image_items, key=lambda x: int(x.get("order") or 999999))[0]
        main_image_url = str(main_image.get("url") or "")

        # Determine which scenes to use
        if scene_ids:
            scenes_to_use = []
            for scene_id in scene_ids:
                scene = client.fetch_scene(scene_id)
                if scene:
                    scenes_to_use.append(scene)
        else:
            # Use all product scenes + ip scenes intersection
            try:
                product_scenes_payload = client.request_json("GET", f"/api/products/{product_id}/scenes")
                product_scenes = _extract_scenes(product_scenes_payload)
            except Exception:
                product_scenes = []
            try:
                ip_scenes_payload = client.request_json("GET", f"/api/ips/{ip_id}/scenes")
                ip_scenes = _extract_scenes(ip_scenes_payload)
            except Exception:
                ip_scenes = []
            scenes_to_use = _intersect_scenes(product_scenes, ip_scenes)

        if not scenes_to_use:
            skipped.append({"styleImageId": style_image_id, "reason": "no_usable_scenes"})
            print(f"[SKIP] {style_image_id} has no usable scene intersection.")
            continue

        for scene in scenes_to_use:
            scene_id = _scene_key(scene)
            scene_name_val = _scene_name(scene)
            scene_url_val = _scene_url(scene)

            # Determine which poses to use
            if pose_ids:
                poses_to_use = [(pid, poses.get(pid)) for pid in pose_ids if poses.get(pid)]
            else:
                poses_to_use = [(None, None)]  # No pose substitution

            for pose_id, pose in poses_to_use:
                # Build effective prompt with pose description
                effective_prompt = prompt
                if pose:
                    pose_name = str(pose.get("name") or "")
                    pose_desc = str(pose.get("description") or pose.get("prompt") or pose_name)
                    if pose_desc and pose_name:
                        effective_prompt = effective_prompt.replace("{pose_description}", pose_desc)
                        effective_prompt = effective_prompt.replace("{pose_name}", pose_name)

                # Build task directory
                dir_parts = [
                    f"{slugify(product_name)}-{product_id[:8]}",
                    f"jimeng-{style_image_id[:8]}",
                    f"scene-{slugify(scene_name_val)}-{scene_id[:8]}",
                ]
                if pose_id:
                    dir_parts.append(f"pose-{slugify(pose_name)}-{pose_id[:8]}")
                task_dir = output_root / "__".join(dir_parts)
                assets_dir = task_dir / "assets"
                assets_dir.mkdir(parents=True, exist_ok=True)

                # Download 3 reference images
                ip_media_url = resolve_media_url(client.media_base_url, str(ip_full_body_url))
                main_media_url = resolve_media_url(client.media_base_url, main_image_url)
                scene_media_url = resolve_media_url(client.media_base_url, scene_url_val)

                ip_path = assets_dir / f"ip-full-body{extension_from_url(ip_media_url)}"
                main_path = assets_dir / f"product-main{extension_from_url(main_media_url)}"
                scene_path = assets_dir / f"scene-reference{extension_from_url(scene_media_url)}"

                try:
                    client.download_file(ip_media_url, ip_path, cookie=cookie)
                    client.download_file(main_media_url, main_path, cookie=cookie)
                    client.download_file(scene_media_url, scene_path, cookie=cookie)
                except Exception as e:
                    skipped.append({
                        "styleImageId": style_image_id,
                        "sceneId": scene_id,
                        "poseId": pose_id,
                        "reason": f"download_failed: {e}",
                    })
                    print(f"[SKIP] {style_image_id} / {scene_id} / pose {pose_id} download failed: {e}")
                    continue

                # Write task.md
                lines = [
                    f"# {product_name} / jimeng / {scene_name_val}",
                    "",
                    f"[图片一：人物]({ip_path.relative_to(task_dir).as_posix()})",
                    f"[图片二：服装]({main_path.relative_to(task_dir).as_posix()})",
                    f"[图片三：场景]({scene_path.relative_to(task_dir).as_posix()})",
                    "",
                    effective_prompt,
                    "",
                ]
                case_path = task_dir / "task.md"
                case_path.write_text("\n".join(lines), encoding="utf-8")

                # Write .media-ai.json sidecar
                sidecar: dict[str, Any] = {
                    "kind": "jimeng_image",
                    "baseUrl": base_url,
                    "productId": product_id,
                    "productName": product_name,
                    "ipId": ip_id,
                    "styleImageId": style_image_id,
                    "styleImageUrl": ip_media_url,
                    "sceneId": scene_id,
                    "sceneName": scene_name_val,
                    "sceneUrl": scene_media_url,
                    "uploadSubDir": "first-frames",
                }
                if pose_id:
                    sidecar["poseId"] = pose_id
                    sidecar["poseName"] = pose_name
                    sidecar["poseDescription"] = pose_desc
                if cookie and not args.no_embed_cookie:
                    sidecar["cookie"] = cookie
                case_path.with_suffix(".media-ai.json").write_text(
                    json.dumps(sidecar, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

                task_paths.append(case_path)
                pose_label = f" pose-{pose_id[:8]}" if pose_id else ""
                print(f"[TASK] {style_image_id} / {scene_id} {scene_name_val}{pose_label} -> {case_path}")

    manifest = {
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "baseUrl": base_url,
        "bridgeUrl": args.bridge_url,
        "styleImageCount": len(style_image_ids),
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


def _extract_scenes(payload) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("scenes", "materials", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _scene_key(scene: dict) -> str:
    material = scene.get("material")
    if isinstance(material, dict) and material.get("id"):
        return str(material.get("id"))
    return str(scene.get("materialId") or scene.get("id") or "")


def _scene_name(scene: dict) -> str:
    material = scene.get("material")
    if isinstance(material, dict):
        return str(material.get("name") or material.get("title") or material.get("id") or "")
    return str(scene.get("name") or scene.get("title") or scene.get("materialId") or scene.get("id") or "")


def _scene_url(scene: dict) -> str:
    material = scene.get("material")
    if isinstance(material, dict):
        for key in ("url", "imageUrl", "image", "coverUrl"):
            value = material.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    for key in ("url", "imageUrl", "image", "coverUrl"):
        value = scene.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _intersect_scenes(product_scenes: list[dict], ip_scenes: list[dict]) -> list[dict]:
    if product_scenes:
        ip_scene_ids = {_scene_key(s) for s in ip_scenes if _scene_key(s)}
        chosen = [s for s in product_scenes if _scene_key(s) and _scene_key(s) in ip_scene_ids]
    else:
        chosen = [s for s in ip_scenes if _scene_key(s)]
    deduped: list[dict] = []
    seen: set[str] = set()
    for scene in chosen:
        sid = _scene_key(scene)
        if not sid or sid in seen:
            continue
        seen.add(sid)
        deduped.append(scene)
    return deduped


if __name__ == "__main__":
    raise SystemExit(main())