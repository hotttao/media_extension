from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from submit_media_ai_model_images import (
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
)


from local_bridge.media_ai_client import MediaAIClient

DEFAULT_PROMPT_FILE = pathlib.Path("prompts/04_定妆图.md")


def normalize_list(payload: Any, keys: tuple[str, ...], label: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise ValueError(f"Cannot find {label} array in response.")


def load_ids(path: pathlib.Path) -> list[str]:
    text = read_text(path)
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


def fetch_model_images(args: argparse.Namespace, cookie: str | None) -> list[dict[str, Any]]:
    base_url = args.base_url.rstrip("/")
    products = fetch_products(args, cookie)
    model_images: list[dict[str, Any]] = []
    wanted_model_ids = set(args.model_image_id or [])

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
        for model_image in normalize_list(payload.get("modelImages") if isinstance(payload, dict) else [], (), "model image"):
            model_image_id = str(model_image.get("id") or "")
            if wanted_model_ids and model_image_id not in wanted_model_ids:
                continue
            model_image["productName"] = product.get("name")
            model_images.append(model_image)

    return model_images


def fetch_poses(args: argparse.Namespace, cookie: str | None) -> list[dict[str, Any]]:
    base_url = args.base_url.rstrip("/")
    pose_ids = set(args.pose_id or [])
    if args.pose_ids_file:
        pose_ids.update(load_ids(pathlib.Path(args.pose_ids_file)))

    poses = normalize_list(
        request_json("GET", f"{base_url}/api/materials?{urlencode({'type': 'POSE'})}", cookie=cookie, timeout=args.timeout),
        ("materials", "items", "data"),
        "pose",
    )
    if pose_ids:
        poses = [pose for pose in poses if str(pose.get("id") or "") in pose_ids]
    if args.pose_limit:
        poses = poses[: args.pose_limit]
    return poses


def existing_style_images(
    base_url: str,
    product_id: str,
    model_image_id: str,
    *,
    cookie: str | None,
    timeout: int,
) -> list[dict[str, Any]]:
    query = urlencode({"modelImageId": model_image_id})
    payload = request_json(
        "GET",
        f"{base_url.rstrip('/')}/api/products/{product_id}/style-images?{query}",
        cookie=cookie,
        timeout=timeout,
    )
    return payload if isinstance(payload, list) else []


# [DEPRECATED] Replaced by local_bridge.single_task.build_style_image_task
# def build_task_file(
#     *,
#     args: argparse.Namespace,
#     cookie: str | None,
#     prompt: str,
#     model_image: dict[str, Any],
#     pose: dict[str, Any],
#     output_root: pathlib.Path,
# ) -> pathlib.Path | None:
#     base_url = args.base_url.rstrip("/")
#     model_image_id = str(model_image.get("id") or "")
#     product_id = str(model_image.get("productId") or "")
#     product_name = str(model_image.get("productName") or product_id)
#     ip_id = str(model_image.get("ipId") or "")
#     pose_id = str(pose.get("id") or "")
#     pose_name = str(pose.get("name") or pose_id)
#     model_url = str(model_image.get("url") or "")
#     pose_url = str(pose.get("url") or "")
#     if not model_image_id or not product_id or not pose_id or not model_url or not pose_url:
#         return None
#
#     task_dir = output_root / (
#         f"{slugify(product_name)}-{product_id[:8]}__"
#         f"model-{model_image_id[:8]}__pose-{slugify(pose_name)}-{pose_id[:8]}"
#     )
#     assets_dir = task_dir / "assets"
#     assets_dir.mkdir(parents=True, exist_ok=True)
#
#     model_media_url = resolve_media_url(base_url, model_url)
#     pose_media_url = resolve_media_url(base_url, pose_url)
#     model_path = assets_dir / f"model-image{extension_from_url(model_media_url)}"
#     pose_path = assets_dir / f"pose-reference{extension_from_url(pose_media_url)}"
#     download_file(model_media_url, model_path, cookie=cookie, timeout=args.timeout)
#     download_file(pose_media_url, pose_path, cookie=cookie, timeout=args.timeout)
#
#     lines = [
#         f"# {product_name} / {pose_name} 定妆图",
#         "",
#         f"[图片一：换装好的模特图]({model_path.relative_to(task_dir).as_posix()})",
#         f"[图片二：姿势参考图]({pose_path.relative_to(task_dir).as_posix()})",
#         "",
#         prompt,
#         "",
#     ]
#     case_path = task_dir / "task.md"
#     case_path.write_text("\n".join(lines), encoding="utf-8")
#
#     sidecar: dict[str, Any] = {
#         "kind": "style-image",
#         "baseUrl": base_url,
#         "productId": product_id,
#         "productName": product_name,
#         "ipId": ip_id,
#         "modelImageId": model_image_id,
#         "poseId": pose_id,
#         "poseName": pose_name,
#         "uploadSubDir": args.upload_subdir,
#         "modelImageUrl": model_media_url,
#         "poseUrl": pose_media_url,
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
        description="Prepare Media AI style-image tasks and submit them to the local GPT image queue."
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
    parser.add_argument("--model-image-id", action="append")
    parser.add_argument("--pose-id", action="append")
    parser.add_argument("--pose-ids-file")
    parser.add_argument("--target-audience", choices=["MENS", "WOMENS", "KIDS"])
    parser.add_argument("--search")
    parser.add_argument("--limit", type=int, help="Maximum number of products to inspect.")
    parser.add_argument("--pose-limit", type=int)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--upload-subdir", default="style-images")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--no-auto-bridge", action="store_true")
    parser.add_argument("--no-wait", action="store_true")
    parser.add_argument("--poll-interval", type=int, default=15)
    parser.add_argument("--wait-timeout", type=int, default=300, help="Seconds to wait. 0 means no timeout.")
    parser.add_argument(
        "--output-root",
        default=f"runs/media-ai-style-image-queue-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
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

    model_images = fetch_model_images(args, cookie)
    poses = fetch_poses(args, cookie)
    task_paths: list[pathlib.Path] = []
    skipped: list[dict[str, Any]] = []

    for model_image in model_images:
        product_id = str(model_image.get("productId") or "")
        model_image_id = str(model_image.get("id") or "")
        product_name = str(model_image.get("productName") or product_id)
        existing = client.existing_style_images(product_id, model_image_id)
        existing_pose_ids = {str(item.get("poseId") or "") for item in existing}

        for pose in poses:
            pose_id = str(pose.get("id") or "")
            pose_name = str(pose.get("name") or pose_id)
            if pose_id in existing_pose_ids:
                skipped.append(
                    {
                        "productId": product_id,
                        "productName": product_name,
                        "modelImageId": model_image_id,
                        "poseId": pose_id,
                        "poseName": pose_name,
                        "reason": "style_image_exists",
                    }
                )
                print(f"[SKIP] {model_image_id} / {pose_id} {pose_name} already has style image.")
                continue

            case_path, _ = client.build_style_image_task(
                model_image_id=model_image_id,
                pose_id=pose_id,
                output_root=output_root,
                prompt=prompt,
                force=True,
            )
            if not case_path:
                skipped.append(
                    {
                        "productId": product_id,
                        "productName": product_name,
                        "modelImageId": model_image_id,
                        "poseId": pose_id,
                        "poseName": pose_name,
                        "reason": "missing_inputs",
                    }
                )
                print(f"[SKIP] {model_image_id} / {pose_id} {pose_name} missing model or pose image.")
                continue
            task_paths.append(case_path)
            print(f"[TASK] {model_image_id} / {pose_id} {pose_name} -> {case_path}")

    manifest = {
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "baseUrl": base_url,
        "bridgeUrl": args.bridge_url,
        "promptFile": args.prompt_file,
        "modelImageCount": len(model_images),
        "poseCount": len(poses),
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
