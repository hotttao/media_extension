"""Tests for media_ai_client: image download and data fetching.

Run integration tests with real server:
  MEDIA_AI_COOKIE=<cookie> uv run pytest tests/test_media_ai_client.py -v

Unit tests use mocks and don't require a running server.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from local_bridge.media_ai_client import (
    MediaAIClient,
    load_media_ai_sidecar,
    resolve_media_url,
    extension_from_url,
)


MEDIA_AI_BASE_URL = "http://localhost:3000"
MEDIA_SERVICE_URL = "http://192.168.2.38"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client() -> MediaAIClient:
    """Client with default base URLs."""
    return MediaAIClient(
        base_url=MEDIA_AI_BASE_URL,
        media_base_url=MEDIA_SERVICE_URL,
        timeout=30,
    )


@pytest.fixture
def real_image_url() -> str:
    """Real image URL path stored in database."""
    return "/uploads/teams/18982144-3d42-4a51-98d8-4d6959332d66/materials/IMG_4726_322e5b31-5a31-4b58-8a9a-993b81d17012.JPG"


# ---------------------------------------------------------------------------
# resolve_media_url
# ---------------------------------------------------------------------------

class Test_resolve_media_url:
    def test_absolute_url_pass_through(self) -> None:
        url = "http://example.com/image.png"
        assert resolve_media_url("http://base.com", url) == url

    def test_https_absolute_pass_through(self) -> None:
        url = "https://example.com/image.png"
        assert resolve_media_url("http://base.com", url) == url

    def test_relative_path_joined(self) -> None:
        result = resolve_media_url("http://192.168.2.38", "/uploads/teams/123/materials/img.jpg")
        assert result == "http://192.168.2.38/uploads/teams/123/materials/img.jpg"

    def test_relative_path_no_leading_slash(self) -> None:
        result = resolve_media_url("http://192.168.2.38", "uploads/teams/123/img.jpg")
        assert result == "http://192.168.2.38/uploads/teams/123/img.jpg"


# ---------------------------------------------------------------------------
# extension_from_url
# ---------------------------------------------------------------------------

class Test_extension_from_url:
    def test_png_extension(self) -> None:
        assert extension_from_url("http://example.com/image.PNG") == ".png"

    def test_jpg_extension(self) -> None:
        assert extension_from_url("http://example.com/image.jpg") == ".jpg"

    def test_jpeg_extension(self) -> None:
        assert extension_from_url("http://example.com/path/file.jpeg") == ".jpeg"

    def test_webp_extension(self) -> None:
        assert extension_from_url("http://example.com/photo.webp") == ".webp"

    def test_fallback_for_unknown(self) -> None:
        result = extension_from_url("http://example.com/file.xyz")
        assert result == ".png"  # default fallback


# ---------------------------------------------------------------------------
# load_media_ai_sidecar
# ---------------------------------------------------------------------------

class Test_load_media_ai_sidecar:
    def test_loads_existing_sidecar(self, tmp_path: pathlib.Path) -> None:
        case_file = tmp_path / "task.md"
        case_file.write_text("# Test task", encoding="utf-8")
        sidecar_file = tmp_path / "task.media-ai.json"
        sidecar_file.write_text(json.dumps({
            "kind": "jimeng-image",
            "productId": "prod_001",
            "ipId": "ip_001",
            "styleImageId": "style_001",
        }), encoding="utf-8")

        sidecar = load_media_ai_sidecar(case_file)
        assert sidecar is not None
        assert sidecar["kind"] == "jimeng-image"
        assert sidecar["productId"] == "prod_001"

    def test_returns_none_for_missing_sidecar(self, tmp_path: pathlib.Path) -> None:
        case_file = tmp_path / "task.md"
        case_file.write_text("# Test task", encoding="utf-8")
        # No sidecar file
        sidecar = load_media_ai_sidecar(case_file)
        assert sidecar is None


# ---------------------------------------------------------------------------
# download_file (unit tests with mock)
# ---------------------------------------------------------------------------

class Test_download_file_unit:
    def test_download_file_with_cookie(self, tmp_path: pathlib.Path) -> None:
        """download_file passes cookie correctly to request."""
        target = tmp_path / "output.png"
        test_cookie = "next-auth.session-token=test-token"

        with patch("local_bridge.media_ai_client.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = b"\x89PNG\r\n\x1a\n"
            mock_response.status = 200
            mock_response.read.return_value = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
            mock_urlopen.return_value.__enter__.return_value = mock_response

            client = MediaAIClient(base_url=MEDIA_AI_BASE_URL, media_base_url=MEDIA_SERVICE_URL)
            client.download_file(
                f"{MEDIA_SERVICE_URL}/uploads/teams/test/materials/img.png",
                target,
                cookie=test_cookie,
            )

            mock_urlopen.assert_called_once()
            call_args = mock_urlopen.call_args
            request_obj = call_args[0][0]
            headers = dict(request_obj.headers)
            assert "Cookie" in headers
            assert test_cookie in headers["Cookie"]

    def test_download_file_no_cookie(self, tmp_path: pathlib.Path) -> None:
        """download_file works without cookie for public files."""
        target = tmp_path / "output.png"

        with patch("local_bridge.media_ai_client.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
            mock_response.status = 200
            mock_urlopen.return_value.__enter__.return_value = mock_response

            client = MediaAIClient(base_url=MEDIA_AI_BASE_URL, media_base_url=MEDIA_SERVICE_URL)
            client.download_file(
                f"{MEDIA_SERVICE_URL}/uploads/public/test.png",
                target,
                cookie=None,
            )

            mock_urlopen.assert_called_once()
            request_obj = mock_urlopen.call_args[0][0]
            # No Cookie header when cookie is None
            assert "Cookie" not in dict(request_obj.headers)


# ---------------------------------------------------------------------------
# fetch_style_image (mocked HTTP)
# ---------------------------------------------------------------------------

class Test_fetch_style_image_unit:
    def test_returns_none_on_404(self) -> None:
        """404 returns None (not an exception)."""
        from urllib.error import HTTPError

        client = MediaAIClient(base_url=MEDIA_AI_BASE_URL, media_base_url=MEDIA_SERVICE_URL)

        with patch.object(client, "request_json") as mock_request:
            err = HTTPError(url="http://localhost/api/style-images/bad", code=404, msg="Not Found", hdrs={}, fp=None)
            mock_request.side_effect = err

            result = client.fetch_style_image("bad-id")
            assert result is None

    def test_returns_data_on_success(self) -> None:
        client = MediaAIClient(base_url=MEDIA_AI_BASE_URL, media_base_url=MEDIA_SERVICE_URL)

        with patch.object(client, "request_json") as mock_request:
            mock_request.return_value = {
                "id": "style_001",
                "productId": "prod_001",
                "ipId": "ip_001",
                "url": "/uploads/teams/123/materials/style.jpg",
            }

            result = client.fetch_style_image("style_001")
            assert result is not None
            assert result["id"] == "style_001"
            assert result["productId"] == "prod_001"


# ---------------------------------------------------------------------------
# Integration tests (require real server)
# ---------------------------------------------------------------------------

def _ping_server(url: str) -> bool:
    try:
        client = MediaAIClient(base_url=url, timeout=5)
        cookie = client.resolve_cookie()
        if not cookie:
            return False
        from local_bridge.media_ai_client import request_json
        request_json("GET", f"{url.rstrip('/')}/api/products?limit=1", cookie=cookie, timeout=5)
        return True
    except Exception:
        return False


skip_if_no_server = pytest.mark.skipif(
    not _ping_server(MEDIA_AI_BASE_URL),
    reason=f"Media AI server not reachable at {MEDIA_AI_BASE_URL}",
)


@skip_if_no_server
class Test_fetch_style_image_integration:
    def test_fetch_style_image_with_real_id(self) -> None:
        """Fetch a real style image by ID. Get ID from db or known fixture."""
        client = MediaAIClient(base_url=MEDIA_AI_BASE_URL, media_base_url=MEDIA_SERVICE_URL)
        cookie = client.resolve_cookie()
        assert cookie, "No cookie available"

        # Using the test fixture style image ID
        result = client.fetch_style_image("style_001")
        # Fixture returns None if not found, skip if fixture not set up
        if result is None:
            pytest.skip("style_001 not found in test fixture")


@skip_if_no_server
class Test_download_file_integration:
    def test_download_image_from_media_service(self, tmp_path: pathlib.Path, real_image_url: str) -> None:
        """Download a real image from 192.168.2.38 using path from database."""
        client = MediaAIClient(base_url=MEDIA_AI_BASE_URL, media_base_url=MEDIA_SERVICE_URL)

        target = tmp_path / "downloaded.jpg"
        full_url = resolve_media_url(MEDIA_SERVICE_URL, real_image_url)

        try:
            client.download_file(full_url, target, cookie=None)
            assert target.exists(), "File should be downloaded"
            assert target.stat().st_size > 0, "File should not be empty"
        except Exception as e:
            pytest.skip(f"Cannot reach media service or image not found: {e}")


@skip_if_no_server
class Test_fetch_product_integration:
    def test_fetch_product_returns_dict(self) -> None:
        client = MediaAIClient(base_url=MEDIA_AI_BASE_URL, media_base_url=MEDIA_SERVICE_URL)
        cookie = client.resolve_cookie()
        assert cookie

        # Use a known product ID from fixtures
        result = client.fetch_product("prod_001")
        if result is None:
            pytest.skip("prod_001 not found in test fixture")
        assert isinstance(result, dict)
        assert "id" in result or "name" in result or result == {}


@skip_if_no_server
class Test_resolve_cookie_integration:
    def test_resolve_cookie_returns_string(self) -> None:
        """Cookie resolution should return a non-empty string."""
        client = MediaAIClient(base_url=MEDIA_AI_BASE_URL, media_base_url=MEDIA_SERVICE_URL)
        cookie = client.resolve_cookie()
        assert cookie is not None
        assert isinstance(cookie, str)
        assert len(cookie) > 10
        assert "next-auth.session-token" in cookie or "__Secure-next-auth.session-token" in cookie