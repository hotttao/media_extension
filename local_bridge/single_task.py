"""Reusable task builders for Media AI image workflows.

All core logic moved to media_ai_client.MediaAIClient.
This module re-exports the client and its task-builder methods for backward compatibility.
"""

from local_bridge.media_ai_client import (
    MediaAIClient,
    load_media_ai_sidecar,
    resolve_media_url,
    extension_from_url,
    guess_mime_type,
    sha256_bytes,
    slugify,
)

# Backward compatibility: module-level functions delegate to a default client instance
_default_client: MediaAIClient | None = None


def _get_client() -> MediaAIClient:
    global _default_client
    if _default_client is None:
        _default_client = MediaAIClient()
    return _default_client


def resolve_cookie(cookie: str | None = None) -> str | None:
    return _get_client().resolve_cookie(cookie)


def download_file(url: str, target, *, cookie: str | None = None, timeout: int = 120):
    return _get_client().download_file(url, target, cookie=cookie)


def fetch_model_image(model_image_id: str, *, cookie: str | None = None, timeout: int = 120):
    return _get_client().fetch_model_image(model_image_id)


def fetch_style_image(style_image_id: str, *, cookie: str | None = None, timeout: int = 120):
    return _get_client().fetch_style_image(style_image_id)


def fetch_pose(pose_id: str, *, cookie: str | None = None, timeout: int = 120):
    return _get_client().fetch_pose(pose_id)


def fetch_scene(scene_id: str, *, cookie: str | None = None, timeout: int = 120):
    return _get_client().fetch_scene(scene_id)


def fetch_first_frame(first_frame_id: str, *, cookie: str | None = None, timeout: int = 120):
    return _get_client().fetch_first_frame(first_frame_id)


def build_model_image_task(*args, **kwargs):
    return _get_client().build_model_image_task(*args, **kwargs)


def build_style_image_task(*args, **kwargs):
    return _get_client().build_style_image_task(*args, **kwargs)


def build_first_frame_task(*args, **kwargs):
    return _get_client().build_first_frame_task(*args, **kwargs)


__all__ = [
    "MediaAIClient",
    "build_first_frame_task",
    "build_model_image_task",
    "build_style_image_task",
    "download_file",
    "fetch_first_frame",
    "fetch_model_image",
    "fetch_pose",
    "fetch_scene",
    "fetch_style_image",
    "guess_mime_type",
    "load_media_ai_sidecar",
    "resolve_cookie",
    "resolve_media_url",
    "extension_from_url",
    "sha256_bytes",
    "slugify",
]
