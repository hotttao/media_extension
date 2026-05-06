"""Tests for Level-3 business logic functions.

Functions under test:
  - load_case_file(case_path)
  - build_jobs(case_paths, output_root, start_index)
"""

from __future__ import annotations

import pathlib
from unittest.mock import patch

import pytest

from local_bridge.server import build_jobs, load_case_file


class Test_load_case_file:
    def test_loads_prompt_only(self, tmp_path: pathlib.Path) -> None:
        task = tmp_path / "task.md"
        task.write_text("hello world prompt", encoding="utf-8")
        prompt, assets = load_case_file(task)
        assert prompt == "hello world prompt"
        assert assets == []

    def test_extracts_assets(self, tmp_path: pathlib.Path) -> None:
        # Create a real image file
        img = tmp_path / "photo.png"
        img.write_bytes(b"\x00" * 20)

        task = tmp_path / "task.md"
        task.write_text("[图片](photo.png)\n\n生成图片", encoding="utf-8")

        prompt, assets = load_case_file(task)
        assert len(assets) == 1
        assert assets[0]["name"] == "photo.png"
        assert assets[0]["label"] == "图片"

    def test_multiple_assets(self, tmp_path: pathlib.Path) -> None:
        for name in ("a.png", "b.jpg"):
            (tmp_path / name).write_bytes(b"\x00")
        task = tmp_path / "task.md"
        task.write_text("[图1](a.png) and [图2](b.jpg)", encoding="utf-8")
        prompt, assets = load_case_file(task)
        assert len(assets) == 2

    def test_nonexistent_images_ignored(self, tmp_path: pathlib.Path) -> None:
        task = tmp_path / "task.md"
        task.write_text("[missing](nofile.png)\n\nprompt", encoding="utf-8")
        prompt, assets = load_case_file(task)
        assert "nofile.png" in prompt  # link kept since file missing
        assert assets == []

    def test_non_image_links_ignored(self, tmp_path: pathlib.Path) -> None:
        task = tmp_path / "task.md"
        task.write_text("[doc](readme.txt)", encoding="utf-8")
        prompt, assets = load_case_file(task)
        assert "readme.txt" in prompt
        assert assets == []


