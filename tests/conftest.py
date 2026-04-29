"""Pytest configuration and shared fixtures for local_bridge tests."""

from __future__ import annotations

import pathlib
import tempfile
from typing import Any

import pytest

FIXTURE_ROOT = pathlib.Path(__file__).parent / "fixtures"
JIMENG_IMAGE_CASE = FIXTURE_ROOT / "cases" / "jimeng_image_case"
JIMENG_VIDEO_CASE = FIXTURE_ROOT / "cases" / "jimeng_video_case"
GPT_CASE = FIXTURE_ROOT / "cases" / "gpt_case"


@pytest.fixture
def temp_output_root(tmp_path: pathlib.Path) -> pathlib.Path:
    """Temporary output root for job files."""
    return tmp_path


@pytest.fixture
def sample_image_png(tmp_path: pathlib.Path) -> pathlib.Path:
    """Small valid PNG file for testing asset handling."""
    # 1x1 red pixel PNG
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
        b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
        b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    path = tmp_path / "test.png"
    path.write_bytes(png_bytes)
    return path


@pytest.fixture
def sample_image_jpg(tmp_path: pathlib.Path) -> pathlib.Path:
    """Small valid JPEG file for testing asset handling."""
    # Minimal valid JPEG (1x1 pixel)
    jpg_bytes = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00"
        b"\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\x08\x06\x06"
        b"\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r"
        b"\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f"
        b"\x1e\x1d\x1a\x1c\x1c $.\' \",#\x1c\x1c(#\x1c\x1c\x1c"
        b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11"
        b"\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01"
        b"\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01"
        b"\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00"
        b"\xb5\x10\x00\x02\x01\x03\x03\x03\x02\x04\x03\x05"
        b"\x05\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11"
        b"\x05\x12\x21\x31\x41\x06\x13\x51\x61\x07\x22\x71"
        b"\x14\x32\x81\x91\xa1\x08#\x42\xb1\xc1\x15R\xd1\xf0"
        b"$3br\x82\x09\x0a\x16\x17\x18\x19\x1a%&\'()*456789"
        b":CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86"
        b"\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99"
        b"\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3"
        b"\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6"
        b"\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9"
        b"\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1"
        b"\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00"
        b"\x08\x01\x01\x00\x00?\x00\xbf\xff\xd9"
    )
    path = tmp_path / "test.jpg"
    path.write_bytes(jpg_bytes)
    return path


@pytest.fixture
def case_with_images(tmp_path: pathlib.Path, sample_image_png: pathlib.Path) -> pathlib.Path:
    """A task.md alongside three image files for testing replace_image_links."""
    case_dir = tmp_path / "case_with_images"
    case_dir.mkdir()
    (case_dir / "person.png").write_bytes(sample_image_png.read_bytes())
    (case_dir / "clothing.png").write_bytes(sample_image_png.read_bytes())
    (case_dir / "scene.png").write_bytes(sample_image_png.read_bytes())
    (case_dir / "task.md").write_text(
        "[图片一：人物](person.png)\n[图片二：服装](clothing.png)\n[图片三：场景](scene.png)\n\nprompt here",
        encoding="utf-8",
    )
    return case_dir / "task.md"


@pytest.fixture
def jimeng_image_sidecar() -> dict[str, Any]:
    """Minimal jimeng_image sidecar dict."""
    return {
        "kind": "jimeng_image",
        "baseUrl": "http://localhost:3000",
        "productId": "prod_001",
        "productName": "Test Product",
        "ipId": "ip_001",
        "styleImageId": "style_001",
        "sceneId": "scene_001",
        "uploadSubDir": "first-frames",
    }


@pytest.fixture
def jimeng_video_sidecar() -> dict[str, Any]:
    """Minimal jimeng_video sidecar dict."""
    return {
        "kind": "jimeng_video",
        "baseUrl": "http://localhost:3000",
        "productId": "prod_002",
        "ipId": "ip_002",
        "firstFrameId": "ff_001",
        "movement": "缓慢转身展示服装",
    }


@pytest.fixture
def gpt_sidecar() -> dict[str, Any]:
    """Minimal GPT model-image sidecar dict."""
    return {
        "baseUrl": "http://localhost:3000",
        "productId": "prod_003",
        "ipId": "ip_003",
        "uploadSubDir": "model-images",
    }