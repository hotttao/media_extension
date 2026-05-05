from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
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
    normalize_product_list,
    normalize_ip_list,
    load_ids,
)

DEFAULT_BASE_URL = "http://localhost:3000"
DEFAULT_BRIDGE_URL = "http://127.0.0.1:8765"
DEFAULT_PROMPT_FILE = Path("prompts/03_模特图.md")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare Media AI model-image tasks and submit them to the local queue."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--bridge-url", default=DEFAULT_BRIDGE_URL)
    parser.add_argument("--ip-id", action="append", help="Virtual IP id filter. Omit to use all virtual IPs.")
    parser.add_argument("--prompt-file", default=str(DEFAULT_PROMPT_FILE))
    parser.add_argument("--cookie", help="Media AI browser Cookie header value.")
    parser.add_argument("--cookie-file", help="File containing the Media AI Cookie header value.")
    parser.add_argument("--env-file", default=".env", help="Env file containing MEDIA_AI_USER/MEDIA_AI_PASSWORD.")
    parser.add_argument("--no-embed-cookie", action="store_true", help="Do not store auth cookie in task sidecars.")
    parser.add_argument("--product-id", action="append", help="Product id. Can be passed multiple times.")
    parser.add_argument("--product-ids-file", help="Text file with one product id per line, or a JSON array.")
    parser.add_argument("--target-audience", choices=["MENS", "WOMENS", "KIDS"])
    parser.add_argument("--search", help="Search term used when fetching products from /api/products.")
    parser.add_argument("--limit", type=int, help="Maximum number of fetched products to inspect.")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--no-detail-images", action="store_true")
    parser.add_argument("--max-detail-images", type=int, default=6)
    parser.add_argument("--upload-subdir", default="model-images")
    parser.add_argument("--prepare-only", action="store_true", help="Create task files but do not enqueue them.")
    parser.add_argument("--dry-run", action="store_true", help="Print job preview without enqueueing.")
    parser.add_argument("--no-wait", action="store_true", help="Submit tasks and exit without waiting for completion.")
    parser.add_argument("--poll-interval", type=int, default=15)
    parser.add_argument("--wait-timeout", type=int, default=300, help="Seconds to wait. 0 means no timeout.")
    parser.add_argument(
        "--output-root",
        default=f"runs/media-ai-model-image-queue-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
    )
    return parser


def fetch_products(args: argparse.Namespace, cookie: str | None) -> list[dict[str, Any]]:
    base_url = args.base_url.rstrip("/")
    product_ids = list(args.product_id or [])
    if args.product_ids_file:
        product_ids.extend(load_ids(args.product_ids_file))

    if product_ids:
        products = []
        for product_id in dict.fromkeys(product_ids):
            products.append(
                request_json(
                    "GET",
                    f"{base_url}/api/products/{product_id}",
                    cookie=cookie,
                    timeout=args.timeout,
                )
            )
        return products

    query: dict[str, str] = {}
    if args.target_audience:
        query["targetAudience"] = args.target_audience
    if args.search:
        query["search"] = args.search
    from urllib.parse import urlencode
    suffix = f"?{urlencode(query)}" if query else ""
    products = normalize_product_list(
        request_json("GET", f"{base_url}/api/products{suffix}", cookie=cookie, timeout=args.timeout)
    )
    if args.limit:
        products = products[: args.limit]
    return products


def fetch_ips(args: argparse.Namespace, cookie: str | None) -> list[dict[str, Any]]:
    base_url = args.base_url.rstrip("/")
    ip_ids = list(args.ip_id or [])
    if ip_ids:
        ips = []
        for ip_id in dict.fromkeys(ip_ids):
            ips.append(
                request_json(
                    "GET",
                    f"{base_url}/api/ips/{ip_id}",
                    cookie=cookie,
                    timeout=args.timeout,
                )
            )
        return ips

    return normalize_ip_list(
        request_json("GET", f"{base_url}/api/ips", cookie=cookie, timeout=args.timeout)
    )


def main() -> int:
    args = build_parser().parse_args()

    cookie = read_cookie(args)
    prompt = Path(args.prompt_file).read_text(encoding="utf-8").strip()
    base_url = args.base_url.rstrip("/")
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    client = MediaAIClient(base_url=base_url, cookie=cookie, timeout=args.timeout)
    client.resolve_cookie()  # auto-login via .env if needed

    products = fetch_products(args, cookie)
    ips = fetch_ips(args, cookie)

    task_paths: list[Path] = []
    skipped: list[dict[str, Any]] = []
    for product in products:
        product_id = str(product.get("id") or "")
        product_name = str(product.get("name") or product_id)
        for ip in ips:
            ip_id = str(ip.get("id") or "")
            ip_name = str(ip.get("nickname") or ip_id)
            if not ip.get("fullBodyUrl"):
                skipped.append(
                    {
                        "productId": product_id,
                        "productName": product_name,
                        "ipId": ip_id,
                        "ipNickname": ip_name,
                        "reason": "ip_missing_full_body_url",
                    }
                )
                print(f"[SKIP] {product_id} {product_name} / {ip_id} {ip_name} missing IP fullBodyUrl.")
                continue

            existing = client.existing_model_images(product_id, ip_id)
            if existing:
                skipped.append(
                    {
                        "productId": product_id,
                        "productName": product_name,
                        "ipId": ip_id,
                        "ipNickname": ip_name,
                        "reason": "model_image_exists",
                        "count": len(existing),
                    }
                )
                print(
                    f"[SKIP] {product_id} {product_name} / {ip_id} {ip_name} "
                    f"already has {len(existing)} model image(s)."
                )
                continue

            job_id = f"{slugify(product_name)}-{product_id[:8]}__{slugify(ip_name)}-{ip_id[:8]}"
            case_path, _ = client.build_model_image_task(
                product_id=str(product.get("id") or ""),
                ip_id=str(ip.get("id") or ""),
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
                        "ipNickname": ip_name,
                        "reason": "missing_inputs",
                    }
                )
                print(f"[SKIP] {product_id} {product_name} / {ip_id} {ip_name} missing product image or IP image.")
                continue
            task_paths.append(case_path)
            print(f"[TASK] {product_id} {product_name} / {ip_id} {ip_name} -> {case_path}")

    manifest = {
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "baseUrl": base_url,
        "bridgeUrl": args.bridge_url,
        "ipIds": [str(ip.get("id")) for ip in ips],
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
    print(f"Enqueued {len(task_paths)} task(s). Skipped {len(skipped)} product(s).")
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