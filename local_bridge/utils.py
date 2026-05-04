"""Shared utilities for all submit scripts — single source of truth."""

from __future__ import annotations

import json
import mimetypes
import os
import pathlib
import re
import subprocess
import sys
import time
from http.cookiejar import CookieJar
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlparse, urlunparse
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "http://localhost:3000"
DEFAULT_BRIDGE_URL = "http://127.0.0.1:8765"


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


# ---------------------------------------------------------------------------
# Bridge health
# ---------------------------------------------------------------------------

def can_reach_bridge(bridge_url: str, timeout: int = 3) -> bool:
    try:
        request_json("GET", f"{bridge_url.rstrip('/')}/v1/state", timeout=timeout)
        return True
    except Exception:
        return False


def ensure_bridge_running(args: Any) -> Any:
    """Raise RuntimeError if bridge is not reachable. Does not auto-start."""
    if can_reach_bridge(args.bridge_url):
        return None
    raise RuntimeError(
        f"local_bridge is not running at {args.bridge_url}. "
        "Start it with: uv run python -m local_bridge serve"
    )


# ---------------------------------------------------------------------------
# Wait for jobs
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Auth / Cookie
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Cookie file cache (persistent across script invocations)
# ---------------------------------------------------------------------------

_COOKIE_CACHE_FILE = pathlib.Path.home() / ".cache" / "media-ai-cookie.json"


def _validate_cookie_via_api(base_url: str, cookie: str, timeout: int) -> bool:
    """Return True if cookie is still valid, False if expired (401/403)."""
    try:
        request_json(
            "GET",
            f"{base_url.rstrip('/')}/api/products?limit=1",
            cookie=cookie,
            timeout=timeout,
        )
        return True
    except HTTPError as err:
        if err.code in (401, 403):
            return False
        return True  # non-auth errors → assume cookie still OK
    except Exception:
        return True  # network errors → assume cookie OK


def _load_cached_cookie(base_url: str, timeout: int) -> str | None:
    """Load cookie from persistent cache file. Validates before returning."""
    cache_file = _COOKIE_CACHE_FILE
    if not cache_file.exists():
        return None
    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        cookie = str(payload.get("cookie") or "").strip()
        if not cookie:
            return None
        if _validate_cookie_via_api(base_url, cookie, timeout):
            return cookie
        # expired — remove stale cache
        cache_file.unlink(missing_ok=True)
        return None
    except (json.JSONDecodeError, OSError):
        return None


def _save_cached_cookie(cookie: str) -> None:
    """Persist cookie to cache file for reuse across script invocations."""
    cache_file = _COOKIE_CACHE_FILE
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps({"cookie": cookie}, ensure_ascii=False),
        encoding="utf-8",
    )


def login_media_ai(base_url: str, *, email: str, password: str, timeout: int) -> str:
    """Log in to Media AI and return the session cookie."""
    cookie_jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookie_jar))
    base_url = base_url.rstrip("/")

    csrf_request = Request(
        f"{base_url}/api/auth/csrf", headers={"Accept": "application/json"}, method="GET"
    )
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


def read_cookie(args: Any) -> str | None:
    """Resolve cookie from args (cookie/cookie_file/env_file) or environment.

    Resolution order:
      1. Explicit --cookie argument
      2. --cookie-file path
      3. MEDIA_AI_COOKIE env var
      4. Persistent cache file (~/.cache/media-ai-cookie.json), validated before use
      5. .env file credentials (user + password), result cached for next run

    When auto-login is triggered, the resulting cookie is saved to the cache file
    so subsequent script invocations reuse it without re-authenticating.
    """
    if getattr(args, "cookie", None):
        return args.cookie.strip()
    if getattr(args, "cookie_file", None):
        return pathlib.Path(args.cookie_file).read_text(encoding="utf-8").strip()
    env_cookie = os.environ.get("MEDIA_AI_COOKIE")
    if env_cookie:
        return env_cookie.strip()

    base_url = getattr(args, "base_url", "http://localhost:3000")
    timeout = getattr(args, "timeout", 120)

    # Try persistent cache (validated via lightweight API call)
    cached = _load_cached_cookie(base_url, timeout)
    if cached:
        return cached

    # .env file credentials
    env_file = pathlib.Path(getattr(args, "env_file", ".env"))
    env_values = parse_env_file(env_file)
    user = os.environ.get("MEDIA_AI_USER") or env_values.get("MEDIA_AI_USER")
    password = os.environ.get("MEDIA_AI_PASSWORD") or env_values.get("MEDIA_AI_PASSWORD")
    if user and password:
        cookie = login_media_ai(
            base_url,
            email=user,
            password=password,
            timeout=timeout,
        )
        _save_cached_cookie(cookie)
        return cookie
    return None


def redact_sensitive(value: Any) -> Any:
    """Redact cookie fields from nested structures."""
    if isinstance(value, dict):
        return {k: "<redacted>" if k.lower() == "cookie" else redact_sensitive(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    return value


# ---------------------------------------------------------------------------
# Normalize list helpers
# ---------------------------------------------------------------------------

def normalize_list(payload: Any, keys: tuple[str, ...], label: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise ValueError(f"Cannot find {label} array in response.")


def normalize_product_list(payload: Any) -> list[dict[str, Any]]:
    return normalize_list(payload, ("products", "items", "data"), "product")


def normalize_ip_list(payload: Any) -> list[dict[str, Any]]:
    return normalize_list(payload, ("ips", "items", "data"), "virtual IP")


# ---------------------------------------------------------------------------
# ID file loading
# ---------------------------------------------------------------------------

def load_ids(path: str) -> list[str]:
    """Load IDs from a file (JSON array or one-per-line)."""
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


def read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8").strip()


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


def guess_mime_type(path: pathlib.Path) -> str:
    mime_type, _ = mimetypes.guess_type(path.name)
    return mime_type or "application/octet-stream"


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


def download_file(url: str, target: pathlib.Path, *, cookie: str | None, timeout: int) -> None:
    headers = {"Accept": "*/*"}
    if cookie:
        headers["Cookie"] = cookie
    request = Request(quote_url(url), headers=headers, method="GET")
    with urlopen(request, timeout=timeout) as response:
        target.write_bytes(response.read())


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