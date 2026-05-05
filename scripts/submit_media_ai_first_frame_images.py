from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from local_bridge.utils import (
    DEFAULT_BASE_URL,
    DEFAULT_BRIDGE_URL,
    download_file,
    ensure_bridge_running,
    extension_from_url,
    read_cookie,
    read_text,
    redact_sensitive,
    request_json,
    resolve_media_url,
    slugify,
    wait_for_jobs,
    normalize_list,
    load_ids,
    normalize_product_list,
)

from local_bridge.media_ai_client import MediaAIClient


DEFAULT_PROMPT_FILE = pathlib.Path("prompts/05_首帧图.md")


def fetch_products(args: argparse.Namespace, cookie: str | None) -> list[dict[str, Any]]:
    base_url = args.base_url.rstrip("/")
    product_ids = list(args.product_id or [])
    if args.product_ids_file:
        product_ids.extend(load_ids(pathlib.Path(args.product_ids_file)))

    if product_ids:
        products = []
        for product_id in dict.fromkeys(product_ids):
            products.append(
                request_json("GET", f"{base_url}/api/products/{product_id}", cookie=cookie, timeout=args.timeout)
            )
        return products

    query: dict[str, str] = {}
    if args.target_audience:
        query["targetAudience"] = args.target_audience
    if args.search:
        query["search"] = args.search
    suffix = f"?{urlencode(query)}" if query else ""
    products = normalize_list(
        request_json("GET", f"{base_url}/api/products{suffix}", cookie=cookie, timeout=args.timeout),
        ("products", "items", "data"),
        "product",
    )
    if args.limit:
        products = products[: args.limit]
    return products


