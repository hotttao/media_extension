"""Media AI API client — single source of truth for all Media AI HTTP interactions."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import pathlib
import re
import sys
import uuid
from http.cookiejar import CookieJar
from typing import Any
from urllib.parse import quote, urlencode, urljoin, urlparse, urlunparse
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen
from urllib.error import HTTPError, URLError
from loguru import logger as _logger

# Configure loguru for this module
_logger.remove()
LOG_FILE = pathlib.Path("logs/media_ai_client.log")
LOG_FILE.parent.mkdir(exist_ok=True)
_logger.add(
    LOG_FILE,
    format="{time:HH:mm:ss} | {level} | {message}",
    level=os.environ.get("LOG_LEVEL", "DEBUG").upper(),
    rotation="100 MB",
    retention="7 days",
    encoding="utf-8",
    enqueue=True,
    backtrace=True,
    diagnose=True,
)


# ---------------------------------------------------------------------------
# URL Utilities
# ---------------------------------------------------------------------------


def _quote_url(url: str) -> str:
    """Quote URL path and query characters for safe use in Request."""
    parsed = urlparse(url)
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            quote(parsed.path, safe="/:"),
            parsed.params,
            quote(parsed.query, safe="=&?/:;"),
            parsed.fragment,
        )
    )


def resolve_media_url(base_url: str, value: str) -> str:
    """Resolve a potentially-relative media URL to an absolute URL."""
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return urljoin(base_url.rstrip("/") + "/", value.lstrip("/"))


def extension_from_url(url: str, fallback: str = ".png") -> str:
    """Extract the file extension from a URL, with a fallback default."""
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


def guess_mime_type(path: pathlib.Path) -> str:
    """Guess the MIME type of a file based on its extension."""
    mime_type, _ = mimetypes.guess_type(path.name)
    return mime_type or "application/octet-stream"


def sha256_bytes(data: bytes) -> str:
    """Compute the SHA256 hex digest of raw bytes."""
    return hashlib.sha256(data).hex()


def slugify(value: str) -> str:
    """Convert a string to a safe slug identifier."""
    cleaned = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff_-]+", "-", value).strip("-")
    return cleaned or "product"


# ---------------------------------------------------------------------------
# Scene helpers
# ---------------------------------------------------------------------------


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


def _extract_scenes(payload) -> list[dict]:
    """Normalize a scenes response into a list of scene dicts."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("scenes", "materials", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _normalize_list(payload) -> list[dict]:
    """Normalize a list response, trying common container keys."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("items", "data", "products", "ips", "materials"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def load_media_ai_sidecar(case_path: pathlib.Path) -> dict | None:
    """Load the .media-ai.json sidecar accompanying a task.md file."""
    sidecar_path = case_path.with_suffix(".media-ai.json")
    if not sidecar_path.exists():
        return None
    return json.loads(sidecar_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# MediaAIClient
# ---------------------------------------------------------------------------

class MediaAIClient:
    """
    Unified client for all Media AI API interactions.

    Usage:
        client = MediaAIClient(base_url="http://localhost:3000")
        client.resolve_cookie()  # login from .env / env vars
        product = client.fetch_product("3813528280213094793")
        case_path, status = client.build_model_image_task(...)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:3000",
        media_base_url: str = "http://192.168.2.38",
        cookie: str | None = None,
        timeout: int = 120,
    ):
        self.base_url = base_url.rstrip("/")
        self.media_base_url = media_base_url.rstrip("/")
        self.cookie = cookie
        self.timeout = timeout

    # -------------------------------------------------------------------------
    # Cookie / Auth
    # -------------------------------------------------------------------------

    def login(self, email: str, password: str) -> str:
        """Log in to Media AI and return the session cookie."""
        cookie_jar = CookieJar()
        opener = build_opener(HTTPCookieProcessor(cookie_jar))

        csrf_request = Request(
            f"{self.base_url}/api/auth/csrf",
            headers={"Accept": "application/json"},
            method="GET",
        )
        with opener.open(csrf_request, timeout=self.timeout) as response:
            csrf_payload = json.loads(response.read().decode("utf-8"))
        csrf_token = csrf_payload.get("csrfToken")
        if not csrf_token:
            raise RuntimeError(f"CSRF response missing csrfToken: {csrf_payload}")

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
            f"{self.base_url}/api/auth/callback/credentials",
            data=form,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        with opener.open(login_request, timeout=self.timeout) as response:
            raw = response.read().decode("utf-8")
            if response.status >= 400:
                raise RuntimeError(f"Login failed with HTTP {response.status}: {raw}")

        cookie_str = "; ".join(f"{c.name}={c.value}" for c in cookie_jar)
        if "next-auth.session-token=" not in cookie_str and "__Secure-next-auth.session-token=" not in cookie_str:
            raise RuntimeError("Login did not produce a NextAuth session cookie.")
        return cookie_str

    def _validate_cookie(self) -> bool:
        """Validate cached cookie by hitting a lightweight API endpoint."""
        try:
            self.request_json("GET", "/api/products?limit=1", cookie=self.cookie)
            return True
        except HTTPError as err:
            if err.code in (401, 403):
                _logger.debug("cookie expired (HTTP {code}), will re-authenticate", code=err.code)
                return False
            # Other errors — network issue, server error, etc. — treat cookie as potentially valid
            _logger.debug("cookie validation got HTTP {code}, assuming still valid", code=err.code)
            return True
        except Exception as err:
            _logger.debug("cookie validation failed with {err}, assuming still valid", err=err)
            return True

    def resolve_cookie(self, cookie: str | None = None) -> str | None:
        """Resolve cookie: explicit > env var > .env file > auto-login. Saves to self.cookie.

        If a cached cookie is present (from a previous auto-login), it is validated
        before reuse. When validation fails (401/403), the cached value is cleared
        and the full resolution chain is retried.
        """
        if cookie:
            self.cookie = cookie
            return cookie
        if self.cookie:
            if self._validate_cookie():
                return self.cookie
            # cookie expired — clear and fall through to re-resolve
            self.cookie = None
        env_cookie = os.environ.get("MEDIA_AI_COOKIE")
        if env_cookie:
            self.cookie = env_cookie.strip()
            return self.cookie

        # Try .env file (project root: two levels up from this file)
        env_file = pathlib.Path.cwd() / ".env"
        env_values: dict[str, str] = {}
        if env_file.exists():
            for raw_line in env_file.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                    value = value[1:-1]
                env_values[key] = value

        user = os.environ.get("MEDIA_AI_USER") or env_values.get("MEDIA_AI_USER")
        password = os.environ.get("MEDIA_AI_PASSWORD") or env_values.get("MEDIA_AI_PASSWORD")
        if user and password:
            self.cookie = self.login(user, password)
            return self.cookie
        return None

    # -------------------------------------------------------------------------
    # Core HTTP
    # -------------------------------------------------------------------------

    def request_json(
        self,
        method: str,
        path: str,
        *,
        cookie: str | None = None,
        body: dict | None = None,
    ) -> Any:
        """Perform an HTTP request and parse the JSON response."""
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        resolved_cookie = cookie or self.cookie
        if resolved_cookie:
            headers["Cookie"] = resolved_cookie

        url = f"{self.base_url}{path}" if path.startswith("/") else f"{self.base_url}/{path}"
        _logger.debug("HTTP {method} {path}", method=method, path=path)
        request = Request(_quote_url(url), data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                _logger.debug("HTTP {method} {path} -> {status} ({size} bytes)", method=method, path=path, status=response.status, size=len(raw) if raw else 0)
                return json.loads(raw) if raw else None
        except HTTPError as error:
            raw = error.read().decode("utf-8", errors="replace")
            _logger.error("HTTP {method} {path} -> HTTP {code} ({size} bytes)", method=method, path=path, code=error.code, size=len(raw) if raw else 0)
            raise RuntimeError(f"{method} {url} failed with HTTP {error.code}: {raw}") from error
        except URLError as error:
            _logger.error("HTTP {method} {path} -> ERR {reason}", method=method, path=path, reason=error.reason)
            raise RuntimeError(f"{method} {url} failed: {error.reason}") from error

    def download_file(
        self,
        url: str,
        target: pathlib.Path,
        *,
        cookie: str | None = None,
    ) -> None:
        """Download a URL to a local file. Handles Chinese characters in URL paths."""
        _logger.debug("download_file url={url} target={target}", url=url, target=target.name)
        headers = {"Accept": "*/*"}
        resolved_cookie = cookie or self.cookie
        if resolved_cookie:
            headers["Cookie"] = resolved_cookie
        request = Request(_quote_url(url), headers=headers, method="GET")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                data = response.read()
                target.write_bytes(data)
                _logger.debug("download_file completed url={url} size={size} bytes", url=url, size=len(data))
        except HTTPError as error:
            _logger.error("download_file failed url={url} HTTP={code}", url=url, code=error.code)
            raise
        except URLError as error:
            _logger.error("download_file failed url={url} err={reason}", url=url, reason=error.reason)
            raise

    def upload_file(
        self,
        file_path: pathlib.Path,
        sub_dir: str,
        *,
        cookie: str | None = None,
    ) -> dict:
        """Upload a file to Media AI via multipart form."""
        _logger.debug("upload_file file={file} sub_dir={sub}", file=file_path.name, sub=sub_dir)
        boundary = f"----codex-{uuid.uuid4().hex}"
        file_bytes = file_path.read_bytes()
        mime_type = guess_mime_type(file_path)
        fields = [
            (
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="subDir"\r\n\r\n'
                f"{sub_dir}\r\n"
            ).encode("utf-8"),
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
                f"Content-Type: {mime_type}\r\n\r\n"
            ).encode("utf-8"),
            file_bytes,
            f"\r\n--{boundary}--\r\n".encode("utf-8"),
        ]
        body = b"".join(fields)
        headers = {
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        }
        resolved_cookie = cookie or self.cookie
        if resolved_cookie:
            headers["Cookie"] = resolved_cookie

        url = f"{self.base_url}/api/upload"
        request = Request(_quote_url(url), data=body, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                _logger.debug("upload_file completed file={file} size={size} bytes", file=file_path.name, size=len(file_bytes))
                return json.loads(raw) if raw else {}
        except HTTPError as error:
            raw = error.read().decode("utf-8", errors="replace")
            _logger.error("upload_file failed file={file} HTTP={code}", file=file_path.name, code=error.code)
            raise RuntimeError(f"POST {url} failed with HTTP {error.code}: {raw}") from error
        except URLError as error:
            _logger.error("upload_file failed file={file} err={reason}", file=file_path.name, reason=error.reason)
            raise RuntimeError(f"POST {url} failed: {error.reason}") from error

    # -------------------------------------------------------------------------
    # Entity Fetchers
    # -------------------------------------------------------------------------

    def fetch_product(self, product_id: str) -> dict:
        return self.request_json("GET", f"/api/products/{product_id}")

    def fetch_ip(self, ip_id: str) -> dict:
        return self.request_json("GET", f"/api/ips/{ip_id}")

    def fetch_model_image(self, model_image_id: str) -> dict | None:
        """Fetch a model-image by ID via GET /api/model-images/{id}."""
        try:
            return self.request_json("GET", f"/api/model-images/{model_image_id}")
        except HTTPError as error:
            if error.code == 404:
                return None
            raise
        except Exception:
            return None

    def fetch_style_image(self, style_image_id: str) -> dict | None:
        """Fetch a style-image by ID via GET /api/style-images/{id}."""
        try:
            return self.request_json("GET", f"/api/style-images/{style_image_id}")
        except HTTPError as error:
            if error.code == 404:
                return None
            raise
        except Exception:
            return None

    def fetch_first_frame(self, first_frame_id: str) -> dict | None:
        """Fetch a first-frame by ID via GET /api/first-frames/{id}."""
        try:
            return self.request_json("GET", f"/api/first-frames/{first_frame_id}")
        except HTTPError as error:
            if error.code == 404:
                return None
            raise
        except Exception:
            return None

    def fetch_pose(self, pose_id: str) -> dict | None:
        """Fetch a POSE material by ID."""
        try:
            payload = self.request_json(
                "GET", f"/api/materials?{urlencode({'type': 'POSE'})}"
            )
            materials = payload
            if isinstance(payload, dict):
                materials = payload.get("materials") or payload.get("items") or payload.get("data") or payload
            if isinstance(materials, list):
                for item in materials:
                    if str(item.get("id") or "") == pose_id:
                        return item
        except Exception:
            pass
        return None

    def fetch_scene(self, scene_id: str) -> dict | None:
        """Fetch a scene by ID. Tries product scenes then IP scenes."""
        # Try product scenes first
        try:
            page = self.request_json("GET", "/api/products?limit=100")
            for product in _normalize_list(page):
                product_id = str(product.get("id") or "")
                if not product_id:
                    continue
                try:
                    scenes_payload = self.request_json(
                        "GET", f"/api/products/{product_id}/scenes"
                    )
                    scenes = _extract_scenes(scenes_payload)
                    for scene in scenes:
                        if _scene_key(scene) == scene_id:
                            return scene
                except Exception:
                    continue
        except Exception:
            pass

        # Try IP scenes
        try:
            ip_payload = self.request_json("GET", "/api/ips?limit=100")
            for ip in _normalize_list(ip_payload):
                ip_id = str(ip.get("id") or "")
                if not ip_id:
                    continue
                try:
                    scenes_payload = self.request_json(
                        "GET", f"/api/ips/{ip_id}/scenes"
                    )
                    scenes = _extract_scenes(scenes_payload)
                    for scene in scenes:
                        if _scene_key(scene) == scene_id:
                            return scene
                except Exception:
                    continue
        except Exception:
            pass

        return None

    # -------------------------------------------------------------------------
    # Existence Checks
    # -------------------------------------------------------------------------

    def existing_model_images(self, product_id: str, ip_id: str) -> list[dict]:
        query = urlencode({"ipId": ip_id})
        payload = self.request_json(
            "GET", f"/api/products/{product_id}/model-images?{query}"
        )
        return payload if isinstance(payload, list) else []

    def existing_style_images(self, model_image_id: str, pose_id: str) -> list[dict]:
        query = urlencode({"modelImageId": model_image_id})
        payload = self.request_json(
            "GET", f"/api/model-images/{model_image_id}/style-images?{query}"
        )
        items: list[dict] = []
        if isinstance(payload, list):
            items = [item for item in payload if isinstance(item, dict)]
        elif isinstance(payload, dict):
            for key in ("styleImages", "items", "data"):
                value = payload.get(key)
                if isinstance(value, list):
                    items = [item for item in value if isinstance(item, dict)]
                    break
        return [item for item in items if str(item.get("poseId") or "") == pose_id]

    def existing_first_frames(
        self, product_id: str, style_image_id: str, scene_id: str
    ) -> list[dict]:
        query = urlencode({"styleImageId": style_image_id})
        payload = self.request_json(
            "GET", f"/api/products/{product_id}/first-frames?{query}"
        )
        items: list[dict] = []
        if isinstance(payload, list):
            items = [item for item in payload if isinstance(item, dict)]
        elif isinstance(payload, dict):
            for key in ("firstFrames", "items", "data"):
                value = payload.get(key)
                if isinstance(value, list):
                    items = [item for item in value if isinstance(item, dict)]
                    break
        # Filter by sceneId to avoid false positives
        return [item for item in items if str(item.get("sceneId") or "") == scene_id]

    # -------------------------------------------------------------------------
    # Task Builders
    # -------------------------------------------------------------------------

    def build_model_image_task(
        self,
        product_id: str,
        ip_id: str,
        output_root: pathlib.Path,
        prompt: str,
        force: bool = False,
    ) -> tuple[pathlib.Path | None, str]:
        """
        Build a model-image task.

        Returns (case_path, status) where status is:
        - "ok" — task created
        - "exists" — already exists (and force=False)
        - "error" — failed
        """
        cookie = self.resolve_cookie()

        if not force:
            existing = self.existing_model_images(product_id, ip_id)
            if existing:
                return (None, "exists")

        product = self.request_json("GET", f"/api/products/{product_id}", cookie=cookie)
        ip = self.request_json("GET", f"/api/ips/{ip_id}", cookie=cookie)

        product_id = str(product.get("id") or "")
        product_name = str(product.get("name") or product_id)
        ip_name = str(ip.get("nickname") or ip_id)

        images = product.get("images") or []
        if not isinstance(images, list) or not images:
            raise RuntimeError(f"[model-image] product {product_id} has no images")

        image_items = [item for item in images if isinstance(item, dict) and item.get("url")]
        if not image_items:
            raise RuntimeError(f"[model-image] product {product_id} has no valid image URLs")

        main = next((item for item in image_items if item.get("isMain") is True), None)
        if main is None:
            main = sorted(
                image_items, key=lambda x: (int(x.get("order") or 999999), str(x.get("id") or ""))
            )[0]

        main_image_url = resolve_media_url(self.media_base_url, str(main["url"]))
        ip_full_body_url = ip.get("fullBodyUrl")
        if not product_id or not ip_id or not main_image_url or not ip_full_body_url:
            raise RuntimeError(f"[model-image] missing required fields product_id={product_id!r} ip_id={ip_id!r} main_url={main_image_url!r} ip_full_body={ip_full_body_url!r}")

        task_dir = output_root / f"{slugify(product_name)}-{product_id[:8]}__{slugify(ip_name)}-{ip_id[:8]}"
        assets_dir = task_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        ip_url = resolve_media_url(self.media_base_url, str(ip_full_body_url))
        main_url = resolve_media_url(self.media_base_url, main_image_url)

        ip_path = assets_dir / f"model-reference{extension_from_url(ip_url)}"
        main_path = assets_dir / f"product-main{extension_from_url(main_url)}"
        _logger.debug("build_model_image_task downloading assets ip_url={ip} main_url={main}", ip=ip_url, main=main_url)
        self.download_file(ip_url, ip_path, cookie=cookie)
        self.download_file(main_url, main_path, cookie=cookie)

        lines = [
            f"# {product_name} / {ip_name} 模特图",
            "",
            f"[图片一：模特参考图]({ip_path.relative_to(task_dir).as_posix()})",
            f"[图片二：服装主图]({main_path.relative_to(task_dir).as_posix()})",
            "",
            prompt,
            "",
        ]
        case_path = task_dir / "task.md"
        case_path.write_text("\n".join(lines), encoding="utf-8")

        sidecar: dict = {
            "kind": "model-image",
            "baseUrl": self.base_url,
            "productId": product_id,
            "productName": product_name,
            "ipId": ip_id,
            "ipNickname": ip_name,
            "productMainImageUrl": main_url,
        }
        if cookie:
            sidecar["cookie"] = cookie
        case_path.with_suffix(".media-ai.json").write_text(
            json.dumps(sidecar, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return (case_path.resolve(), "ok")

    def build_style_image_task(
        self,
        model_image_id: str,
        pose_id: str,
        output_root: pathlib.Path,
        prompt: str,
        force: bool = False,
    ) -> tuple[pathlib.Path | None, str]:
        """Build a style-image task. Returns (case_path, status)."""
        cookie = self.resolve_cookie()

        model_image = self.fetch_model_image(model_image_id)
        if not model_image:
            raise RuntimeError(f"[style-image] model_image not found: {model_image_id}")
        pose = self.fetch_pose(pose_id)
        if not pose:
            raise RuntimeError(f"[style-image] pose not found: {pose_id}")

        model_image_id_str = str(model_image.get("id") or "")
        product_id = str(model_image.get("productId") or "")
        product_name = str(model_image.get("productName") or product_id)
        ip_id = str(model_image.get("ipId") or "")
        pose_id_str = str(pose.get("id") or "")
        pose_name = str(pose.get("name") or pose_id)
        model_url = str(model_image.get("url") or "")
        pose_url = str(pose.get("url") or "")
        if not model_image_id_str or not product_id or not pose_id_str or not model_url or not pose_url:
            raise RuntimeError(f"[style-image] missing fields: model_id={model_image_id_str!r} product_id={product_id!r} pose_id={pose_id_str!r} model_url={model_url!r} pose_url={pose_url!r}")

        if not force:
            existing = self.existing_style_images(model_image_id_str, pose_id_str)
            if existing:
                return (None, "exists")

        task_dir = output_root / (
            f"{slugify(product_name)}-{product_id[:8]}__"
            f"model-{model_image_id_str[:8]}__pose-{slugify(pose_name)}-{pose_id_str[:8]}"
        )
        assets_dir = task_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        model_media_url = resolve_media_url(self.media_base_url, model_url)
        pose_media_url = resolve_media_url(self.media_base_url, pose_url)
        model_path = assets_dir / f"model-image{extension_from_url(model_media_url)}"
        pose_path = assets_dir / f"pose-reference{extension_from_url(pose_media_url)}"
        _logger.debug("build_style_image_task downloading assets model_url={model} pose_url={pose}", model=model_media_url, pose=pose_media_url)
        self.download_file(model_media_url, model_path, cookie=cookie)
        self.download_file(pose_media_url, pose_path, cookie=cookie)

        lines = [
            f"# {product_name} / {pose_name} 定妆图",
            "",
            f"[图片一：换装好的模特图]({model_path.relative_to(task_dir).as_posix()})",
            f"[图片二：姿势参考图]({pose_path.relative_to(task_dir).as_posix()})",
            "",
            prompt,
            "",
        ]
        case_path = task_dir / "task.md"
        case_path.write_text("\n".join(lines), encoding="utf-8")

        sidecar: dict = {
            "kind": "style-image",
            "baseUrl": self.base_url,
            "productId": product_id,
            "productName": product_name,
            "ipId": ip_id,
            "modelImageId": model_image_id_str,
            "poseId": pose_id_str,
            "poseName": pose_name,
            "modelImageUrl": model_media_url,
            "poseUrl": pose_media_url,
        }
        if cookie:
            sidecar["cookie"] = cookie
        case_path.with_suffix(".media-ai.json").write_text(
            json.dumps(sidecar, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return (case_path.resolve(), "ok")

    def build_first_frame_task(
        self,
        style_image_id: str,
        scene_id: str,
        output_root: pathlib.Path,
        prompt: str,
        force: bool = False,
    ) -> tuple[pathlib.Path | None, str]:
        """Build a first-frame-image task. Returns (case_path, status)."""
        cookie = self.resolve_cookie()

        style_image = self.fetch_style_image(style_image_id)
        if not style_image:
            raise RuntimeError(f"[first-frame] style_image not found: {style_image_id}")
        scene = self.fetch_scene(scene_id)
        if not scene:
            raise RuntimeError(f"[first-frame] scene not found: {scene_id}")

        product_id = str(style_image.get("productId") or "")
        product_name = str(style_image.get("productName") or product_id)
        ip_id = str(style_image.get("ipId") or "")
        style_image_id_str = str(style_image.get("id") or "")
        style_image_url = str(style_image.get("url") or "")
        scene_id_key = _scene_key(scene)
        scene_name_val = _scene_name(scene)
        scene_url_val = _scene_url(scene)

        if not product_id or not ip_id or not style_image_id_str or not style_image_url or not scene_id_key or not scene_url_val:
            raise RuntimeError(f"[first-frame] missing fields: product_id={product_id!r} ip_id={ip_id!r} style_image_id={style_image_id_str!r} style_url={style_image_url!r} scene_id={scene_id_key!r} scene_url={scene_url_val!r}")

        if not force:
            existing = self.existing_first_frames(product_id, style_image_id_str, scene_id_key)
            if existing:
                return (None, "exists")

        task_dir = output_root / (
            f"{slugify(product_name)}-{product_id[:8]}__"
            f"style-{style_image_id_str[:8]}__"
            f"scene-{slugify(scene_name_val)}-{scene_id_key[:8]}"
        )
        assets_dir = task_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        style_media_url = resolve_media_url(self.media_base_url, style_image_url)
        scene_media_url = resolve_media_url(self.media_base_url, scene_url_val)
        style_path = assets_dir / f"style-image{extension_from_url(style_media_url)}"
        scene_path = assets_dir / f"scene-reference{extension_from_url(scene_media_url)}"
        _logger.debug("build_first_frame_task downloading assets style_url={style} scene_url={scene}", style=style_media_url, scene=scene_media_url)
        self.download_file(style_media_url, style_path, cookie=cookie)
        self.download_file(scene_media_url, scene_path, cookie=cookie)

        lines = [
            f"# {product_name} / style-{style_image_id_str[:8]} / {scene_name_val} 首帧图",
            "",
            f"[图片一：模特定妆照]({style_path.relative_to(task_dir).as_posix()})",
            f"[图片二：场景]({scene_path.relative_to(task_dir).as_posix()})",
            "",
            prompt,
            "",
        ]
        case_path = task_dir / "task.md"
        case_path.write_text("\n".join(lines), encoding="utf-8")

        sidecar: dict = {
            "kind": "first-frame-image",
            "baseUrl": self.base_url,
            "productId": product_id,
            "productName": product_name,
            "ipId": ip_id,
            "styleImageId": style_image_id_str,
            "styleImageUrl": style_media_url,
            "sceneId": scene_id_key,
            "sceneName": scene_name_val,
            "sceneUrl": scene_media_url,
        }
        if cookie:
            sidecar["cookie"] = cookie
        case_path.with_suffix(".media-ai.json").write_text(
            json.dumps(sidecar, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return (case_path.resolve(), "ok")

    # -------------------------------------------------------------------------
    # Save Generated Images
    # -------------------------------------------------------------------------

    def save_model_image(
        self,
        product_id: str,
        ip_id: str,
        image_path: pathlib.Path,
        *,
        cookie: str | None = None,
    ) -> dict:
        """Upload and save a generated model image to Media AI."""
        cookie = cookie or self.resolve_cookie()
        upload_result = self.upload_file(image_path, sub_dir="model-images", cookie=cookie)
        image_url = upload_result.get("url", "")
        if not image_url:
            raise RuntimeError(f"Upload response missing url: {upload_result}")

        save_body = {"ipId": ip_id, "imageUrl": image_url}
        save_url = f"/api/products/{product_id}/model-image/save"
        save_result = self.request_json("POST", save_url, cookie=cookie, body=save_body)
        return {"uploaded": upload_result, "saved": save_result}

    def save_style_image(
        self,
        product_id: str,
        model_image_id: str,
        image_path: pathlib.Path,
        *,
        cookie: str | None = None,
        pose_id: str | None = None,
        makeup_id: str | None = None,
        accessory_id: str | None = None,
    ) -> dict:
        """Upload and save a generated style image to Media AI."""
        cookie = cookie or self.resolve_cookie()
        upload_result = self.upload_file(image_path, sub_dir="style-images", cookie=cookie)
        image_url = upload_result.get("url", "")
        if not image_url:
            raise RuntimeError(f"Upload response missing url: {upload_result}")

        save_body = {
            "modelImageId": model_image_id,
            "poseId": pose_id,
            "makeupId": makeup_id,
            "accessoryId": accessory_id,
            "imageUrl": image_url,
        }
        save_url = f"/api/products/{product_id}/style-image/save"
        save_result = self.request_json("POST", save_url, cookie=cookie, body=save_body)
        return {"uploaded": upload_result, "saved": save_result}

    def save_first_frame_image(
        self,
        product_id: str,
        style_image_id: str,
        image_path: pathlib.Path,
        *,
        cookie: str | None = None,
        scene_id: str | None = None,
        composition: dict | None = None,
    ) -> dict:
        """Upload and save a generated first-frame image to Media AI."""
        cookie = cookie or self.resolve_cookie()
        upload_result = self.upload_file(image_path, sub_dir="first-frames", cookie=cookie)
        image_url = upload_result.get("url", "")
        if not image_url:
            raise RuntimeError(f"Upload response missing url: {upload_result}")

        save_body = {
            "styleImageId": style_image_id,
            "sceneId": scene_id,
            "composition": composition,
            "imageUrl": image_url,
        }
        save_url = f"/api/products/{product_id}/first-frame"
        save_result = self.request_json("POST", save_url, cookie=cookie, body=save_body)
        return {"uploaded": upload_result, "saved": save_result}
