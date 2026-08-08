from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services import upload_jobs, upload_state_repository
from app.services.dataset_scope import (
    build_dataset_scope,
    current_dataset_scope,
    dataset_scope_from_queue_routing,
    set_current_dataset_scope,
)
from app.services.runtime_db import (
    claim_next_upload_job,
    clear_stale_processing_queue_jobs,
    enqueue_upload_job,
    read_upload_job,
    read_upload_queue_job,
)
from app.services.job_progress import complete_progress
from app.services.upload_session_service import resolve_upload_status


class _FakeS3Body:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload


class _FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        ContentType: str | None = None,
        **_kwargs,
    ) -> None:
        del ContentType
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, _FakeS3Body]:
        return {"Body": _FakeS3Body(self.objects[(Bucket, Key)])}

    def list_objects_v2(
        self,
        *,
        Bucket: str,
        Prefix: str,
        ContinuationToken: str | None = None,
    ) -> dict[str, object]:
        del ContinuationToken
        contents = [
            {"Key": key}
            for bucket, key in sorted(self.objects)
            if bucket == Bucket and key.startswith(Prefix)
        ]
        return {"Contents": contents, "IsTruncated": False}


def _configure_shared_runtime(monkeypatch: pytest.MonkeyPatch, fake_s3: _FakeS3Client) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("NERAIUM_UPLOAD_STATE_BUCKET", "shared-upload-state")
    monkeypatch.setattr("app.services.runtime_db._get_s3_client", lambda: fake_s3)
    monkeypatch.setattr(upload_state_repository, "_external_shared_state_enabled", lambda: True)
    # Production keeps a process-local runtime database alongside shared S3.
    # Exercise both so a stale API-local row cannot hide a worker's S3 update.
    monkeypatch.setattr(upload_state_repository, "_runtime_db_latest_enabled", lambda: True)
    monkeypatch.setattr(upload_state_repository, "_get_s3_client", lambda: fake_s3)
    monkeypatch.setattr(upload_state_repository, "_get_s3_state_client", lambda: fake_s3)


def test_split_api_worker_runtime_routes_failure_to_scoped_shared_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_s3 = _FakeS3Client()
    _configure_shared_runtime(monkeypatch, fake_s3)
    api_runtime = tmp_path / "api-runtime"
    worker_runtime = tmp_path / "worker-runtime"
    owner_scope = build_dataset_scope(
        tenant_id="owner@example.com",
        user_id="owner@example.com",
        workspace_id="plant-a",
    )
    other_scope = build_dataset_scope(
        tenant_id="other@example.com",
        user_id="other@example.com",
        workspace_id="plant-b",
    )
    job_id = "split-runtime-job"

    monkeypatch.setenv("NERAIUM_PROCESS_ROLE", "api")
    upload_jobs.configure_runtime_dir(api_runtime)
    set_current_dataset_scope(owner_scope)
    upload_jobs.write_job(
        {
            "job_id": job_id,
            "filename": "owner-upload.csv",
            "file_path": "uploads/missing-owner-upload.csv",
            "file_size_bytes": 128,
            "status": "PENDING",
            "processing_state": "queued",
            "message": "Waiting for a worker to claim this job.",
        }
    )
    enqueue_upload_job(job_id)

    queued = read_upload_queue_job(job_id)
    assert queued is not None
    assert dataset_scope_from_queue_routing(queued) == owner_scope
    assert read_upload_job(job_id) is not None
    queued_status = upload_jobs.read_job(job_id)
    assert queued_status is not None
    queued_progress = queued_status["job_progress"]
    assert queued_progress["contract_version"] == "job-progress.v1"

    monkeypatch.setenv("NERAIUM_PROCESS_ROLE", "worker")
    upload_jobs.configure_runtime_dir(worker_runtime)
    upload_jobs.JOB_RUNTIME_DIRS.clear()
    set_current_dataset_scope(other_scope)
    assert read_upload_job(job_id) is None

    assert upload_jobs.process_next_queued_upload_job() is False
    assert current_dataset_scope() == other_scope
    failed_queue = read_upload_queue_job(job_id)
    assert failed_queue is not None
    assert failed_queue["status"] == "failed"
    assert failed_queue["attempts"] == 1
    assert failed_queue["last_error"] == "missing_upload_file"

    monkeypatch.setenv("NERAIUM_PROCESS_ROLE", "api")
    upload_jobs.configure_runtime_dir(api_runtime)
    upload_jobs.JOB_RUNTIME_DIRS.clear()
    set_current_dataset_scope(owner_scope)
    failed_status = upload_jobs.read_job(job_id)
    assert failed_status is not None
    assert failed_status["status"] == "FAILED"
    assert failed_status["error_type"] == "missing_upload_file"
    assert failed_status["filename"] == "owner-upload.csv"
    assert failed_status["dataset_scope"] == owner_scope.as_dict()
    assert failed_status["job_progress"]["contract_version"] == "job-progress.v1"
    assert failed_status["job_progress"]["status"] == "failed"
    assert (
        failed_status["job_progress"]["overall_percent_complete"]
        == queued_progress["overall_percent_complete"]
    )
    assert failed_status["job_progress"]["overall_percent_complete"] < 100

    set_current_dataset_scope(other_scope)
    assert upload_jobs.read_job(job_id) is None
    other_status = resolve_upload_status(job_id)
    assert other_status["status"] == "NOT_FOUND"
    assert other_status["queue_state"] is None
    other_status_key = (
        "shared-upload-state",
        f"upload-state/scopes/{other_scope.storage_id}/upload_status_{job_id}.json",
    )
    assert other_status_key not in fake_s3.objects


