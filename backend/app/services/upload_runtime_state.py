from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_MAX_CACHED_UPLOAD_JOBS = 1000


@dataclass
class UploadRuntimeState:
    runtime_dir: Path = Path("backend/runtime")
    upload_dir: Path = Path("backend/runtime/uploads")
    job_dir: Path = Path("backend/runtime/upload_jobs")
    legacy_job_dir: Path = Path("backend/runtime/jobs")
    jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    latest_upload_cache: dict[str, Any] = field(
        default_factory=lambda: {"summary": None, "result": None, "canonical": None}
    )
    reset_block_persisted: bool = False
    reset_blocked_scopes: set[str] = field(default_factory=set)
    upload_state_s3_client: Any | None = None
    max_cached_jobs: int = DEFAULT_MAX_CACHED_UPLOAD_JOBS

    def cache_job(self, job_id: str, payload: dict[str, Any]) -> list[str]:
        normalized_id = str(job_id)
        self.jobs.pop(normalized_id, None)
        self.jobs[normalized_id] = payload
        evicted: list[str] = []
        while len(self.jobs) > max(int(self.max_cached_jobs), 1):
            oldest_id = next(iter(self.jobs))
            self.jobs.pop(oldest_id, None)
            evicted.append(oldest_id)
        return evicted

    def configure_runtime_dir(self, path: str | Path) -> bool:
        next_runtime_dir = Path(path)
        runtime_changed = next_runtime_dir != self.runtime_dir
        self.runtime_dir = next_runtime_dir
        self.upload_dir = next_runtime_dir / "uploads"
        self.job_dir = next_runtime_dir / "upload_jobs"
        self.legacy_job_dir = next_runtime_dir / "jobs"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.job_dir.mkdir(parents=True, exist_ok=True)
        self.legacy_job_dir.mkdir(parents=True, exist_ok=True)
        self.jobs.clear()
        self.latest_upload_cache.clear()
        self.latest_upload_cache.update({"summary": None, "result": None, "canonical": None})
        self.reset_blocked_scopes.clear()
        self.upload_state_s3_client = None
        if runtime_changed:
            self.reset_block_persisted = True
        return runtime_changed


UPLOAD_RUNTIME_STATE = UploadRuntimeState()
