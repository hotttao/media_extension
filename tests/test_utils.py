"""Tests for Level-1 pure utility functions in local_bridge.server."""

from __future__ import annotations

import json
import pathlib
from unittest.mock import patch

import pytest

from local_bridge.server import (
    ensure_text,
    guess_mime_type,
    sanitize_slug,
    sha256_bytes,
    utc_now_iso,
)
from local_bridge.utils import (
    _load_cached_cookie,
    _save_cached_cookie,
)


class Test_sha256_bytes:
    def test_bytes_input(self) -> None:
        result = sha256_bytes(b"hello")
        # Full SHA256 of "hello" (not truncated)
        assert result == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"

    def test_empty_bytes(self) -> None:
        result = sha256_bytes(b"")
        assert result == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    def test_deterministic(self) -> None:
        data = b"test data"
        assert sha256_bytes(data) == sha256_bytes(data)


class Test_guess_mime_type:
    def test_png(self) -> None:
        path = pathlib.Path("image.png")
        assert guess_mime_type(path) == "image/png"

    def test_jpg(self) -> None:
        path = pathlib.Path("photo.jpg")
        assert guess_mime_type(path) == "image/jpeg"

    def test_jpeg(self) -> None:
        path = pathlib.Path("photo.jpeg")
        assert guess_mime_type(path) == "image/jpeg"

    def test_webp(self) -> None:
        path = pathlib.Path("image.webp")
        # mimetypes on Windows may not register .webp; function falls back to octet-stream
        # Just verify it returns a string and doesn't crash
        result = guess_mime_type(path)
        assert isinstance(result, str)
        assert "/" in result  # valid mime type format

    def test_unknown_extension(self) -> None:
        path = pathlib.Path("file.xyz")
        assert guess_mime_type(path) == "application/octet-stream"


class Test_ensure_text:
    def test_string_passthrough(self) -> None:
        assert ensure_text("hello") == "hello"
        assert ensure_text("") == ""

    def test_none(self) -> None:
        result = ensure_text(None)
        assert isinstance(result, str)
        assert result == "null"

    def test_int(self) -> None:
        assert ensure_text(123) == "123"

    def test_dict(self) -> None:
        result = ensure_text({"a": 1})
        assert isinstance(result, str)
        assert "a" in result


class Test_sanitize_slug:
    def test_lowercase(self) -> None:
        assert sanitize_slug("Hello World") == "hello-world"

    def test_special_chars_removed(self) -> None:
        assert sanitize_slug("Test@#!File") == "test-file"

    def test_multiple_dashes(self) -> None:
        assert sanitize_slug("foo  bar  baz") == "foo-bar-baz"

    def test_strip_leading_trailing_dashes(self) -> None:
        assert sanitize_slug("##test##") == "test"

    def test_empty_string(self) -> None:
        assert sanitize_slug("") == "job"
        assert sanitize_slug("@@@") == "job"


class Test_utc_now_iso:
    def test_format(self) -> None:
        result = utc_now_iso()
        # ISO 8601 format with timezone
        assert "T" in result
        assert result.endswith("Z") or "+" in result or "-" in result[10:]

    def test_deterministic_enough(self) -> None:
        # Just ensure it returns without error and is a valid string
        result = utc_now_iso()
        assert isinstance(result, str)
        assert len(result) > 0


class Test_cookie_cache:
    """Tests for persistent cookie caching (_save_cached_cookie / _load_cached_cookie)."""

    def test_save_and_load(self, tmp_path: pathlib.Path) -> None:
        fake_cache = tmp_path / "cookie_cache.json"
        with patch("local_bridge.utils._COOKIE_CACHE_FILE", fake_cache):
            _save_cached_cookie("session-token-abc123")
            loaded = _load_cached_cookie("http://localhost:3000", timeout=10)
            assert loaded == "session-token-abc123"

    def test_load_missing_file_returns_none(self, tmp_path: pathlib.Path) -> None:
        fake_cache = tmp_path / "nonexistent.json"
        with patch("local_bridge.utils._COOKIE_CACHE_FILE", fake_cache):
            # No cache file exists — should return None without error
            result = _load_cached_cookie("http://localhost:3000", timeout=10)
            assert result is None

    def test_load_corrupted_json_returns_none(self, tmp_path: pathlib.Path) -> None:
        fake_cache = tmp_path / "bad.json"
        fake_cache.write_text("not valid json {", encoding="utf-8")
        with patch("local_bridge.utils._COOKIE_CACHE_FILE", fake_cache):
            result = _load_cached_cookie("http://localhost:3000", timeout=10)
            assert result is None

    def test_load_empty_cookie_returns_none(self, tmp_path: pathlib.Path) -> None:
        fake_cache = tmp_path / "empty.json"
        fake_cache.write_text(json.dumps({"cookie": "  "}), encoding="utf-8")
        with patch("local_bridge.utils._COOKIE_CACHE_FILE", fake_cache):
            result = _load_cached_cookie("http://localhost:3000", timeout=10)
            assert result is None

    def test_load_validates_before_return(self, tmp_path: pathlib.Path) -> None:
        """When cache file exists but cookie is expired (401/403), returns None and deletes cache."""
        fake_cache = tmp_path / "expired.json"
        fake_cache.write_text(json.dumps({"cookie": "expired-token"}), encoding="utf-8")

        # Mock _validate_cookie_via_api to return False (expired)
        with patch("local_bridge.utils._COOKIE_CACHE_FILE", fake_cache), \
             patch("local_bridge.utils._validate_cookie_via_api", return_value=False):
            result = _load_cached_cookie("http://localhost:3000", timeout=10)
            assert result is None
            # Cache file should be deleted
            assert not fake_cache.exists()

    def test_load_returns_cookie_when_validation_passes(self, tmp_path: pathlib.Path) -> None:
        """Cache file is preserved when cookie is still valid."""
        fake_cache = tmp_path / "valid.json"
        fake_cache.write_text(json.dumps({"cookie": "valid-token"}), encoding="utf-8")

        with patch("local_bridge.utils._COOKIE_CACHE_FILE", fake_cache), \
             patch("local_bridge.utils._validate_cookie_via_api", return_value=True):
            result = _load_cached_cookie("http://localhost:3000", timeout=10)
            assert result == "valid-token"
            # Cache file should still exist
            assert fake_cache.exists()
