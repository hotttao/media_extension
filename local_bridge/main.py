"""FastAPI application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from local_bridge.api.routers import (
    jobs_router,
    job_claim_router,
    job_progress_router,
    job_result_router,
    job_fail_router,
    job_requeue_router,
    job_cancel_router,
    jobs_cancel_router,
    job_delete_router,
    assets_router,
    single_model_image_router,
    single_style_image_router,
    single_first_frame_router,
    single_jimeng_router,
    job_watch_router,
)
from local_bridge.infrastructure.media_ai_client import MediaAIClient
from local_bridge.infrastructure.persistence import JobStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    # No startup/shutdown needed for this simple app
    yield


def create_app(store: JobStore | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="local_bridge",
        version="1.0.0",
        description="Media AI task queue bridge with OpenAPI docs",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Attach state
    app.state.store = store
    app.state.media_ai_client = MediaAIClient()

    # Static file serving for job manager UI
    static_path = Path(__file__).parent / "static"
    if static_path.exists():
        app.mount("/manage", StaticFiles(directory=str(static_path), html=True), name="manage")

    # Mount routers
    app.include_router(jobs_router, prefix="/v1", tags=["jobs"])
    app.include_router(job_claim_router, prefix="/v1", tags=["job"])
    app.include_router(job_progress_router, prefix="/v1", tags=["job"])
    app.include_router(job_result_router, prefix="/v1", tags=["job"])
    app.include_router(job_fail_router, prefix="/v1", tags=["job"])
    app.include_router(job_requeue_router, prefix="/v1", tags=["job"])
    app.include_router(job_cancel_router, prefix="/v1", tags=["job"])
    app.include_router(jobs_cancel_router, prefix="/v1", tags=["jobs"])
    app.include_router(job_delete_router, prefix="/v1", tags=["job"])
    app.include_router(assets_router, prefix="/v1", tags=["assets"])
    app.include_router(single_model_image_router, prefix="/v1", tags=["single"])
    app.include_router(single_style_image_router, prefix="/v1", tags=["single"])
    app.include_router(single_first_frame_router, prefix="/v1", tags=["single"])
    app.include_router(single_jimeng_router, prefix="/v1", tags=["single"])
    app.include_router(job_watch_router, prefix="/v1", tags=["job"])

    return app


def setup_logging(level: str = "info", log_file: Path | None = None) -> None:
    """Configure logging for local_bridge package. Called once at startup."""
    import logging
    level = level.upper()
    logger = logging.getLogger("local_bridge")
    logger.setLevel(level)
    logger.handlers.clear()
    fmt = logging.Formatter("[%(name)s] %(levelname)s %(message)s")
    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    # Also propagate to root so uvicorn and other libs work
    logging.getLogger().setLevel(level)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--log-level", default="info", choices=["debug", "info", "warning", "error"])
    args = parser.parse_args()

    log_path = Path("runs/bridge.log")
    log_path.parent.mkdir(exist_ok=True)
    setup_logging(level=args.log_level, log_file=log_path)

    uvicorn.run("local_bridge.main:app", host=args.host, port=args.port, reload=False, log_level=args.log_level.lower())


# Module-level app instance for uvicorn --app-dir reference
app = create_app()
