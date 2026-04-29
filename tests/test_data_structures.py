"""Tests for Level-4 data structure methods (Job.to_public_dict, public_media_ai).

These tests use real Job dataclass instances and verify serialization.
"""

from __future__ import annotations

import pathlib

import pytest

from local_bridge.server import Job, public_media_ai


class Test_Job_to_public_dict:
    def test_basic_fields(self) -> None:
        job = Job(
            id="001-test",
            case_file=pathlib.Path("case/task.md"),
            prompt="test prompt",
            assets=[],
            output_dir=pathlib.Path("runs/001"),
        )
        result = job.to_public_dict("http://localhost:8765")
        assert result["id"] == "001-test"
        assert result["prompt"] == "test prompt"
        # caseFile is the string representation of the path
        assert "case" in result["caseFile"] and "task.md" in result["caseFile"]

    def test_assets_formatted(self) -> None:
        job = Job(
            id="002-test",
            case_file=pathlib.Path("case/task.md"),
            prompt="prompt",
            assets=[
                {"label": "img1", "name": "photo.png", "mimeType": "image/png", "sha256": "abc123"},
            ],
            output_dir=pathlib.Path("runs/002"),
        )
        result = job.to_public_dict("http://localhost:8765")
        assert len(result["assets"]) == 1
        asset = result["assets"][0]
        assert asset["index"] == 0
        assert asset["label"] == "img1"
        # URL contains the job id and asset index
        assert "002-test" in asset["url"] and "/0" in asset["url"]

    def test_platform_added_when_set(self) -> None:
        job = Job(
            id="003-test",
            case_file=pathlib.Path("case/task.md"),
            prompt="",
            assets=[],
            output_dir=pathlib.Path("runs/003"),
            platform="jimeng_image",
        )
        result = job.to_public_dict("http://localhost:8765")
        assert result["platform"] == "jimeng_image"

    def test_platform_absent_when_none(self) -> None:
        job = Job(
            id="004-test",
            case_file=pathlib.Path("case/task.md"),
            prompt="",
            assets=[],
            output_dir=pathlib.Path("runs/004"),
        )
        result = job.to_public_dict("http://localhost:8765")
        assert "platform" not in result

    def test_target_url_added_when_set(self) -> None:
        job = Job(
            id="005-test",
            case_file=pathlib.Path("case/task.md"),
            prompt="",
            assets=[],
            output_dir=pathlib.Path("runs/005"),
            platform="jimeng_image",
            target_url="https://jimeng.jianying.com/ai-tool/home/?type=image&workspace=0",
        )
        result = job.to_public_dict("http://localhost:8765")
        assert result["targetUrl"] == "https://jimeng.jianying.com/ai-tool/home/?type=image&workspace=0"

    def test_style_image_id_from_media_ai(self) -> None:
        job = Job(
            id="006-test",
            case_file=pathlib.Path("case/task.md"),
            prompt="",
            assets=[],
            output_dir=pathlib.Path("runs/006"),
            media_ai={"styleImageId": "style_abc", "sceneId": "scene_xyz"},
        )
        result = job.to_public_dict("http://localhost:8765")
        assert result["styleImageId"] == "style_abc"
        assert result["sceneId"] == "scene_xyz"

    def test_media_ai_fields_absent_when_not_set(self) -> None:
        job = Job(
            id="007-test",
            case_file=pathlib.Path("case/task.md"),
            prompt="",
            assets=[],
            output_dir=pathlib.Path("runs/007"),
        )
        result = job.to_public_dict("http://localhost:8765")
        assert "styleImageId" not in result
        assert "sceneId" not in result

    def test_timeout_seconds_default(self) -> None:
        job = Job(
            id="008-test",
            case_file=pathlib.Path("case/task.md"),
            prompt="",
            assets=[],
            output_dir=pathlib.Path("runs/008"),
        )
        result = job.to_public_dict("http://localhost:8765")
        assert result["timeoutSeconds"] == 900


class Test_public_media_ai:
    def test_returns_none_when_input_none(self) -> None:
        assert public_media_ai(None) is None

    def test_strips_cookie(self) -> None:
        sidecar = {"kind": "jimeng_image", "productId": "p1", "cookie": "secret"}
        result = public_media_ai(sidecar)
        # cookie should be redacted, not removed
        assert result["cookie"] == "<redacted>"
        assert result["kind"] == "jimeng_image"
        assert result["productId"] == "p1"

    def test_keeps_non_cookie_fields(self) -> None:
        sidecar = {"kind": "jimeng_video", "productId": "p2", "ipId": "i1", "movement": "转身"}
        result = public_media_ai(sidecar)
        assert result["kind"] == "jimeng_video"
        assert result["productId"] == "p2"
        assert result["ipId"] == "i1"
        assert result["movement"] == "转身"

    def test_style_image_id_and_scene_id_preserved(self) -> None:
        sidecar = {
            "kind": "jimeng_image",
            "styleImageId": "s1",
            "sceneId": "scene1",
            "productId": "p1",
        }
        result = public_media_ai(sidecar)
        assert result["styleImageId"] == "s1"
        assert result["sceneId"] == "scene1"