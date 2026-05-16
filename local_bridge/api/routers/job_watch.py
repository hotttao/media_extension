"""Router for SSE job status watch."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from local_bridge.infrastructure.events import event_generator

router = APIRouter(tags=["job"])


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
    async def sse_generator():
        try:
            async for event_data in event_generator(job_id=job_id, platform=platform):
                yield event_data
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        finally:
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