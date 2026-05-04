"""API routers."""
from local_bridge.api.routers import (
    jobs,
    job_claim,
    job_progress,
    job_result,
    job_fail,
    job_requeue,
    job_cancel,
    jobs_cancel,
    single_model_image,
    single_style_image,
    single_first_frame,
    single_jimeng,
)

__all__ = [
    "jobs",
    "job_claim",
    "job_progress",
    "job_result",
    "job_fail",
    "job_requeue",
    "job_cancel",
    "jobs_cancel",
    "single_model_image",
    "single_style_image",
    "single_first_frame",
    "single_jimeng",
]