"""Tests for Level-2 string/file processing functions.

Functions under test:
  - replace_image_links(markdown_text, case_dir)
  - load_media_ai_sidecar(case_path)
"""

from __future__ import annotations

import json
import pathlib

import pytest

from local_bridge.server import load_media_ai_sidecar, replace_image_links

FIXTURE_ROOT = pathlib.Path(__file__).parent / "fixtures"


class Test_replace_image_links:
    def test_no_links(self, tmp_path: pathlib.Path) -> None:
        text = "hello world"
        prompt, assets = replace_image_links(text, tmp_path)
        assert prompt == "hello world"
        assert assets == []

    def test_single_image_link(self, tmp_path: pathlib.Path) -> None:
        img = tmp_path / "photo.png"
        img.write_bytes(b"\x00" * 10)
        text = "see [photo](photo.png)"
        prompt, assets = replace_image_links(text, tmp_path)
        assert "photo.png" not in prompt
        assert len(assets) == 1
        assert assets[0]["label"] == "photo"
        assert assets[0]["name"] == "photo.png"

    def test_multiple_image_links(self, tmp_path: pathlib.Path) -> None:
        for name in ("a.png", "b.jpg"):
            (tmp_path / name).write_bytes(b"\x00" * 10)
        text = "[图1](a.png) and [图2](b.jpg)"
        _, assets = replace_image_links(text, tmp_path)
        assert len(assets) == 2
        assert assets[0]["label"] == "图1"
        assert assets[1]["label"] == "图2"

    def test_duplicate_link_same_label(self, tmp_path: pathlib.Path) -> None:
        img = tmp_path / "img.png"
        img.write_bytes(b"\x00" * 10)
        text = "[same](img.png) and [same](img.png) again"
        _, assets = replace_image_links(text, tmp_path)
        # Same path appears twice but only one asset
        assert len(assets) == 1

    def test_non_image_link_ignored(self, tmp_path: pathlib.Path) -> None:
        text = "[doc](readme.md)"
        prompt, assets = replace_image_links(text, tmp_path)
        # .md is not in IMAGE_SUFFIXES so it stays as-is
        assert "readme.md" in prompt
        assert assets == []

    def test_missing_file_ignored(self, tmp_path: pathlib.Path) -> None:
        text = "[missing](nofile.png)"
        prompt, assets = replace_image_links(text, tmp_path)
        assert "nofile.png" in prompt  # link preserved since file doesn't exist
        assert assets == []

    def test_label_extraction(self, tmp_path: pathlib.Path) -> None:
        (tmp_path / "x.jpg").write_bytes(b"\x00")
        _, assets = replace_image_links("[图片一：人物](x.jpg)", tmp_path)
        assert assets[0]["label"] == "图片一：人物"

    def test_asset_has_sha256(self, tmp_path: pathlib.Path) -> None:
        content = b"hello world"
        (tmp_path / "test.png").write_bytes(content)
        _, assets = replace_image_links("[img](test.png)", tmp_path)
        import hashlib
        expected = hashlib.sha256(content).hexdigest()
        assert assets[0]["sha256"] == expected


class Test_load_media_ai_sidecar:
    def test_loads_valid_sidecar(self) -> None:
        case_path = FIXTURE_ROOT / "cases" / "jimeng_image_case" / "task.md"
        sidecar = load_media_ai_sidecar(case_path)
        assert sidecar is not None
        assert sidecar["kind"] == "first-frame-image"
        assert sidecar["productId"] == "prod_001"
        assert sidecar["ipId"] == "ip_001"
        assert sidecar["productId"] == "prod_001"
        assert sidecar["ipId"] == "ip_001"

    def test_missing_sidecar_returns_none(self, tmp_path: pathlib.Path) -> None:
        # A path with no sidecar file (task.media-ai.json not present)
        task = tmp_path / "task.md"
        task.write_text("hello")
        result = load_media_ai_sidecar(task)
        assert result is None

    def test_invalid_json_returns_none(self, tmp_path: pathlib.Path) -> None:
        task = tmp_path / "task.md"
        task.write_text("hello")
        (tmp_path / "task.media-ai.json").write_text("not valid json {", encoding="utf-8")
        result = load_media_ai_sidecar(task)
        assert result is None

    def test_video_sidecar(self) -> None:
        case_path = FIXTURE_ROOT / "cases" / "jimeng_video_case" / "task.md"
        sidecar = load_media_ai_sidecar(case_path)
        assert sidecar is not None
        assert sidecar["kind"] == "video"
        assert sidecar["firstFrameId"] == "ff_001"
        assert sidecar["movement"] == "缓慢转身展示服装"

    def test_gpt_sidecar(self) -> None:
        case_path = FIXTURE_ROOT / "cases" / "gpt_case" / "task.md"
        sidecar = load_media_ai_sidecar(case_path)
        assert sidecar is not None
        assert "kind" not in sidecar  # GPT uses model-image default
        assert sidecar["productId"] == "prod_003"