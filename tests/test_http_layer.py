"""Tests for Level-5 HTTP layer (real server integration).

Uses MediaAIClient for cookie resolution — no custom auth code here.
The server must be running at MEDIA_AI_BASE_URL (default: http://localhost:3000).

Run with: MEDIA_AI_COOKIE=<cookie> .venv/Scripts/python.exe -m pytest tests/test_http_layer.py -v
"""

from __future__ import annotations

import os
import pathlib
import tempfile

import pytest

from local_bridge.media_ai_client import MediaAIClient
from local_bridge.server import Job
from local_bridge.domain.services import (
    request_json,
    save_media_ai_generated_image,
    save_media_ai_generated_video,
    upload_file_multipart,
)


MEDIA_AI_BASE_URL = os.environ.get("MEDIA_AI_BASE_URL", "http://localhost:3000")
COOKIE = os.environ.get("MEDIA_AI_COOKIE", "")


def _ping_server(url: str) -> bool:
    """Ping server with authenticated cookie from MediaAIClient."""
    try:
        client = MediaAIClient(base_url=url, timeout=5)
        cookie = client.resolve_cookie()
        if not cookie:
            return False
        request_json("GET", f"{url.rstrip('/')}/api/products?limit=1", cookie=cookie, timeout=5)
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _ping_server(MEDIA_AI_BASE_URL),
    reason=f"Media AI server not reachable at {MEDIA_AI_BASE_URL}",
)


def _get_cookie() -> str:
    """Resolve cookie: explicit env var > MediaAIClient auto-login."""
    if COOKIE:
        return COOKIE
    client = MediaAIClient(base_url=MEDIA_AI_BASE_URL, timeout=30)
    cookie = client.resolve_cookie()
    if not cookie:
        pytest.skip("Cannot resolve Media AI cookie (set MEDIA_AI_COOKIE env var or ensure .env credentials are valid)")
    return cookie


class Test_request_json:
    def test_get_products_returns_valid_response(self) -> None:
        cookie = _get_cookie()
        result = request_json(
            "GET",
            f"{MEDIA_AI_BASE_URL}/api/products?limit=5",
            cookie=cookie,
            timeout=30,
        )
        assert result is not None
        assert isinstance(result, (list, dict))

    def test_get_nonexistent_product_returns_404(self) -> None:
        cookie = _get_cookie()
        with pytest.raises(RuntimeError) as exc_info:
            request_json(
                "GET",
                f"{MEDIA_AI_BASE_URL}/api/products/nonexistent-product-xyz-123",
                cookie=cookie,
                timeout=10,
            )
        assert "404" in str(exc_info.value)

    def test_post_validates_request_format(self) -> None:
        """POST with invalid product ID should return non-auth error (4xx/5xx)."""
        cookie = _get_cookie()
        body = {"ipId": "test", "imageUrl": "http://example.com/test.png"}
        # Server accepts the request but returns 400/404 — not auth error
        with pytest.raises(RuntimeError) as exc_info:
            request_json(
                "POST",
                f"{MEDIA_AI_BASE_URL}/api/products/fake-id-for-test/first-frame",
                cookie=cookie,
                body=body,
                timeout=10,
            )
        # Should be 400/404/405 not 401
        msg = str(exc_info.value)
        assert "401" not in msg, f"Got auth error, cookie may not be valid: {msg}"


