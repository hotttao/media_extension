#!/usr/bin/env python3
"""
Test script for SSE watch interface.
Usage: python scripts/test_watch.py <job_id>
  or   python scripts/test_watch.py  (watch all jobs, will trigger a test event)

Start the bridge first:
  python -m local_bridge.main

Then run this script to test the watch interface.
"""
import asyncio
import sys
import time
import threading
import requests

BRIDGE_URL = "http://localhost:8765"


def trigger_event_via_requeue(job_id: str) -> bool:
    """Trigger a status change by requeueing a job."""
    try:
        r = requests.post(f"{BRIDGE_URL}/v1/job/{job_id}/requeue", timeout=5)
        print(f"  [requeue] status={r.status_code} body={r.text[:200]}")
        return r.status_code == 200
    except Exception as e:
        print(f"  [requeue] error: {e}")
        return False


def trigger_direct_emit(job_id: str):
    """Directly emit an event for testing (bypasses bridge HTTP)."""
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
    from local_bridge.infrastructure.events import emit
    emit({"type": "status_change", "job_id": job_id, "status": "pending", "platform": "gpt"})
    print(f"  [emit] direct event fired for {job_id}")


def submit_a_new_job() -> str | None:
    """Submit a minimal job and return its id."""
    body = {
        "modelImageId": "37be8a2d-f566-4b73-a985-9faa698aa89d",
        "poseId": "7c697d38-0d32-4f8e-ab34-d9474587934c",
        "force": True,
    }
    try:
        r = requests.post(f"{BRIDGE_URL}/v1/single/model-image", json=body, timeout=30)
        data = r.json()
        job = data.get("job")
        if job:
            print(f"  [submit] job created: {job['id']}")
            return job["id"]
        else:
            print(f"  [submit] no job returned: {data}")
            return None
    except Exception as e:
        print(f"  [submit] error: {e}")
        return None


def watch_sse(job_id: str | None = None, timeout: int = 10):
    """Watch SSE stream and print events."""
    params = {}
    if job_id:
        params["job_id"] = job_id

    print(f"\n[watch] Connecting to {BRIDGE_URL}/v1/job/watch?...")
    print(f"[watch] job_id filter: {job_id}")
    print("[watch] Waiting for events (Ctrl+C to stop)...\n")

    try:
        with requests.get(
            f"{BRIDGE_URL}/v1/job/watch",
            params=params,
            stream=True,
            headers={"Accept": "text/event-stream"},
            timeout=timeout,
        ) as r:
            print(f"[watch] HTTP status: {r.status_code}")
            print(f"[watch] Content-Type: {r.headers.get('Content-Type')}")
            print()
            for line in r.iter_lines(decode_unicode=True):
                if line:
                    print(f"  SSE: {line}")
                else:
                    print("  (blank line)")
    except requests.exceptions.Timeout:
        print("[watch] Timeout - no events received")
    except Exception as e:
        print(f"[watch] Error: {e}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Test SSE watch interface")
    parser.add_argument("job_id", nargs="?", help="Job ID to watch (optional)")
    parser.add_argument("--timeout", "-t", type=int, default=150000, help="Watch timeout in seconds")
    parser.add_argument("--trigger", action="store_true", help="Also trigger a test event after connecting")
    args = parser.parse_args()

    job_id = args.job_id

    if not job_id:
        print("=" * 60)
        print("No job_id provided — will watch ALL jobs and trigger a test event")
        print("=" * 60)

        # Check if there are existing jobs
        try:
            r = requests.get(f"{BRIDGE_URL}/v1/state", timeout=5)
            jobs = r.json().get("jobs", [])
            print(f"\nExisting jobs in bridge: {len(jobs)}")
            for j in jobs[:5]:
                print(f"  id={j['id'][:60]}... status={j['status']}")
            if jobs:
                job_id = jobs[0]["id"]
                print(f"\nUsing first job for filter test: {job_id[:40]}...")
        except Exception as e:
            print(f"Could not fetch state: {e}")

    print("\n" + "=" * 60)
    print("Starting SSE watch in background thread...")
    print("=" * 60)

    # Start watch in background thread
    result = {}
    def run_watch():
        try:
            watch_sse(job_id=job_id, timeout=args.timeout)
        except Exception as e:
            result["error"] = str(e)

    watch_thread = threading.Thread(target=run_watch)
    watch_thread.start()

    # Give SSE time to connect
    time.sleep(1.5)

    if args.trigger or not job_id:
        print("\n[main] Triggering test event...")
        print("[main] Option A: requeue an existing job (if we have one)")
        if job_id:
            success = trigger_event_via_requeue(job_id)
            if success:
                print("[main] requeue succeeded, watching for event...")
        if not success if job_id else True:
            print("[main] Option B: direct emit (bypass HTTP)")
            trigger_direct_emit(job_id or "test-job-999")

    # Wait for watch to complete (it'll close after timeout)
    watch_thread.join(timeout=args.timeout + 2)


if __name__ == "__main__":
    main()