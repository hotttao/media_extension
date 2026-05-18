"""Router for SSE job status watch."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from local_bridge.infrastructure.events import event_generator

router = APIRouter(tags=["job"])
logger = logging.getLogger("local_bridge.job_watch")


@router.get("/job/watch")
def watch_jobs(
    request: Request,
    job_id: str | None = Query(None, description="Filter events for specific job"),
    platform: str | None = Query(None, description="Filter events for specific platform"),
):
    """
    SSE endpoint to watch job status changes.
    No polling needed - server pushes events on status changes.
    """
    logger.info(f"[watch] SSE connection started job_id={job_id} platform={platform}")

    store = request.app.state.store

    async def sse_generator():
        count = 0

        # If watching a specific job that's already terminal, emit current state and exit immediately
        if job_id:
            job = store.get_job(job_id)
            if job and job.status in ("completed", "failed", "cancelled"):
                event = {"type": "status_change", "job_id": job.id, "status": job.status, "platform": job.platform}
                logger.info(f"[watch] job already terminal, returning immediately: {event}")
                yield f"data: {json.dumps(event)}\n\n"
                yield "data: {\"type\": \"done\"}\n\n"
                return

        try:
            async for event in event_generator(job_id=job_id, platform=platform):
                count += 1
                logger.info(f"[watch] yielding event #{count}: {event}")
                yield f"data: {json.dumps(event)}\n\n"
        except asyncio.CancelledError:
            logger.info(f"[watch] SSE cancelled after {count} events")
        except Exception as e:
            logger.error(f"[watch] SSE error after {count} events: {e}")
        finally:
            logger.info(f"[watch] SSE connection closed, total events sent: {count}")
            yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )