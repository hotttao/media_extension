"""JobStore persistence layer. Migrated from server.py."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from local_bridge.domain.models import Job, build_jobs, utc_now_iso, write_json


class JobStore:
    def __init__(self, jobs: list[Job], output_root: pathlib.Path):
        self.jobs = jobs
        self.output_root = output_root
        self.lock = threading.Lock()

    def add_jobs(self, case_paths: list[pathlib.Path]) -> list[Job]:
        with self.lock:
            existing_ids = {job.id for job in self.jobs}
            jobs = build_jobs(case_paths, self.output_root, start_index=len(self.jobs) + 1)
            new_jobs = [j for j in jobs if j.id not in existing_ids]
            self.jobs.extend(new_jobs)
            return new_jobs

    @staticmethod
    def classify_platform(job: Job) -> str:
        if job.platform == "jimeng":
            if job.target_url and "type=video" in job.target_url:
                return "jimeng-video"
            return "jimeng-image"
        return "gpt-image"

    def claim_next_job(self, worker_id: str | None, platform_id: str | None = None) -> Job | None:
        with self.lock:
            for job in self.jobs:
                if job.status != "pending":
                    continue
                if platform_id and self.classify_platform(job) != platform_id:
                    continue
                job.status = "running"
                job.claimed_at = utc_now_iso()
                job.worker_id = worker_id
                job.output_dir.mkdir(parents=True, exist_ok=True)
                (job.output_dir / "prompt.md").write_text(job.prompt, encoding="utf-8")
                from local_bridge.infrastructure.events import emit
                emit({"type": "status_change", "job_id": job.id, "status": "running", "platform": job.platform})
                return job
        return None

    def get_job(self, job_id: str) -> Job | None:
        with self.lock:
            for job in self.jobs:
                if job.id == job_id:
                    return job
        return None

    def mark_completed(self, job_id: str) -> Job:
        with self.lock:
            job = self._get_job_or_raise(job_id)
            job.status = "completed"
            job.finished_at = utc_now_iso()
            from local_bridge.infrastructure.events import emit
            emit({"type": "status_change", "job_id": job.id, "status": "completed", "platform": job.platform})
            return job

    def mark_failed(self, job_id: str, reason: str) -> Job:
        with self.lock:
            job = self._get_job_or_raise(job_id)
            job.status = "failed"
            job.finished_at = utc_now_iso()
            job.failure_reason = reason
            from local_bridge.infrastructure.events import emit
            emit({"type": "status_change", "job_id": job.id, "status": "failed", "platform": job.platform, "reason": reason})
            return job

    def requeue(self, job_id: str) -> Job:
        with self.lock:
            job = self._get_job_or_raise(job_id)
            job.status = "pending"
            job.claimed_at = None
            job.finished_at = None
            job.failure_reason = None
            job.worker_id = None
            return job

    def cancel(self, job_id: str) -> Job:
        with self.lock:
            job = self._get_job_or_raise(job_id)
            if job.status == "running":
                raise RuntimeError("Running jobs cannot be canceled from the local bridge.")
            if job.status in {"completed", "failed"}:
                raise RuntimeError(f"Terminal job cannot be canceled: {job.status}")
            job.status = "canceled"
            job.finished_at = utc_now_iso()
            job.failure_reason = "canceled"
            return job

    def cancel_all(self, platform_id: str | None = None) -> list[Job]:
        with self.lock:
            canceled = []
            for job in self.jobs:
                if platform_id and self.classify_platform(job) != platform_id:
                    continue
                if job.status == "pending":
                    job.status = "canceled"
                    job.finished_at = utc_now_iso()
                    job.failure_reason = "canceled"
                    canceled.append(job)
            return canceled

    def heartbeat(self, job_id: str) -> Job:
        with self.lock:
            job = self._get_job_or_raise(job_id)
            job.claimed_at = utc_now_iso()
            return job

    def add_progress(self, job_id: str, message: str, at: str | None = None, details: Any | None = None) -> Job:
        with self.lock:
            job = self._get_job_or_raise(job_id)
            event: dict[str, Any] = {
                "at": at or utc_now_iso(),
                "message": message,
            }
            if details is not None:
                event["details"] = details
            job.progress.append(event)
            job.output_dir.mkdir(parents=True, exist_ok=True)
            (job.output_dir / "prompt.md").write_text(job.prompt, encoding="utf-8")
            write_json(job.output_dir / "logs.json", job.progress)
            return job

    def summary(self) -> dict[str, Any]:
        with self.lock:
            from local_bridge.domain.models import public_media_ai
            return {
                "jobs": [
                    {
                        "id": job.id,
                        "caseFile": str(job.case_file),
                        "status": job.status,
                        "platform": job.platform,
                        "platformId": self.classify_platform(job),
                        "targetUrl": job.target_url,
                        "createdAt": job.created_at,
                        "claimedAt": job.claimed_at,
                        "finishedAt": job.finished_at,
                        "failureReason": job.failure_reason,
                        "outputDir": str(job.output_dir),
                        "latestProgress": job.progress[-1] if job.progress else None,
                        "progress": list(job.progress),
                        "assets": [
                            {
                                "index": i,
                                "label": a["label"],
                                "name": a["name"],
                                "mimeType": a["mimeType"],
                                "url": f"http://127.0.0.1:8765/v1/assets/{job.id}/{i}",
                            }
                            for i, a in enumerate(job.assets)
                        ],
                        "mediaAi": public_media_ai(job.media_ai),
                    }
                    for job in self.jobs
                ]
            }

    def delete(self, job_id: str) -> Job:
        with self.lock:
            job = self._get_job_or_raise(job_id)
            if job.status == "running":
                raise RuntimeError("Running jobs cannot be deleted.")
            self.jobs.remove(job)
            return job

    def _get_job_or_raise(self, job_id: str) -> Job:
        for job in self.jobs:
            if job.id == job_id:
                return job
        raise KeyError(job_id)
