"""Event bus for job status change notifications."""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Callable

_observers: list[Callable[[dict[str, Any]], None]] = []
_lock = threading.Lock()
_logger = logging.getLogger("local_bridge.events")


def emit(event: dict[str, Any]) -> None:
    """Emit an event to all observers. Thread-safe."""
    _logger.info(f"[emit] thread={threading.current_thread().name} event={event}")
    with _lock:
        _logger.info(f"[emit] observers count={len(_observers)}")
        for i, callback in enumerate(_observers):
            try:
                _logger.info(f"[emit] calling observer[{i}]...")
                callback(event)
                _logger.info(f"[emit] observer[{i}] completed")
            except Exception as e:
                _logger.warning(f"[emit] observer[{i}] raised: {e}")


def subscribe(callback: Callable[[dict[str, Any]], None]) -> None:
    """Subscribe a callback to receive job events."""
    with _lock:
        _observers.append(callback)
    _logger.info(f"[subscribe] total observers: {len(_observers)}, callback_id={id(callback)}")


def unsubscribe(callback: Callable[[dict, Any], None]) -> None:
    """Unsubscribe a callback."""
    with _lock:
        if callback in _observers:
            _observers.remove(callback)
    _logger.debug(f"[unsubscribe] total observers: {len(_observers)}")


# Per-generator queue registry for cleanup
_queue_registry: dict[int, asyncio.Queue] = {}
_registry_lock = threading.Lock()


async def event_generator(
    job_id: str | None = None,
    platform: str | None = None,
) -> Any:
    """
    Async generator that yields job events as SSE data.
    Optionally filter by job_id or platform.

    Design: Each generator has its own asyncio.Queue. The observer
    puts events into the queue directly (no event-loop crossing).
    This decouples the sync fire-and-forget emit() from async consumption.
    """
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    generator_id = id(queue)

    # Register queue for potential cleanup
    with _registry_lock:
        _queue_registry[generator_id] = queue

    _logger.info(f"[event_generator] started id={generator_id} job_id={job_id} platform={platform}")

    def observer(event: dict[str, Any]) -> None:
        # Filter by job_id if specified
        if job_id and event.get("job_id") != job_id:
            _logger.debug(f"[observer] filtered out by job_id: {event.get('job_id')} != {job_id}")
            return
        # Filter by platform if specified
        if platform and event.get("platform") != platform:
            _logger.debug(f"[observer] filtered out by platform: {event.get('platform')} != {platform}")
            return
        _logger.info(f"[observer] matched event: {event}")
        # Put into queue directly — no asyncio loop crossing needed
        try:
            queue.put_nowait(event)
            _logger.info(f"[observer] put_nowait succeeded, queue.qsize={queue.qsize()}")
        except asyncio.QueueFull:
            _logger.warning(f"[observer] queue full, dropping event: {event}")

    subscribe(observer)
    try:
        while True:
            _logger.debug("[event_generator] waiting on queue.get()...")
            event = await queue.get()
            if event is None:  # Sentinel to stop
                _logger.debug("[event_generator] got sentinel, exiting")
                break
            _logger.info(f"[event_generator] yielding event: {event}")
            yield event
            # Stop after terminal events so SSE closes promptly
            if event.get("status") in ("completed", "failed", "cancelled"):
                _logger.info("[event_generator] terminal event received, sending stop sentinel")
                await queue.put(None)
    except GeneratorExit:
        _logger.info("[event_generator] GeneratorExit")
    finally:
        unsubscribe(observer)
        with _registry_lock:
            _queue_registry.pop(generator_id, None)
        _logger.info("[event_generator] stopped")