class Test_build_jobs:
    def test_builds_single_job(self, tmp_path: pathlib.Path) -> None:
        # Create a complete case
        case_dir = tmp_path / "case1"
        case_dir.mkdir()
        (case_dir / "task.md").write_text("generate something", encoding="utf-8")
        (case_dir / "task.media-ai.json").write_text(
            '{"kind": "first-frame-image", "platform": "jimeng", "productId": "p1", "ipId": "i1"}',
            encoding="utf-8",
        )

        jobs = build_jobs([case_dir / "task.md"], tmp_path / "output")
        assert len(jobs) == 1
        job = jobs[0]
        assert job.prompt == "generate something"
        assert job.status == "pending"
        assert job.platform == "jimeng"
        assert job.target_url == "https://jimeng.jianying.com/ai-tool/home/?type=image&workspace=0"

    def test_builds_multiple_jobs(self, tmp_path: pathlib.Path) -> None:
        for i in range(3):
            d = tmp_path / f"case{i}"
            d.mkdir()
            (d / "task.md").write_text(f"prompt {i}", encoding="utf-8")
            (d / "task.media-ai.json").write_text('{"kind": "first-frame-image", "platform": "jimeng", "productId": "p", "ipId": "i"}', encoding="utf-8")

        jobs = build_jobs([tmp_path / f"case{i}/task.md" for i in range(3)], tmp_path / "output")
        assert len(jobs) == 3

    def test_gpt_job_platform(self, tmp_path: pathlib.Path) -> None:
        case_dir = tmp_path / "gpt_case"
        case_dir.mkdir()
        (case_dir / "task.md").write_text("GPT prompt", encoding="utf-8")
        (case_dir / "task.media-ai.json").write_text('{"productId": "p", "ipId": "i"}', encoding="utf-8")

        jobs = build_jobs([case_dir / "task.md"], tmp_path / "output")
        assert len(jobs) == 1
        # GPT job has no platform set (default)
        assert jobs[0].platform is None

    def test_jimeng_video_job(self, tmp_path: pathlib.Path) -> None:
        case_dir = tmp_path / "video_case"
        case_dir.mkdir()
        (case_dir / "task.md").write_text("video prompt", encoding="utf-8")
        (case_dir / "task.media-ai.json").write_text(
            '{"kind": "video", "productId": "p", "ipId": "i", "firstFrameId": "ff"}',
            encoding="utf-8",
        )

        jobs = build_jobs([case_dir / "task.md"], tmp_path / "output")
        assert len(jobs) == 1
        assert jobs[0].platform == "jimeng"
        assert jobs[0].target_url == "https://jimeng.jianying.com/ai-tool/home/?type=video&workspace=0"

    def test_jimeng_video_job_loads_first_frame_from_assets_dir(self, tmp_path: pathlib.Path) -> None:
        job_dir = tmp_path / "jimeng-vid-test"
        input_dir = job_dir / "input"
        assets_dir = input_dir / "assets"
        assets_dir.mkdir(parents=True)

        case_path = input_dir / "task.md"
        case_path.write_text("video prompt only", encoding="utf-8")
        case_path.with_suffix(".media-ai.json").write_text(
            '{"kind": "video", "productId": "p", "ipId": "i", "firstFrameId": "ff"}',
            encoding="utf-8",
        )
        (assets_dir / "first-frame.png").write_bytes(b"\x89PNG\r\n\x1a\n")

        jobs = build_jobs([case_path], tmp_path / "output")

        assert len(jobs) == 1
        assert jobs[0].prompt == "video prompt only"
        assert len(jobs[0].assets) == 1
        assert jobs[0].assets[0]["label"] == "firstFrame"
        assert jobs[0].assets[0]["name"] == "first-frame.png"

    def test_job_id_format(self, tmp_path: pathlib.Path) -> None:
        case_dir = tmp_path / "my-case"
        case_dir.mkdir()
        (case_dir / "task.md").write_text("test", encoding="utf-8")

        jobs = build_jobs([case_dir / "task.md"], tmp_path / "output", start_index=5)
        assert jobs[0].id.startswith("005-")

    def test_output_dir_created(self, tmp_path: pathlib.Path) -> None:
        case_dir = tmp_path / "case1"
        case_dir.mkdir()
        (case_dir / "task.md").write_text("test", encoding="utf-8")
        (case_dir / "task.media-ai.json").write_text('{"productId": "p", "ipId": "i"}', encoding="utf-8")

        output_root = tmp_path / "jobs_output"
        jobs = build_jobs([case_dir / "task.md"], output_root)
        assert jobs[0].output_dir.parent == output_root

    def test_media_ai_sidecar_attached(self, tmp_path: pathlib.Path) -> None:
        case_dir = tmp_path / "case1"
        case_dir.mkdir()
        (case_dir / "task.md").write_text("test", encoding="utf-8")
        (case_dir / "task.media-ai.json").write_text(
            '{"kind": "first-frame-image", "platform": "jimeng", "productId": "p", "ipId": "i", "styleImageId": "s1"}',
            encoding="utf-8",
        )

        jobs = build_jobs([case_dir / "task.md"], tmp_path / "output")
        assert jobs[0].media_ai is not None
        assert jobs[0].media_ai["styleImageId"] == "s1"
    def test_style_image_kind_maps_to_gpt_platform(self, tmp_path: pathlib.Path) -> None:
        """style-image kind should resolve to gpt platform."""
        case_dir = tmp_path / "style_case"
        case_dir.mkdir()
        (case_dir / "task.md").write_text("style prompt", encoding="utf-8")
        (case_dir / "task.media-ai.json").write_text(
            '{"kind": "style-image", "productId": "p", "ipId": "i", "styleImageId": "s1", "sceneId": "sc1"}',
            encoding="utf-8",
        )
        jobs = build_jobs([case_dir / "task.md"], tmp_path / "output")
        assert len(jobs) == 1
        assert jobs[0].platform == "gpt"
        assert jobs[0].target_url is None
        assert jobs[0].media_ai["styleImageId"] == "s1"

    def test_model_image_kind_maps_to_gpt_platform(self, tmp_path: pathlib.Path) -> None:
        """model-image kind should resolve to gpt platform."""
        case_dir = tmp_path / "model_case"
        case_dir.mkdir()
        (case_dir / "task.md").write_text("model prompt", encoding="utf-8")
        (case_dir / "task.media-ai.json").write_text(
            '{"kind": "model-image", "productId": "p", "ipId": "i", "modelImageId": "m1"}',
            encoding="utf-8",
        )
        jobs = build_jobs([case_dir / "task.md"], tmp_path / "output")
        assert len(jobs) == 1
        assert jobs[0].platform == "gpt"
        assert jobs[0].target_url is None

    def test_first_frame_image_kind_maps_to_gpt_platform(self, tmp_path: pathlib.Path) -> None:
        """first-frame-image kind should resolve to gpt platform."""
        case_dir = tmp_path / "ff_case"
        case_dir.mkdir()
        (case_dir / "task.md").write_text("first frame prompt", encoding="utf-8")
        (case_dir / "task.media-ai.json").write_text(
            '{"kind": "first-frame-image", "productId": "p", "ipId": "i", "styleImageId": "s1", "sceneId": "sc1"}',
            encoding="utf-8",
        )
        jobs = build_jobs([case_dir / "task.md"], tmp_path / "output")
        assert len(jobs) == 1
        assert jobs[0].platform == "gpt"
        assert jobs[0].target_url is None

    def test_wrong_sidecar_name_not_read(self, tmp_path: pathlib.Path) -> None:
        """Sidecar named .media-ai.json (old buggy name) should NOT be read."""
        case_dir = tmp_path / "wrong_name_case"
        case_dir.mkdir()
        (case_dir / "task.md").write_text("prompt", encoding="utf-8")
        # Write sidecar with wrong name (old buggy format)
        (case_dir / ".media-ai.json").write_text(
            '{"kind": "jimeng-image", "productId": "should_not_be_read"}',
            encoding="utf-8",
        )
        jobs = build_jobs([case_dir / "task.md"], tmp_path / "output")
        # Sidecar should NOT be loaded; media_ai should be None
        assert jobs[0].media_ai is None
        assert jobs[0].platform is None
