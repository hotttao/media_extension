from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_BRIDGE_URL = "http://127.0.0.1:8765"
TERMINAL_STATUSES = {"completed", "failed", "canceled"}


def request_json(
    method: str,
    url: str,
    *,
    body: dict[str, Any] | None = None,
    timeout: int = 30,
) -> Any:
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")

    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed with HTTP {error.code}: {raw}") from error
    except URLError as error:
        raise RuntimeError(f"{method} {url} failed: {error.reason}") from error


def fetch_jobs(bridge_url: str, timeout: int) -> list[dict[str, Any]]:
    payload = request_json("GET", f"{bridge_url.rstrip('/')}/v1/state", timeout=timeout)
    jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
    return [job for job in jobs if isinstance(job, dict)]


def print_summary(jobs: list[dict[str, Any]]) -> None:
    counts = Counter(str(job.get("status") or "unknown") for job in jobs)
    summary = ", ".join(f"{status}={counts[status]}" for status in sorted(counts)) or "no jobs"
    print(f"Summary: {summary}")


def print_jobs(jobs: list[dict[str, Any]]) -> None:
    if not jobs:
        print("No jobs.")
        return

    print_summary(jobs)
    for job in jobs:
        job_id = str(job.get("id") or "")
        status = str(job.get("status") or "unknown")
        case_file = str(job.get("caseFile") or "")
        failure_reason = job.get("failureReason")
        print(f"- {job_id} [{status}]")
        print(f"  caseFile: {case_file}")
        if failure_reason:
            print(f"  failureReason: {failure_reason}")


def cancel_all_jobs(bridge_url: str, timeout: int, *, force_running: bool) -> int:
    jobs = fetch_jobs(bridge_url, timeout)
    if not jobs:
        print("No jobs.")
        return 0

    print_summary(jobs)
    canceled: list[str] = []
    failed_running: list[str] = []
    skipped: list[tuple[str, str]] = []

    for job in jobs:
        job_id = str(job.get("id") or "")
        status = str(job.get("status") or "unknown")
        if status in TERMINAL_STATUSES:
            skipped.append((job_id, status))
            continue

        if status == "running":
            if not force_running:
                skipped.append((job_id, status))
                continue
            request_json(
                "POST",
                f"{bridge_url.rstrip('/')}/v1/job/{job_id}/fail",
                body={"reason": "bulk canceled by manage_gpt_image_queue.py"},
                timeout=timeout,
            )
            failed_running.append(job_id)
            continue

        request_json(
            "POST",
            f"{bridge_url.rstrip('/')}/v1/job/{job_id}/cancel",
            timeout=timeout,
        )
        canceled.append(job_id)

    if canceled:
        print(f"Canceled pending jobs: {', '.join(canceled)}")
    if failed_running:
        print(f"Failed running jobs: {', '.join(failed_running)}")
    if skipped:
        skipped_text = ", ".join(f"{job_id}({status})" for job_id, status in skipped)
        print(f"Skipped jobs: {skipped_text}")

    refreshed_jobs = fetch_jobs(bridge_url, timeout)
    print_summary(refreshed_jobs)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and clear the local GPT image queue.")
    parser.add_argument("--bridge-url", default=DEFAULT_BRIDGE_URL)
    parser.add_argument("--timeout", type=int, default=30)

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="Show all queue jobs.")

    cancel_parser = subparsers.add_parser("cancel-all", help="Cancel all cancelable jobs in the queue.")
    cancel_parser.add_argument(
        "--force-running",
        action="store_true",
        help="Mark running jobs as failed so the queue is fully cleared.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "list":
        print_jobs(fetch_jobs(args.bridge_url, args.timeout))
        return 0
    if args.command == "cancel-all":
        return cancel_all_jobs(args.bridge_url, args.timeout, force_running=args.force_running)
    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