def test_split_runtime_worker_claims_routed_job_and_publishes_terminal_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_s3 = _FakeS3Client()
    _configure_shared_runtime(monkeypatch, fake_s3)
    api_runtime = tmp_path / "success-api-runtime"
    worker_runtime = tmp_path / "success-worker-runtime"
    owner_scope = build_dataset_scope(user_id="owner@example.com", workspace_id="plant-a")
    worker_scope = build_dataset_scope(user_id="worker", workspace_id="default")
    job_id = "split-runtime-success-job"
    dataset_id = "split-runtime-success-dataset"

    monkeypatch.setenv("NERAIUM_PROCESS_ROLE", "api")
    upload_jobs.configure_runtime_dir(api_runtime)
    set_current_dataset_scope(owner_scope)
    upload_jobs.write_job(
        {
            "job_id": job_id,
            "dataset_id": dataset_id,
            "filename": "owner-upload.csv",
            "shared_upload_source_key": (
                f"upload-state/scopes/{owner_scope.storage_id}/upload-sources/{dataset_id}.csv"
            ),
            "status": "PENDING",
            "processing_state": "queued",
            "message": "Waiting for a worker to claim this job.",
        }
    )
    enqueue_upload_job(job_id)

    monkeypatch.setenv("NERAIUM_PROCESS_ROLE", "worker")
    upload_jobs.configure_runtime_dir(worker_runtime)
    upload_jobs.JOB_RUNTIME_DIRS.clear()
    set_current_dataset_scope(worker_scope)
    captured: dict[str, object] = {}

    def restore_source(claimed_job_id: str, source_key: str, *, filename: str | None = None) -> Path:
        assert current_dataset_scope() == owner_scope
        assert claimed_job_id == job_id
        assert source_key.endswith(f"/{dataset_id}.csv")
        restored = upload_jobs.UPLOAD_DIR / (filename or "owner-upload.csv")
        restored.parent.mkdir(parents=True, exist_ok=True)
        restored.write_text("timestamp,flow\n2026-01-01T00:00:00Z,1\n", encoding="utf-8")
        return restored

    def process_csv(path: Path, **kwargs: object) -> dict[str, object]:
        assert current_dataset_scope() == owner_scope
        claimed = read_upload_queue_job(job_id)
        assert claimed is not None
        assert claimed["status"] == "processing"
        assert claimed["attempts"] == 1
        assert claimed["locked_at"]
        captured["claimed"] = True
        current = upload_jobs.read_job(job_id) or {}
        completed_at = datetime.now(timezone.utc).isoformat()
        result = {
            **current,
            "job_id": job_id,
            "dataset_id": dataset_id,
            "filename": kwargs.get("filename") or path.name,
            "status": "COMPLETE",
            "processing_state": "complete",
            "worker_state": "complete",
            "worker_last_seen_at": completed_at,
            "completed_at": completed_at,
            "sii_completed": True,
            "result_available": True,
            "sii_completion_artifacts": {
                "evidence_persisted": True,
                "relationships_persisted": True,
                "behavioral_structure_persisted": True,
                "baseline_persisted": True,
                "final_result_persisted": True,
                "terminal_backend_state_published": True,
            },
            "job_progress": complete_progress(
                current.get("job_progress") if isinstance(current.get("job_progress"), dict) else None,
                job_id=job_id,
                workflow="legacy_analysis",
                message="Analysis ready.",
            ),
        }
        upload_state_repository.write_upload_result(job_id, result)
        upload_jobs.write_job(result)
        return result

    monkeypatch.setattr(upload_jobs.UPLOAD_QUEUE_LIFECYCLE, "restore_upload_source", restore_source)
    monkeypatch.setattr(upload_jobs, "process_csv_file", process_csv)

    assert upload_jobs.process_next_queued_upload_job() is True
    assert captured == {"claimed": True}
    assert current_dataset_scope() == worker_scope
    completed_queue = read_upload_queue_job(job_id)
    assert completed_queue is not None
    assert completed_queue["status"] == "completed"
    assert completed_queue["attempts"] == 1

    monkeypatch.setenv("NERAIUM_PROCESS_ROLE", "api")
    upload_jobs.configure_runtime_dir(api_runtime)
    upload_jobs.JOB_RUNTIME_DIRS.clear()
    set_current_dataset_scope(owner_scope)
    completed = resolve_upload_status(job_id)
    assert completed["status"] == "COMPLETE", completed
    assert completed["dataset_scope"] == owner_scope.as_dict()
    assert completed["job_progress"]["status"] == "completed"
    assert completed["job_progress"]["last_worker_heartbeat_at"]
    assert completed["job_progress"]["overall_percent_complete"] == 100

    set_current_dataset_scope(worker_scope)
    assert resolve_upload_status(job_id)["status"] == "NOT_FOUND"


