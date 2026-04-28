from __future__ import annotations

import argparse
import json
import mimetypes
import os
import pathlib
import re
import subprocess
import sys
import time
from http.cookiejar import CookieJar
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlparse, urlunparse
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

from local_bridge.media_ai_client import MediaAIClient

DEFAULT_BASE_URL = "http://localhost:3000"
DEFAULT_BRIDGE_URL = "http://127.0.0.1:8765"
DEFAULT_PROMPT_FILE = pathlib.Path("prompts/03_模特图.md")


def read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def parse_env_file(path: pathlib.Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def cookie_header_from_jar(cookie_jar: CookieJar) -> str:
    return "; ".join(f"{cookie.name}={cookie.value}" for cookie in cookie_jar)


def login_media_ai(base_url: str, *, email: str, password: str, timeout: int) -> str:
    cookie_jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookie_jar))
    base_url = base_url.rstrip("/")

    csrf_request = Request(f"{base_url}/api/auth/csrf", headers={"Accept": "application/json"}, method="GET")
    with opener.open(csrf_request, timeout=timeout) as response:
        csrf_payload = json.loads(response.read().decode("utf-8"))
    csrf_token = csrf_payload.get("csrfToken")
    if not csrf_token:
        raise RuntimeError(f"NextAuth CSRF response did not include csrfToken: {csrf_payload}")

    form = urlencode(
        {
            "csrfToken": csrf_token,
            "email": email,
            "password": password,
            "redirect": "false",
            "json": "true",
        }
    ).encode("utf-8")
    login_request = Request(
        f"{base_url}/api/auth/callback/credentials",
        data=form,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with opener.open(login_request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
        if response.status >= 400:
            raise RuntimeError(f"Login failed with HTTP {response.status}: {raw}")

    cookie = cookie_header_from_jar(cookie_jar)
    if "next-auth.session-token=" not in cookie and "__Secure-next-auth.session-token=" not in cookie:
        raise RuntimeError("Login did not produce a NextAuth session cookie.")
    return cookie


def read_cookie(args: argparse.Namespace) -> str | None:
    if args.cookie:
        return args.cookie.strip()
    if args.cookie_file:
        return read_text(pathlib.Path(args.cookie_file))
    cookie = os.environ.get("MEDIA_AI_COOKIE")
    if cookie:
        return cookie.strip()

    env_values = parse_env_file(pathlib.Path(args.env_file))
    user = os.environ.get("MEDIA_AI_USER") or env_values.get("MEDIA_AI_USER")
    password = os.environ.get("MEDIA_AI_PASSWORD") or env_values.get("MEDIA_AI_PASSWORD")
    if user and password:
        return login_media_ai(args.base_url, email=user, password=password, timeout=args.timeout)

    return None


def request_json(
    method: str,
    url: str,
    *,
    cookie: str | None = None,
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


def can_reach_bridge(bridge_url: str, timeout: int = 3) -> bool:
    try:
        request_json("GET", f"{bridge_url.rstrip('/')}/health", timeout=timeout)
        return True
    except Exception:
        return False


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "<redacted>" if key.lower() == "cookie" else redact_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    return value


def ensure_bridge_running(args: argparse.Namespace) -> subprocess.Popen[Any] | None:
    if can_reach_bridge(args.bridge_url):
        return None
    if args.no_auto_bridge:
        raise RuntimeError(
            f"GPT image queue bridge is not running: {args.bridge_url}. "
            "Start it with: python local_bridge\\server.py serve"
        )

    log_dir = pathlib.Path(args.output_root)
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / "auto-local-bridge.log"
    log_file = log_path.open("a", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            "local_bridge/server.py",
            "serve",
            "--output-root",
            "runs",
        ],
        cwd=pathlib.Path.cwd(),
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )

    for _ in range(20):
        if process.poll() is not None:
            raise RuntimeError(f"Failed to start local bridge. See {log_path}.")
        if can_reach_bridge(args.bridge_url):
            print(f"[BRIDGE] started local queue bridge at {args.bridge_url}. Log: {log_path}")
            return process
        time.sleep(0.5)

    raise RuntimeError(f"Timed out waiting for local bridge to start. See {log_path}.")


def normalize_product_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("products", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise ValueError("Cannot find a product array in /api/products response.")


def normalize_ip_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("ips", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise ValueError("Cannot find a virtual IP array in /api/ips response.")


def load_product_ids(path: pathlib.Path) -> list[str]:
    text = read_text(path)
    if not text:
        return []
    if text.startswith("["):
        payload = json.loads(text)
        if not isinstance(payload, list):
            raise ValueError(f"{path} must contain a JSON array or one product id per line.")
        return [str(item).strip() for item in payload if str(item).strip()]

    ids: list[str] = []
    for line in text.splitlines():
        value = line.split("#", 1)[0].strip()
        if value:
            ids.append(value)
    return ids


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff_-]+", "-", value).strip("-")
    return cleaned or "product"


def resolve_media_url(base_url: str, value: str) -> str:
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return urljoin(base_url.rstrip("/") + "/", value.lstrip("/"))


def quote_url(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            quote(parsed.path, safe="/:%"),
            parsed.params,
            quote(parsed.query, safe="=&?/:;%"),
            parsed.fragment,
        )
    )


def download_file(url: str, target: pathlib.Path, *, cookie: str | None, timeout: int) -> None:
    headers = {"Accept": "*/*"}
    if cookie:
        headers["Cookie"] = cookie
    request = Request(quote_url(url), headers=headers, method="GET")
    with urlopen(request, timeout=timeout) as response:
        target.write_bytes(response.read())


def extension_from_url(url: str, fallback: str = ".png") -> str:
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


def product_sort_key(image: dict[str, Any]) -> tuple[int, str]:
    order = image.get("order")
    return (int(order) if isinstance(order, int) else 999999, str(image.get("id") or ""))


def select_images(
    product: dict[str, Any],
    *,
    include_detail_images: bool,
    max_detail_images: int,
) -> tuple[str | None, list[str]]:
    images = product.get("images") or []
    if not isinstance(images, list):
        return None, []

    image_items = [item for item in images if isinstance(item, dict) and item.get("url")]
    if not image_items:
        return None, []

    main = next((item for item in image_items if item.get("isMain") is True), None)
    if main is None:
        main = sorted(image_items, key=product_sort_key)[0]

    main_url = str(main["url"])
    if not include_detail_images:
        return main_url, []

    detail_urls = [
        str(item["url"])
        for item in sorted(image_items, key=product_sort_key)
        if str(item["url"]) != main_url
    ]
    return main_url, detail_urls[:max_detail_images]


def fetch_products(args: argparse.Namespace, cookie: str | None) -> list[dict[str, Any]]:
    base_url = args.base_url.rstrip("/")
    product_ids = list(args.product_id or [])
    if args.product_ids_file:
        product_ids.extend(load_product_ids(pathlib.Path(args.product_ids_file)))

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


def existing_model_images(
    base_url: str,
    product_id: str,
    ip_id: str,
    *,
    cookie: str | None,
    timeout: int,
) -> list[dict[str, Any]]:
    query = urlencode({"ipId": ip_id})
    payload = request_json(
        "GET",
        f"{base_url.rstrip('/')}/api/products/{product_id}/model-images?{query}",
        cookie=cookie,
        timeout=timeout,
    )
    return payload if isinstance(payload, list) else []


# def build_task_file(
#     *,
#     args: argparse.Namespace,
#     cookie: str | None,
#     prompt: str,
#     ip: dict[str, Any],
#     product: dict[str, Any],
#     output_root: pathlib.Path,
# ) -> pathlib.Path | None:
#     base_url = args.base_url.rstrip("/")
#     product_id = str(product.get("id") or "")
#     product_name = str(product.get("name") or product_id)
#     ip_id = str(ip.get("id") or "")
#     ip_name = str(ip.get("nickname") or ip_id)
#     main_image_url, detail_image_urls = select_images(
#         product,
#         include_detail_images=not args.no_detail_images,
#         max_detail_images=args.max_detail_images,
#     )
#     ip_full_body_url = ip.get("fullBodyUrl")
#
#     if not product_id or not ip_id or not main_image_url or not ip_full_body_url:
#         return None
#
#     task_dir = output_root / f"{slugify(product_name)}-{product_id[:8]}__{slugify(ip_name)}-{ip_id[:8]}"
#     assets_dir = task_dir / "assets"
#     assets_dir.mkdir(parents=True, exist_ok=True)
#
#     ip_url = resolve_media_url(base_url, str(ip_full_body_url))
#     main_url = resolve_media_url(base_url, main_image_url)
#     detail_urls = [resolve_media_url(base_url, item) for item in detail_image_urls]
#
#     ip_path = assets_dir / f"model-reference{extension_from_url(ip_url)}"
#     main_path = assets_dir / f"product-main{extension_from_url(main_url)}"
#     download_file(ip_url, ip_path, cookie=cookie, timeout=args.timeout)
#     download_file(main_url, main_path, cookie=cookie, timeout=args.timeout)
#
#     detail_paths: list[pathlib.Path] = []
#     for index, url in enumerate(detail_urls, start=1):
#         detail_path = assets_dir / f"product-detail-{index:02d}{extension_from_url(url)}"
#         download_file(url, detail_path, cookie=cookie, timeout=args.timeout)
#         detail_paths.append(detail_path)
#
#     lines = [
#         f"# {product_name} / {ip_name} 模特图",
#         "",
#         f"[图片一：模特参考图]({ip_path.relative_to(task_dir).as_posix()})",
#         f"[图片二：服装主图]({main_path.relative_to(task_dir).as_posix()})",
#     ]
#     for index, detail_path in enumerate(detail_paths, start=1):
#         lines.append(f"[服装细节图{index}]({detail_path.relative_to(task_dir).as_posix()})")
#     lines.extend(["", prompt, ""])
#
#     case_path = task_dir / "task.md"
#     case_path.write_text("\n".join(lines), encoding="utf-8")
#
#     sidecar: dict[str, Any] = {
#         "baseUrl": base_url,
#         "productId": product_id,
#         "productName": product_name,
#         "ipId": ip_id,
#         "ipNickname": ip_name,
#         "uploadSubDir": args.upload_subdir,
#         "productMainImageUrl": main_url,
#         "productDetailImageUrls": detail_urls,
#     }
#     if not args.no_embed_cookie and cookie:
#         sidecar["cookie"] = cookie
#     case_path.with_suffix(".media-ai.json").write_text(
#         json.dumps(sidecar, ensure_ascii=False, indent=2),
#         encoding="utf-8",
#     )
#     return case_path.resolve()


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
            print("[TIMEOUT] waiting for GPT image jobs timed out.", file=sys.stderr)
            return False

        time.sleep(max(1, poll_interval))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare Media AI model-image tasks and submit them to the local GPT image queue."
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
    parser.add_argument("--no-auto-bridge", action="store_true", help="Do not auto-start local_bridge if unavailable.")
    parser.add_argument("--no-wait", action="store_true", help="Submit tasks and exit without waiting for completion.")
    parser.add_argument("--poll-interval", type=int, default=15)
    parser.add_argument("--wait-timeout", type=int, default=300, help="Seconds to wait. 0 means no timeout.")
    parser.add_argument(
        "--output-root",
        default=f"runs/media-ai-model-image-queue-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    cookie = read_cookie(args)
    prompt = read_text(pathlib.Path(args.prompt_file))
    base_url = args.base_url.rstrip("/")

    client = MediaAIClient(base_url=base_url, cookie=cookie, timeout=args.timeout)

    products = fetch_products(args, cookie)
    ips = fetch_ips(args, cookie)
    output_root = pathlib.Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    task_paths: list[pathlib.Path] = []
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

            case_path, _ = client.build_model_image_task(
                product_id=str(product.get("id") or ""),
                ip_id=str(ip.get("id") or ""),
                output_root=output_root,
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
        print(f"Prepared {len(task_paths)} task(s). Start or enqueue them with local_bridge/server.py.")
        return 0

    ensure_bridge_running(args)
    response = request_json(
        "POST",
        f"{args.bridge_url.rstrip('/')}/v1/jobs",
        body={"caseFiles": [str(path) for path in task_paths]},
        timeout=args.timeout,
    )
    print(json.dumps(redact_sensitive(response), ensure_ascii=False, indent=2))
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
