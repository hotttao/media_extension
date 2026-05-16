"""Pydantic schemas for all API request/response models."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------
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
    mediaAi: dict[str, Any] | None = None


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
    mediaAi: dict[str, Any] | None = None


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
class SingleJobCreatedResponse(BaseModel):
    ok: bool
    job: JobInfo | None = None
    dryRun: bool | None = None
    caseFile: str | None = None
    message: str | None = None


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
