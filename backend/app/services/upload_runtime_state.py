from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
    upload_state_s3_client: Any | None = None

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
        self.latest_upload_cache["summary"] = None
        self.latest_upload_cache["result"] = None
        self.latest_upload_cache["canonical"] = None
        self.upload_state_s3_client = None
        if runtime_changed:
            self.reset_block_persisted = True
        return runtime_changed


UPLOAD_RUNTIME_STATE = UploadRuntimeState()