def test_split_runtime_worker_bootstrap_exception_is_scoped_and_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_s3 = _FakeS3Client()
    _configure_shared_runtime(monkeypatch, fake_s3)
    api_runtime = tmp_path / "bootstrap-api-runtime"
    worker_runtime = tmp_path / "bootstrap-worker-runtime"
    owner_scope = build_dataset_scope(user_id="owner@example.com", workspace_id="plant-a")
    worker_scope = build_dataset_scope(user_id="worker", workspace_id="default")
    job_id = "split-runtime-bootstrap-failure"

    monkeypatch.setenv("NERAIUM_PROCESS_ROLE", "api")
    upload_jobs.configure_runtime_dir(api_runtime)
    set_current_dataset_scope(owner_scope)
    upload_jobs.write_job(
        {
            "job_id": job_id,
            "dataset_id": "bootstrap-dataset",
            "filename": "bootstrap.csv",
            "shared_upload_source_key": "private/source/location.csv",
            "status": "PENDING",
            "processing_state": "queued",
        }
    )
    enqueue_upload_job(job_id)

    monkeypatch.setenv("NERAIUM_PROCESS_ROLE", "worker")
    upload_jobs.configure_runtime_dir(worker_runtime)
    upload_jobs.JOB_RUNTIME_DIRS.clear()
    set_current_dataset_scope(worker_scope)

    def fail_metadata_read(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("sensitive internal storage detail")

    monkeypatch.setattr(
        upload_jobs.UPLOAD_QUEUE_LIFECYCLE,
        "_read_processing_metadata",
        fail_metadata_read,
    )

    assert upload_jobs.process_next_queued_upload_job() is False
    assert current_dataset_scope() == worker_scope
    failed_queue = read_upload_queue_job(job_id)
    assert failed_queue is not None
    assert failed_queue["status"] == "failed"
    assert failed_queue["attempts"] == 1
    assert failed_queue["last_error"] == "upload_worker_bootstrap_failed:RuntimeError"

    monkeypatch.setenv("NERAIUM_PROCESS_ROLE", "api")
    upload_jobs.configure_runtime_dir(api_runtime)
    upload_jobs.JOB_RUNTIME_DIRS.clear()
    set_current_dataset_scope(owner_scope)
    failed = resolve_upload_status(job_id)
    assert failed["status"] == "FAILED"
    assert failed["error_type"] == "upload_worker_bootstrap_failed"
    assert failed["failed_stage"] == "worker_bootstrap"
    assert failed["retryable"] is True
    assert failed["technicalMessage"] == "RuntimeError: upload worker bootstrap failed"
    assert "sensitive internal storage detail" not in json.dumps(failed)

    set_current_dataset_scope(worker_scope)
    assert resolve_upload_status(job_id)["status"] == "NOT_FOUND"


def test_shared_queue_route_cannot_be_replaced_by_another_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_s3 = _FakeS3Client()
    _configure_shared_runtime(monkeypatch, fake_s3)
    monkeypatch.setenv("NERAIUM_PROCESS_ROLE", "api")
    owner_scope = build_dataset_scope(user_id="owner@example.com", workspace_id="plant-a")
    other_scope = build_dataset_scope(user_id="other@example.com", workspace_id="plant-b")

    set_current_dataset_scope(owner_scope)
    enqueue_upload_job("scope-conflict-job")
    set_current_dataset_scope(other_scope)
    with pytest.raises(RuntimeError, match="upload_queue_scope_conflict"):
        enqueue_upload_job("scope-conflict-job")

    queued = read_upload_queue_job("scope-conflict-job")
    assert queued is not None
    assert dataset_scope_from_queue_routing(queued) == owner_scope


def test_split_runtime_stale_recovery_updates_the_routed_scoped_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_s3 = _FakeS3Client()
    _configure_shared_runtime(monkeypatch, fake_s3)
    api_runtime = tmp_path / "stale-api-runtime"
    worker_runtime = tmp_path / "stale-worker-runtime"
    owner_scope = build_dataset_scope(user_id="owner@example.com", workspace_id="plant-a")
    worker_default_scope = build_dataset_scope(user_id="worker", workspace_id="default")
    job_id = "split-runtime-stale-job"

    monkeypatch.setenv("NERAIUM_PROCESS_ROLE", "api")
    upload_jobs.configure_runtime_dir(api_runtime)
    set_current_dataset_scope(owner_scope)
    upload_jobs.write_job(
        {
            "job_id": job_id,
            "filename": "stale.csv",
            "status": "PROCESSING",
            "processing_state": "parsing_telemetry",
            "message": "Parsed 5,000 rows; discovering the source total.",
        }
    )
    enqueue_upload_job(job_id)

    monkeypatch.setenv("NERAIUM_PROCESS_ROLE", "worker")
    upload_jobs.configure_runtime_dir(worker_runtime)
    upload_jobs.JOB_RUNTIME_DIRS.clear()
    set_current_dataset_scope(worker_default_scope)
    assert claim_next_upload_job() == job_id
    assert clear_stale_processing_queue_jobs() == 1
    assert current_dataset_scope() == worker_default_scope

    upload_jobs.configure_runtime_dir(api_runtime)
    upload_jobs.JOB_RUNTIME_DIRS.clear()
    set_current_dataset_scope(owner_scope)
    failed_status = upload_jobs.read_job(job_id)
    assert failed_status is not None
    assert failed_status["status"] == "FAILED"
    assert failed_status["error_type"] == "interrupted_upload"
    assert failed_status["job_progress"]["status"] == "failed"

    set_current_dataset_scope(worker_default_scope)
    assert upload_jobs.read_job(job_id) is None


def test_legacy_shared_queue_record_without_routing_fails_explicitly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_s3 = _FakeS3Client()
    _configure_shared_runtime(monkeypatch, fake_s3)
    monkeypatch.setenv("NERAIUM_PROCESS_ROLE", "worker")
    legacy_job_id = "legacy-unroutable-job"
    owner_scope = build_dataset_scope(user_id="owner@example.com", workspace_id="plant-a")
    set_current_dataset_scope(owner_scope)
    upload_jobs.write_job(
        {
            "job_id": legacy_job_id,
            "filename": "legacy.csv",
            "status": "PENDING",
            "processing_state": "queued",
            "message": "Waiting for a worker to claim this job.",
        }
    )
    fake_s3.objects[
        ("shared-upload-state", f"upload-state/upload-queue/{legacy_job_id}.json")
    ] = json.dumps(
        {
            "job_id": legacy_job_id,
            "status": "pending",
            "attempts": 0,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
    ).encode("utf-8")

    assert upload_jobs.process_next_queued_upload_job() is False

    failed = read_upload_queue_job(legacy_job_id)
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["attempts"] == 1
    assert failed["last_error"] == "upload_queue_routing_missing"
    visible_status = resolve_upload_status(legacy_job_id)
    assert visible_status["status"] == "FAILED"
    assert visible_status["execution_state"] == "failed"
    assert visible_status["error_type"] == "upload_queue_routing_failed"
    assert visible_status["retryable"] is True
    assert "workspace" in visible_status["message"]
    assert visible_status["job_progress"]["status"] == "failed"
