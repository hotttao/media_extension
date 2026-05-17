"""Event bus for job status change notifications."""
from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable

_observers: list[Callable[[dict[str, Any]], None]] = []
_lock = threading.Lock()
_sse_loop: asyncio.AbstractEventLoop | None = None


def emit(event: dict[str, Any]) -> None:
    """Emit an event to all observers. Thread-safe."""
    with _lock:
        for callback in _observers:
            try:
                callback(event)
            except Exception:
                pass  # Don't let one observer crash the bus


def subscribe(callback: Callable[[dict[str, Any]], None]) -> None:
    """Subscribe a callback to receive job events."""
    with _lock:
        _observers.append(callback)


def unsubscribe(callback: Callable[[dict, Any], None]) -> None:
    """Unsubscribe a callback."""
    with _lock:
        if callback in _observers:
            _observers.remove(callback)


async def event_generator(
    job_id: str | None = None,
    platform: str | None = None,
) -> Any:
    """
    Async generator that yields job events as SSE data.
    Optionally filter by job_id or platform.
    """
    global _sse_loop
    _sse_loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    def observer(event: dict[str, Any]) -> None:
        # Filter by job_id if specified
        if job_id and event.get("job_id") != job_id:
            return
        # Filter by platform if specified
        if platform and event.get("platform") != platform:
            return
        # Use the SSE request's event loop (stored at subscription time)
        loop = _sse_loop
        if loop and not loop.is_closed():
            asyncio.run_coroutine_threadsafe(queue.put(event), loop)

    subscribe(observer)
    try:
        while True:
            event = await queue.get()
            if event is None:  # Sentinel to stop
                break
            yield f"data: {event}\n\n"
    except GeneratorExit:
        pass
    finally:
        unsubscribe(observer)
        _sse_loop = None