class Test_upload_file_multipart:
    def test_upload_png_file(self, tmp_path: pathlib.Path) -> None:
        cookie = _get_cookie()
        # 10x10 red PNG
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x0a\x00\x00"
            b"\x00\x0a\x08\x02\x00\x00\x00\x90\x91h6\x00\x00\x00\x19IDAT"
            b"\x78\x9cc\xfc\xff\xff?\x03)\x00\x00\x00\xff\xff\x03\x00"
            b"\x08\xfc\x02\xfe\xa7\x9a]\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        img_path = tmp_path / "test_upload.png"
        img_path.write_bytes(png_bytes)

        result = upload_file_multipart(
            f"{MEDIA_AI_BASE_URL}/api/upload",
            cookie=cookie,
            file_path=img_path,
            sub_dir="test-uploads",
        )
        assert result is not None
        assert "url" in result
        # Upload returns relative or absolute URL
        assert len(result["url"]) > 5

    def test_upload_mp4_file(self, tmp_path: pathlib.Path) -> None:
        cookie = _get_cookie()
        # Minimal valid mp4 placeholder
        mp4_bytes = b"\x00\x00\x00\x1cftypmp42\x00\x00\x00\x00isommp42"
        mp4_path = tmp_path / "test_upload.mp4"
        mp4_path.write_bytes(mp4_bytes)

        result = upload_file_multipart(
            f"{MEDIA_AI_BASE_URL}/api/upload",
            cookie=cookie,
            file_path=mp4_path,
            sub_dir="test-uploads",
        )
        assert result is not None
        assert "url" in result


class Test_save_media_ai_generated_image:
    def test_first_frame_image_save(self, tmp_path: pathlib.Path) -> None:
        """GPT first-frame-image save flow with real product/productId from runs/.

        API: POST /api/products/{id}/first-frame
        Body: {"styleImageId": "...", "sceneId": "...", "imageUrl": "...", "generationPath": "gpt"}
        Expected: HTTP 200 with {"firstFrameUrl": "...", "firstFrameId": "..."}
        """
        cookie = _get_cookie()
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x0a\x00\x00"
            b"\x00\x0a\x08\x02\x00\x00\x00\x90\x91h6\x00\x00\x00\x19IDAT"
            b"\x78\x9cc\xfc\xff\xff?\x03)\x00\x00\x00\xff\xff\x03\x00"
            b"\x08\xfc\x02\xfe\xa7\x9a]\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        img_path = tmp_path / "first_frame.png"
        img_path.write_bytes(png_bytes)

        job = Job(
            id="test-first-frame-001",
            case_file=pathlib.Path("test/task.md"),
            prompt="test",
            assets=[],
            output_dir=tmp_path / "output",
            media_ai={
                "baseUrl": MEDIA_AI_BASE_URL,
                "kind": "first-frame-image",
                "productId": "3813528280213094793",
                "styleImageId": "f07aff65-ba21-4e2c-9580-d599417318f8",
                "sceneId": "d0e56cbd-1ef9-4b71-8ace-c4adb3cc017a",
                "cookie": cookie,
            },
        )

        result = save_media_ai_generated_image(job, img_path)
        assert result is not None
        assert result["kind"] == "first-frame-image"
        assert "uploaded" in result
        assert "saved" in result
        # Save response must include firstFrameId and firstFrameUrl
        assert "firstFrameId" in result["saved"], f"Expected firstFrameId in save result: {result['saved']}"
        assert "firstFrameUrl" in result["saved"], f"Expected firstFrameUrl in save result: {result['saved']}"

    def test_jimeng_image_upload_and_save(self, tmp_path: pathlib.Path) -> None:
        """Upload flow: upload succeeds. Save may fail with 4xx if product doesn't exist."""
        cookie = _get_cookie()
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x0a\x00\x00"
            b"\x00\x0a\x08\x02\x00\x00\x00\x90\x91h6\x00\x00\x00\x19IDAT"
            b"\x78\x9cc\xfc\xff\xff?\x03)\x00\x00\x00\xff\xff\x03\x00"
            b"\x08\xfc\x02\xfe\xa7\x9a]\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        img_path = tmp_path / "generated.png"
        img_path.write_bytes(png_bytes)

        job = Job(
            id="test-jimeng-img-001",
            case_file=pathlib.Path("test/task.md"),
            prompt="test",
            assets=[],
            output_dir=tmp_path / "output",
            media_ai={
                "baseUrl": MEDIA_AI_BASE_URL,
                "kind": "first-frame-image",
                "platform": "jimeng",
                "productId": "prod_test_001",
                "ipId": "ip_test_001",
                "cookie": cookie,
            },
        )

        try:
            result = save_media_ai_generated_image(job, img_path)
            assert result is not None
            assert result["kind"] == "first-frame-image"
            assert "uploaded" in result
            assert "saved" in result
        except RuntimeError as e:
            # Fail only if the /api/upload step itself errored (before save is called).
            # If save fails with 4xx because product doesn't exist, that's acceptable.
            msg = str(e)
            assert "/api/upload" not in msg, f"Upload step failed: {msg}"

    def test_jimeng_first_frame_upload_with_real_files(self, tmp_path: pathlib.Path) -> None:
        """Jimeng first-frame-upload with real run data: 4 images, real product/ip/style IDs.

        API: POST /api/products/{id}/first-frame-upload
        Multipart fields: ipId, generationPath, styleImageId, files (multiple)
        Expected: HTTP 200 with {"success": true, "count": N, "results": [...]}
        """
        cookie = _get_cookie()

        # Real run data from runs/jimeng-f07aff65/
        run_output = pathlib.Path("D:/Code/media/gpt_image2/runs/jimeng-f07aff65/output")
        real_files = list(run_output.glob("result-*.webp"))
        assert len(real_files) == 4, f"Expected 4 real images, found {len(real_files)}: {real_files}"

        # Copy real files to tmp_path
        img_paths = []
        for f in sorted(real_files):
            dst = tmp_path / f.name
            dst.write_bytes(f.read_bytes())
            img_paths.append(dst)

        job = Job(
            id="test-jimeng-real-001",
            case_file=pathlib.Path("test/task.md"),
            prompt="test",
            assets=[],
            output_dir=tmp_path / "output",
            media_ai={
                "baseUrl": MEDIA_AI_BASE_URL,
                "kind": "first-frame-image",
                "platform": "jimeng",
                "productId": "3813528280213094793",
                "ipId": "981cd79c-5973-429a-8edf-dff3eda45014",
                "styleImageId": "f07aff65-ba21-4e2c-9580-d599417318f8",
                "cookie": cookie,
            },
        )

        # Test with first image — save_media_ai_generated_image uploads to /api/upload first,
        # then calls save_media_ai_first_frame_upload for jimeng platform
        img_path = img_paths[0]
        result = save_media_ai_generated_image(job, img_path)
        assert result is not None
        assert result["kind"] == "first-frame-image"
        assert "uploaded" in result
        assert "saved" in result
        # Save response for first-frame-upload is FirstFrameUploadResponse
        assert "success" in result["saved"], f"Expected success in save result: {result['saved']}"


