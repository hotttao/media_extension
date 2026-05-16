"""API routers."""
from local_bridge.api.routers.jobs import router as jobs_router
from local_bridge.api.routers.job_claim import router as job_claim_router
from local_bridge.api.routers.job_progress import router as job_progress_router
from local_bridge.api.routers.job_result import router as job_result_router
from local_bridge.api.routers.job_fail import router as job_fail_router
from local_bridge.api.routers.job_requeue import router as job_requeue_router
from local_bridge.api.routers.job_cancel import router as job_cancel_router
from local_bridge.api.routers.jobs_cancel import router as jobs_cancel_router
from local_bridge.api.routers.job_delete import router as job_delete_router
from local_bridge.api.routers.assets import router as assets_router
from local_bridge.api.routers.single_model_image import router as single_model_image_router
from local_bridge.api.routers.single_style_image import router as single_style_image_router
from local_bridge.api.routers.single_first_frame import router as single_first_frame_router
from local_bridge.api.routers.single_jimeng import router as single_jimeng_router
from local_bridge.api.routers.job_watch import router as job_watch_router

__all__ = [
    "jobs_router",
    "job_claim_router",
    "job_progress_router",
    "job_result_router",
    "job_fail_router",
    "job_requeue_router",
    "job_cancel_router",
    "jobs_cancel_router",
    "job_delete_router",
    "assets_router",
    "single_model_image_router",
    "single_style_image_router",
    "single_first_frame_router",
    "single_jimeng_router",
    "job_watch_router",
]
