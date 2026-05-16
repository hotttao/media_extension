"""Pydantic schemas for all API request/response models."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------


class MediaAiInfo(BaseModel):
    """Job sidecar media-ai metadata. Fields vary by job kind."""

    kind: str | None = Field(None, description="Job kind: first-frame-image, style-image, model-image, video")
    platform: str | None = Field(None, description="Execution platform: jimeng or gpt")
    baseUrl: str | None = Field(None, description="Media AI service base URL")
    productId: str | None = Field(None, description="Product ID on Media AI platform")
    productName: str | None = Field(None, description="Product display name")
    ipId: str | None = Field(None, description="IP/character ID")
    styleImageId: str | None = Field(None, description="定妆图 ID (for first-frame-image with jimeng)")
    styleImageUrl: str | None = Field(None, description="定妆图 URL")
    sceneId: str | None = Field(None, description="场景 ID (for first-frame-image with jimeng)")
    sceneName: str | None = Field(None, description="场景名称")
    sceneUrl: str | None = Field(None, description="场景图片 URL")
    uploadSubDir: str | None = Field(None, description="Upload subdirectory on Media AI")
    firstFrameId: str | None = Field(None, description="首帧图 ID (for video)")
    firstFrameUrl: str | None = Field(None, description="首帧图 URL")
    movement: str | None = Field(None, description="动作描述 (for video)")
    modelImageId: str | None = Field(None, description="模特图 ID (for style-image/model-image)")
    poseId: str | None = Field(None, description="姿势 ID (for style-image)")


class ErrorResponse(BaseModel):
    ok: bool = False
    error: str
    detail: str | None = None


# ---------------------------------------------------------------------------
# /v1/jobs
# ---------------------------------------------------------------------------
class JobsCreateRequest(BaseModel):
    caseFiles: list[str] = Field(..., description="List of .md case file paths")
    tasks: list[str] | None = None  # backward compat alias


class AssetResponse(BaseModel):
    index: int
    label: str
    name: str
    mimeType: str
    url: str


class JobInfo(BaseModel):
    id: str
    caseFile: str
    prompt: str | None = None
    mediaAi: MediaAiInfo | None = None


class JobCreatedResponse(BaseModel):
    ok: bool = True
    jobs: list[JobInfo]


# ---------------------------------------------------------------------------
# /v1/state
# ---------------------------------------------------------------------------
class JobStatusResponse(BaseModel):
    id: str
    caseFile: str
    status: str
    platform: str | None = None
    platformId: str | None = None
    targetUrl: str | None = None
    createdAt: str | None = None
    claimedAt: str | None = None
    finishedAt: str | None = None
    failureReason: str | None = None
    outputDir: str | None = None
    latestProgress: dict[str, Any] | None = None
    mediaAi: MediaAiInfo | None = None


class StateResponse(BaseModel):
    jobs: list[JobStatusResponse]


# ---------------------------------------------------------------------------
# /v1/job/claim
# ---------------------------------------------------------------------------
class AssetInfo(BaseModel):
    index: int
    label: str
    name: str
    mimeType: str
    url: str


class JobClaimed(BaseModel):
    id: str
    caseFile: str
    prompt: str | None = None
    assets: list[AssetInfo] = []
    timeoutSeconds: int = 900
    platform: str | None = None
    targetUrl: str | None = None
    styleImageId: str | None = None
    sceneId: str | None = None


class ClaimResponse(BaseModel):
    job: JobClaimed | None = None


# ---------------------------------------------------------------------------
# /v1/job/{id}/progress
# ---------------------------------------------------------------------------
class ProgressUpdateRequest(BaseModel):
    message: str
    at: str | None = None
    details: Any | None = None


class SuccessResponse(BaseModel):
    ok: bool = True


# ---------------------------------------------------------------------------
# /v1/job/{id}/result
# ---------------------------------------------------------------------------
class ImageResult(BaseModel):
    filename: str | None = None
    mimeType: str | None = None
    base64Data: str | None = None
    sourceUrl: str | None = None


class VideoResult(BaseModel):
    filename: str | None = None
    base64Data: str | None = None
    sourceUrl: str | None = None


class ResultSubmitRequest(BaseModel):
    images: list[ImageResult] = []
    videos: list[VideoResult] = []
    assistantResponse: str | None = None
    logs: list[dict[str, Any]] | None = None


class ResultSubmitResponse(BaseModel):
    ok: bool
    savedFiles: list[str] = []
    skippedFiles: list[dict[str, Any]] = []
    mediaAiResults: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# /v1/job/{id}/fail
# ---------------------------------------------------------------------------
class FailSubmitRequest(BaseModel):
    reason: str
    logs: list[dict[str, Any]] | None = None


# ---------------------------------------------------------------------------
# /v1/job/{id}/requeue
# ---------------------------------------------------------------------------
class RequeueResponse(BaseModel):
    ok: bool = True
    jobId: str
    status: str


# ---------------------------------------------------------------------------
# /v1/job/{id}/cancel
# ---------------------------------------------------------------------------
class CancelResponse(BaseModel):
    ok: bool = True
    jobId: str
    status: str


# ---------------------------------------------------------------------------
# /v1/jobs/cancel
# ---------------------------------------------------------------------------
class CancelAllResponse(BaseModel):
    ok: bool = True
    canceled: list[dict[str, str]] = []


# ---------------------------------------------------------------------------
# /v1/job/{id}/delete
# ---------------------------------------------------------------------------
class DeleteResponse(BaseModel):
    ok: bool = True
    jobId: str


# ---------------------------------------------------------------------------
# Single task endpoints
# ---------------------------------------------------------------------------
class SingleJobCreatedResponseBase(BaseModel):
    """公共字段：所有 /v1/single 接口的 response 都继承此类."""
    ok: bool
    dryRun: bool | None = None
    caseFile: str | None = None
    message: str | None = None


# ---- jimeng-image ----
class JimengImageMediaAi(BaseModel):
    """mediaAi for /v1/single/jimeng-image."""
    kind: str = "first-frame-image"
    platform: str = "jimeng"
    baseUrl: str | None = None
    productId: str | None = None
    productName: str | None = None
    ipId: str | None = None
    styleImageId: str | None = None
    styleImageUrl: str | None = None
    sceneId: str | None = None
    sceneName: str | None = None
    sceneUrl: str | None = None
    uploadSubDir: str | None = None


class JimengImageJob(BaseModel):
    id: str
    caseFile: str
    mediaAi: JimengImageMediaAi | None = None


class JimengImageCreatedResponse(SingleJobCreatedResponseBase):
    job: JimengImageJob | None = None


# ---- jimeng-video ----
class JimengVideoMediaAi(BaseModel):
    """mediaAi for /v1/single/jimeng-video."""
    kind: str = "video"
    platform: str = "jimeng"
    baseUrl: str | None = None
    productId: str | None = None
    productName: str | None = None
    ipId: str | None = None
    firstFrameId: str | None = None
    firstFrameUrl: str | None = None
    movement: str | None = None
    uploadSubDir: str | None = None


class JimengVideoJob(BaseModel):
    id: str
    caseFile: str
    mediaAi: JimengVideoMediaAi | None = None


class JimengVideoCreatedResponse(SingleJobCreatedResponseBase):
    job: JimengVideoJob | None = None


# ---- style-image (GPT) ----
class GptStyleImageMediaAi(BaseModel):
    """mediaAi for /v1/single/style-image."""
    kind: str = "style-image"
    platform: str = "gpt"
    baseUrl: str | None = None
    modelImageId: str | None = None
    poseId: str | None = None
    uploadSubDir: str | None = None


class GptStyleImageJob(BaseModel):
    id: str
    caseFile: str
    mediaAi: GptStyleImageMediaAi | None = None


class StyleImageCreatedResponse(SingleJobCreatedResponseBase):
    job: GptStyleImageJob | None = None


# ---- model-image (GPT) ----
class GptModelImageMediaAi(BaseModel):
    """mediaAi for /v1/single/model-image."""
    kind: str = "model-image"
    platform: str = "gpt"
    baseUrl: str | None = None
    productId: str | None = None
    productName: str | None = None
    ipId: str | None = None
    uploadSubDir: str | None = None


class GptModelImageJob(BaseModel):
    id: str
    caseFile: str
    mediaAi: GptModelImageMediaAi | None = None


class ModelImageCreatedResponse(SingleJobCreatedResponseBase):
    job: GptModelImageJob | None = None


# ---- first-frame-image (GPT) ----
class GptFirstFrameImageMediaAi(BaseModel):
    """mediaAi for /v1/single/first-frame-image."""
    kind: str = "first-frame-image"
    platform: str = "gpt"
    baseUrl: str | None = None
    productId: str | None = None
    productName: str | None = None
    ipId: str | None = None
    styleImageId: str | None = None
    sceneId: str | None = None
    uploadSubDir: str | None = None


class GptFirstFrameImageJob(BaseModel):
    id: str
    caseFile: str
    mediaAi: GptFirstFrameImageMediaAi | None = None


class FirstFrameImageCreatedResponse(SingleJobCreatedResponseBase):
    job: GptFirstFrameImageJob | None = None


class JimengImageCreateRequest(BaseModel):
    styleImageId: str
    sceneId: str | None = None
    productId: str | None = None
    ipId: str | None = None
    force: bool = False
    prompt: str | None = None
    noEmbedCookie: bool = False


class JimengVideoCreateRequest(BaseModel):
    productId: str | None = None
    ipId: str | None = None
    firstFrameId: str | None = None
    movementId: str | None = None
    force: bool = False
    prompt: str | None = None
    noEmbedCookie: bool = False


class ModelImageCreateRequest(BaseModel):
    modelImageId: str | None = None
    productId: str | None = None
    ipId: str | None = None
    force: bool = False


class StyleImageCreateRequest(BaseModel):
    modelImageId: str
    poseId: str
    force: bool = False


class FirstFrameImageCreateRequest(BaseModel):
    styleImageId: str
    sceneId: str
    force: bool = False