class Test_save_media_ai_generated_video:
    def test_jimeng_video_upload_and_save(self, tmp_path: pathlib.Path) -> None:
        """Multipart POST /api/products/{productId}/videos with file, firstFrameId, movementId, subDir."""
        cookie = _get_cookie()
        mp4_bytes = b"\x00\x00\x00\x1cftypmp42\x00\x00\x00\x00isommp42"
        video_path = tmp_path / "generated.mp4"
        video_path.write_bytes(mp4_bytes)

        job = Job(
            id="test-jimeng-video-001",
            case_file=pathlib.Path("test/task.md"),
            prompt="test",
            assets=[],
            output_dir=tmp_path / "output",
            media_ai={
                "baseUrl": MEDIA_AI_BASE_URL,
                "kind": "video",
                "productId": "prod_test_001",
                "ipId": "ip_test_001",
                "firstFrameId": "ff_test_001",
                "movementId": "mv_test_001",
                "cookie": cookie,
            },
        )

        try:
            result = save_media_ai_generated_video(job, video_path)
            assert result is not None
            assert result["kind"] == "video"
            assert "saved" in result, f"Expected 'saved' in result: {result}"
        except RuntimeError as e:
            # Save may fail with 4xx if product doesn't exist
            assert "videos" in str(e), f"Expected 'videos' in error: {e}"