def fetch_style_images(
    args: argparse.Namespace,
    cookie: str | None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    base_url = args.base_url.rstrip("/")
    products = fetch_products(args, cookie)
    product_map = {str(product.get("id") or ""): product for product in products if product.get("id")}
    wanted_ip_ids = set(args.ip_id or [])
    wanted_style_ids = set(args.style_image_id or [])
    style_images: list[dict[str, Any]] = []

    for product in products:
        product_id = str(product.get("id") or "")
        if not product_id:
            continue
        payload = request_json(
            "GET",
            f"{base_url}/api/products/{product_id}/generated-materials",
            cookie=cookie,
            timeout=args.timeout,
        )
        product_style_images = normalize_list(
            payload.get("styleImages") if isinstance(payload, dict) else [],
            (),
            "style image",
        )
        for style_image in product_style_images:
            ip_id = str(style_image.get("ipId") or "")
            style_image_id = str(style_image.get("id") or "")
            if wanted_ip_ids and ip_id not in wanted_ip_ids:
                continue
            if wanted_style_ids and style_image_id not in wanted_style_ids:
                continue
            style_image["productName"] = product.get("name")
            style_images.append(style_image)

    return style_images, product_map


def fetch_ip(base_url: str, ip_id: str, *, cookie: str | None, timeout: int) -> dict[str, Any]:
    return request_json("GET", f"{base_url.rstrip('/')}/api/ips/{ip_id}", cookie=cookie, timeout=timeout)


def fetch_scenes(url: str, *, cookie: str | None, timeout: int) -> list[dict[str, Any]]:
    payload = request_json("GET", url, cookie=cookie, timeout=timeout)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("scenes", "materials", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []
    return []


def scene_key(scene: dict[str, Any]) -> str:
    material = scene.get("material")
    if isinstance(material, dict) and material.get("id"):
        return str(material.get("id"))
    return str(scene.get("materialId") or scene.get("id") or "")


def scene_name(scene: dict[str, Any]) -> str:
    material = scene.get("material")
    if isinstance(material, dict):
        return str(material.get("name") or material.get("title") or material.get("id") or "")
    return str(scene.get("name") or scene.get("title") or scene.get("materialId") or scene.get("id") or "")


def scene_url(scene: dict[str, Any]) -> str:
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


def choose_scenes(
    product_scenes: list[dict[str, Any]],
    ip_scenes: list[dict[str, Any]],
    *,
    wanted_scene_ids: set[str],
) -> list[dict[str, Any]]:
    if product_scenes:
        ip_scene_ids = {scene_key(scene) for scene in ip_scenes if scene_key(scene)}
        chosen = [
            scene
            for scene in product_scenes
            if scene_key(scene) and scene_key(scene) in ip_scene_ids
        ]
    else:
        chosen = [scene for scene in ip_scenes if scene_key(scene)]

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for scene in chosen:
        current_scene_id = scene_key(scene)
        if not current_scene_id or current_scene_id in seen:
            continue
        if wanted_scene_ids and current_scene_id not in wanted_scene_ids:
            continue
        seen.add(current_scene_id)
        deduped.append(scene)
    return deduped


def existing_first_frames(
    base_url: str,
    product_id: str,
    style_image_id: str,
    *,
    cookie: str | None,
    timeout: int,
) -> list[dict[str, Any]]:
    query = urlencode({"styleImageId": style_image_id})
    payload = request_json(
        "GET",
        f"{base_url.rstrip('/')}/api/products/{product_id}/first-frames?{query}",
        cookie=cookie,
        timeout=timeout,
    )
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("firstFrames", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


# def build_task_file(
#     *,
#     args: argparse.Namespace,
#     cookie: str | None,
#     prompt: str,
#     style_image: dict[str, Any],
#     ip: dict[str, Any],
#     scene: dict[str, Any],
#     output_root: pathlib.Path,
# ) -> pathlib.Path | None:
#     base_url = args.base_url.rstrip("/")
#     product_id = str(style_image.get("productId") or "")
#     product_name = str(style_image.get("productName") or product_id)
#     ip_id = str(style_image.get("ipId") or ip.get("id") or "")
#     style_image_id = str(style_image.get("id") or "")
#     style_image_url = str(style_image.get("url") or "")
#     scene_id = scene_key(scene)
#     current_scene_name = scene_name(scene)
#     current_scene_url = scene_url(scene)
#
#     if not product_id or not ip_id or not style_image_id or not style_image_url or not scene_id or not current_scene_url:
#         return None
#
#     task_dir = output_root / (
#         f"{slugify(product_name)}-{product_id[:8]}__"
#         f"style-{style_image_id[:8]}__"
#         f"scene-{slugify(current_scene_name)}-{scene_id[:8]}"
#     )
#     assets_dir = task_dir / "assets"
#     assets_dir.mkdir(parents=True, exist_ok=True)
#
#     style_media_url = resolve_media_url(base_url, style_image_url)
#     scene_media_url = resolve_media_url(base_url, current_scene_url)
#     style_path = assets_dir / f"style-image{extension_from_url(style_media_url)}"
#     scene_path = assets_dir / f"scene-reference{extension_from_url(scene_media_url)}"
#     download_file(style_media_url, style_path, cookie=cookie, timeout=args.timeout)
#     download_file(scene_media_url, scene_path, cookie=cookie, timeout=args.timeout)
#
#     lines = [
#         f"# {product_name} / style-{style_image_id[:8]} / {current_scene_name} 首帧图",
#         "",
#         f"[图片一：模特定妆照]({style_path.relative_to(task_dir).as_posix()})",
#         f"[图片二：场景]({scene_path.relative_to(task_dir).as_posix()})",
#         "",
#         prompt,
#         "",
#     ]
#     case_path = task_dir / "task.md"
#     case_path.write_text("\n".join(lines), encoding="utf-8")
#
#     sidecar: dict[str, Any] = {
#         "kind": "first-frame-image",
#         "baseUrl": base_url,
#         "productId": product_id,
#         "productName": product_name,
#         "ipId": ip_id,
#         "ipNickname": ip.get("nickname"),
#         "styleImageId": style_image_id,
#         "styleImageUrl": style_media_url,
#         "sceneId": scene_id,
#         "sceneName": current_scene_name,
#         "sceneUrl": scene_media_url,
#         "uploadSubDir": args.upload_subdir,
#     }
#     if not args.no_embed_cookie and cookie:
#         sidecar["cookie"] = cookie
#     case_path.with_suffix(".media-ai.json").write_text(
#         json.dumps(sidecar, ensure_ascii=False, indent=2),
#         encoding="utf-8",
#     )
#     return case_path.resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare Media AI first-frame tasks and submit them to the local GPT image queue."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--bridge-url", default=DEFAULT_BRIDGE_URL)
    parser.add_argument("--prompt-file", default=str(DEFAULT_PROMPT_FILE))
    parser.add_argument("--cookie")
    parser.add_argument("--cookie-file")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--no-embed-cookie", action="store_true")
    parser.add_argument("--product-id", action="append")
    parser.add_argument("--product-ids-file")
    parser.add_argument("--ip-id", action="append")
    parser.add_argument("--style-image-id", action="append")
    parser.add_argument("--scene-id", action="append")
    parser.add_argument("--scene-ids-file")
    parser.add_argument("--target-audience", choices=["MENS", "WOMENS", "KIDS"])
    parser.add_argument("--search")
    parser.add_argument("--limit", type=int, help="Maximum number of products to inspect.")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--upload-subdir", default="first-frame-images")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Print job preview without enqueueing or downloading assets.")
    parser.add_argument("--no-auto-bridge", action="store_true")
    parser.add_argument("--no-wait", action="store_true")
    parser.add_argument("--poll-interval", type=int, default=15)
    parser.add_argument("--wait-timeout", type=int, default=300, help="Seconds to wait. 0 means no timeout.")
    parser.add_argument(
        "--output-root",
        default=f"runs/media-ai-first-frame-image-queue-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    cookie = read_cookie(args)
    prompt = read_text(pathlib.Path(args.prompt_file))
    base_url = args.base_url.rstrip("/")
    output_root = pathlib.Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    client = MediaAIClient(base_url=base_url, cookie=cookie, timeout=args.timeout)

    wanted_scene_ids = set(args.scene_id or [])
    if args.scene_ids_file:
        wanted_scene_ids.update(load_ids(pathlib.Path(args.scene_ids_file)))

    style_images, product_map = fetch_style_images(args, cookie)
    task_paths: list[pathlib.Path] = []
    skipped: list[dict[str, Any]] = []
    ip_cache: dict[str, dict[str, Any]] = {}
    product_scene_cache: dict[str, list[dict[str, Any]]] = {}
    ip_scene_cache: dict[str, list[dict[str, Any]]] = {}

    for style_image in style_images:
        product_id = str(style_image.get("productId") or "")
        product_name = str(style_image.get("productName") or product_id)
        ip_id = str(style_image.get("ipId") or "")
        style_image_id = str(style_image.get("id") or "")

        if not product_id or not ip_id or not style_image_id or not style_image.get("url"):
            skipped.append(
                {
                    "productId": product_id,
                    "productName": product_name,
                    "ipId": ip_id,
                    "styleImageId": style_image_id,
                    "reason": "missing_style_inputs",
                }
            )
            print(f"[SKIP] {style_image_id} missing product, IP, or style image URL.")
            continue

        if ip_id not in ip_cache:
            ip_cache[ip_id] = fetch_ip(base_url, ip_id, cookie=cookie, timeout=args.timeout)
        if product_id not in product_scene_cache:
            product_scene_cache[product_id] = fetch_scenes(
                f"{base_url}/api/products/{product_id}/scenes",
                cookie=cookie,
                timeout=args.timeout,
            )
        if ip_id not in ip_scene_cache:
            ip_scene_cache[ip_id] = fetch_scenes(
                f"{base_url}/api/ips/{ip_id}/scenes",
                cookie=cookie,
                timeout=args.timeout,
            )

        chosen_scenes = choose_scenes(
            product_scene_cache[product_id],
            ip_scene_cache[ip_id],
            wanted_scene_ids=wanted_scene_ids,
        )
        if not chosen_scenes:
            skipped.append(
                {
                    "productId": product_id,
                    "productName": product_name,
                    "ipId": ip_id,
                    "styleImageId": style_image_id,
                    "reason": "no_usable_scenes",
                }
            )
            print(f"[SKIP] {style_image_id} has no usable scene intersection.")
            continue

        for scene in chosen_scenes:
            current_scene_id = scene_key(scene)
            current_scene_name = scene_name(scene)

            existing = client.existing_first_frames(product_id, style_image_id, current_scene_id)
            if existing:
                skipped.append(
                    {
                        "productId": product_id,
                        "productName": product_name,
                        "ipId": ip_id,
                        "styleImageId": style_image_id,
                        "sceneId": current_scene_id,
                        "sceneName": current_scene_name,
                        "reason": "first_frame_exists",
                    }
                )
                print(f"[SKIP] {style_image_id} / {current_scene_id} {current_scene_name} already has first frame.")
                continue

            job_id = f"{slugify(product_name)}-{product_id[:8]}__style-{style_image_id}__scene-{slugify(current_scene_name)}-{current_scene_id[:8]}"
            case_path, _ = client.build_first_frame_task(
                style_image_id=style_image_id,
                scene_id=current_scene_id,
                output_root=output_root,
                job_id=job_id,
                prompt=prompt,
                force=True,
            )
            if not case_path:
                skipped.append(
                    {
                        "productId": product_id,
                        "productName": product_name,
                        "ipId": ip_id,
                        "styleImageId": style_image_id,
                        "sceneId": current_scene_id,
                        "sceneName": current_scene_name,
                        "reason": "missing_inputs",
                    }
                )
                print(f"[SKIP] {style_image_id} / {current_scene_id} {current_scene_name} missing style or scene image.")
                continue

            task_paths.append(case_path)
            print(f"[TASK] {style_image_id} / {current_scene_id} {current_scene_name} -> {case_path}")

    manifest = {
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "baseUrl": base_url,
        "bridgeUrl": args.bridge_url,
        "promptFile": args.prompt_file,
        "styleImageCount": len(style_images),
        "productCount": len(product_map),
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
    print(json.dumps(redact_sensitive(response), ensure_ascii=False, indent=2))
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


if __name__ == "__main__":
    raise SystemExit(main())
