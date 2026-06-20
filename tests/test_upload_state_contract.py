from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.evidence_store import upsert_evidence_run
from app.services import upload_jobs, upload_state_repository
from app.services.runtime_db import configure_runtime_dir as configure_runtime_db_dir, db_connection, init_runtime_db
from app.services.upload_jobs import build_empty_latest_upload_record
from app.services.upload_state_repository import (
    read_current_upload_result,
    read_latest_upload_record,
    read_upload_result_by_job_id,
    write_latest_upload_record,
    write_latest_upload_result,
)


def _persisted_result(job_id: str, *, filename: str) -> dict:
    return {
        "job_id": job_id,
        "run_id": job_id,
        "upload_id": job_id,
        "filename": filename,
        "row_count": 6,
        "column_count": 3,
        "columns": ["timestamp", "temperature", "humidity"],
        "preview_rows": [],
        "data_quality": {"readiness": "ready"},
        "engine_result": {"overall_result": "stable"},
        "cultivation_mapping": {"categories": {}},
        "driver_attribution": {},
        "processing_trace": {},
        "processing_stats": {},
        "room_summary": {"room_count": 1, "rooms": [{"room": "Uploaded telemetry", "row_count": 6}]},
        "replay_timeline": {
            "meta": {"frame_count": 1},
            "timeline": [{"timestamp": "2026-05-01T08:00:00+00:00"}],
        },
        "traceability": {"job_id": job_id, "run_id": job_id, "upload_id": job_id},
        "last_processed_at": "2026-05-01T08:05:00+00:00",
        "completed_at": "2026-05-01T08:05:00+00:00",
    }


def test_upload_state_empty_system_returns_no_upload() -> None:
    client = TestClient(create_app())

    payload = client.get("/api/data/latest-upload?include_persisted=1").json()

    assert payload["current_upload"]["status"] == "empty"
    assert payload["current_upload"]["job_id"] is None
    assert payload["job_id"] is None
    assert payload["run_id"] is None
    assert payload["upload_id"] is None
    assert read_current_upload_result() is None


def test_upload_state_valid_upload_returns_canonical_upload() -> None:
    job_id = "upload-state-valid"
    write_latest_upload_result(job_id, _persisted_result(job_id, filename="valid.csv"))

    record = read_latest_upload_record()

    assert record is not None
    assert record["job_id"] == job_id
    assert record["run_id"] == job_id
    assert record["upload_id"] == job_id
    assert read_current_upload_result()["job_id"] == job_id


def test_upload_state_multiple_uploads_preserves_current_and_history_identity() -> None:
    first_job = "upload-state-first"
    second_job = "upload-state-second"
    write_latest_upload_result(first_job, _persisted_result(first_job, filename="first.csv"))
    write_latest_upload_result(second_job, _persisted_result(second_job, filename="second.csv"))

    record = read_latest_upload_record()

    assert record is not None
    assert record["job_id"] == second_job
    assert read_upload_result_by_job_id(first_job)["job_id"] == first_job
    assert read_upload_result_by_job_id(second_job)["job_id"] == second_job


def test_upload_state_repository_latest_write_helpers_persist_canonical_record() -> None:
    job_id = "upload-state-repository-write"
    result = _persisted_result(job_id, filename="repository.csv")

    upload_state_repository.write_latest_upload_result(job_id, result)

    summary = upload_state_repository.read_latest_upload_summary()
    record = upload_state_repository.read_latest_upload_record()

    assert summary is not None
    assert summary["job_id"] == job_id
    assert record is not None
    assert record["job_id"] == job_id
    assert record["result"]["job_id"] == job_id
    assert record["summary"]["job_id"] == job_id


def test_upload_state_repository_latest_summary_write_preserves_matching_result() -> None:
    job_id = "upload-state-summary-write"
    upload_state_repository.write_upload_result(job_id, _persisted_result(job_id, filename="summary.csv"))

    upload_state_repository.write_latest_upload_summary(
        job_id,
        {
            "job_id": job_id,
            "status": "COMPLETE",
            "processing_state": "complete",
            "filename": "summary.csv",
        },
    )

    record = upload_state_repository.read_latest_upload_record()

    assert record is not None
    assert record["summary"]["job_id"] == job_id
    assert record["result"]["job_id"] == job_id


def test_upload_state_repository_write_upload_completion_persists_consistent_artifacts() -> None:
    job_id = "upload-state-completion-write"
    result = _persisted_result(job_id, filename="completion.csv")
    summary = {
        "job_id": job_id,
        "run_id": job_id,
        "upload_id": job_id,
        "status": "COMPLETE",
        "processing_state": "complete",
        "filename": "completion.csv",
        "row_count": 6,
        "column_count": 3,
        "result_available": True,
        "sii_completed": True,
    }

    upload_state_repository.write_upload_completion(job_id, result=result, summary=summary)

    assert upload_state_repository.read_upload_result_by_job_id(job_id)["job_id"] == job_id
    assert upload_state_repository.read_upload_status(job_id)["job_id"] == job_id
    assert upload_state_repository.read_latest_upload_result()["job_id"] == job_id
    assert upload_state_repository.read_latest_upload_summary()["job_id"] == job_id
    record = upload_state_repository.read_latest_upload_record()
    assert record is not None
    assert record["job_id"] == job_id
    assert record["result"]["job_id"] == job_id
    assert record["summary"]["job_id"] == job_id


def test_upload_jobs_write_job_delegates_progress_persistence_to_repository(monkeypatch) -> None:
    calls: list[tuple[str, dict, dict, bool]] = []
    original = upload_jobs.repository_write_upload_status_progress

    def _record(job_id: str, payload: dict, *, latest_summary: dict | None = None, keep_result: bool = False) -> dict:
        calls.append((job_id, dict(payload), dict(latest_summary or {}), keep_result))
        return original(job_id, payload, latest_summary=latest_summary, keep_result=keep_result)

    monkeypatch.setattr(upload_jobs, "repository_write_upload_status_progress", _record)

    upload_jobs.write_job(
        {
            "job_id": "delegated-progress-job",
            "filename": "delegated.csv",
            "status": "PROCESSING",
            "processing_state": "parsing_telemetry",
            "progress": 20,
            "message": "Parsing telemetry.",
        }
    )

    assert len(calls) == 1
    job_id, payload, latest_summary, keep_result = calls[0]
    assert job_id == "delegated-progress-job"
    assert payload["job_id"] == "delegated-progress-job"
    assert latest_summary["job_id"] == "delegated-progress-job"
    assert latest_summary["processing_state"] == "parsing_telemetry"
    assert keep_result is False


def test_upload_jobs_compatibility_write_helpers_remain_stable() -> None:
    job_id = "upload-jobs-compat-write"
    result = _persisted_result(job_id, filename="compat.csv")

    upload_jobs.write_latest_upload_result(job_id, result)

    assert upload_state_repository.read_latest_upload_result()["job_id"] == job_id
    assert upload_state_repository.read_latest_upload_summary()["job_id"] == job_id
    record = upload_state_repository.read_latest_upload_record()
    assert record is not None
    assert record["job_id"] == job_id
    assert read_current_upload_result()["job_id"] == job_id


def test_upload_state_replay_lookup_resolves_correct_upload_identity() -> None:
    first_job = "upload-state-replay-first"
    second_job = "upload-state-replay-second"
    write_latest_upload_result(first_job, _persisted_result(first_job, filename="first.csv"))
    write_latest_upload_result(second_job, _persisted_result(second_job, filename="second.csv"))
    client = TestClient(create_app())

    payload = client.get(f"/api/data/replay/{first_job}").json()

    assert payload["job_id"] == first_job
    assert payload["run_id"] == first_job
    assert payload["upload_id"] == first_job
    assert payload["timeline"]


def test_upload_state_evidence_lookup_resolves_correct_upload_identity() -> None:
    job_id = "upload-state-evidence"
    write_latest_upload_result(job_id, _persisted_result(job_id, filename="evidence.csv"))
    upsert_evidence_run(
        {
            "run_id": job_id,
            "job_id": job_id,
            "upload_id": job_id,
            "source_name": "evidence.csv",
            "source_type": "csv_upload",
            "status": "completed",
            "created_at": "2026-05-01T08:00:00+00:00",
            "completed_at": "2026-05-01T08:05:00+00:00",
            "rows_received": 6,
            "rows_accepted": 6,
            "rows_rejected": 0,
            "sensors_detected": 2,
            "room": "Uploaded telemetry",
            "operating_state": "Monitoring",
            "drift_status": "info",
            "warnings": [],
            "errors": [],
            "primary_drivers": [],
            "evidence_summary": [],
            "structural_archetypes": [],
            "initiated_by": "anonymous",
            "adaptive_site_key": "site::default",
            "operator_feedback_history": [],
            "observation_type": "baseline_shift",
            "observation_status": "completed",
            "variables": ["temperature", "humidity"],
            "drift_metrics": {"replay_frame_count": 1},
            "data_conditions": [],
            "regime_label": "State Group A",
            "structural_state": "Monitoring",
            "deformation_started_at": "2026-05-01T08:00:00+00:00",
            "traceability": {"job_id": job_id, "run_id": job_id, "upload_id": job_id},
        }
    )
    client = TestClient(create_app())

    payload = client.get(f"/api/evidence/runs/{job_id}").json()

    assert payload["run_id"] == job_id
    assert payload["job_id"] == job_id
    assert payload["upload_id"] == job_id
    assert payload["traceability"]["job_id"] == job_id
    assert payload["traceability"]["run_id"] == job_id
    assert payload["traceability"]["upload_id"] == job_id


def test_latest_evidence_prefers_current_upload_identity() -> None:
    first_job = "latest-evidence-first"
    second_job = "latest-evidence-second"
    write_latest_upload_result(first_job, _persisted_result(first_job, filename="first.csv"))
    upsert_evidence_run(
        {
            "run_id": first_job,
            "job_id": first_job,
            "upload_id": first_job,
            "source_name": "first.csv",
            "source_type": "csv_upload",
            "status": "completed",
            "created_at": "2026-05-01T08:00:00+00:00",
            "completed_at": "2026-05-01T08:05:00+00:00",
            "rows_received": 6,
            "rows_accepted": 6,
            "rows_rejected": 0,
            "sensors_detected": 2,
            "room": "Uploaded telemetry",
            "warnings": [],
            "errors": [],
            "primary_drivers": [],
            "evidence_summary": [],
            "structural_archetypes": [],
            "initiated_by": "anonymous",
            "adaptive_site_key": "site::default",
            "operator_feedback_history": [],
            "observation_type": "baseline_shift",
            "observation_status": "completed",
            "variables": ["temperature"],
            "drift_metrics": {"replay_frame_count": 1},
            "data_conditions": [],
            "regime_label": "State Group A",
            "structural_state": "Monitoring",
            "deformation_started_at": "2026-05-01T08:00:00+00:00",
            "traceability": {"job_id": first_job, "run_id": first_job, "upload_id": first_job},
        }
    )
    upsert_evidence_run(
        {
            "run_id": second_job,
            "job_id": second_job,
            "upload_id": second_job,
            "source_name": "second.csv",
            "source_type": "csv_upload",
            "status": "completed",
            "created_at": "2026-05-02T08:00:00+00:00",
            "completed_at": "2026-05-02T08:05:00+00:00",
            "rows_received": 6,
            "rows_accepted": 6,
            "rows_rejected": 0,
            "sensors_detected": 2,
            "room": "Uploaded telemetry",
            "warnings": [],
            "errors": [],
            "primary_drivers": [],
            "evidence_summary": [],
            "structural_archetypes": [],
            "initiated_by": "anonymous",
            "adaptive_site_key": "site::default",
            "operator_feedback_history": [],
            "observation_type": "baseline_shift",
            "observation_status": "completed",
            "variables": ["humidity"],
            "drift_metrics": {"replay_frame_count": 1},
            "data_conditions": [],
            "regime_label": "State Group A",
            "structural_state": "Monitoring",
            "deformation_started_at": "2026-05-02T08:00:00+00:00",
            "traceability": {"job_id": second_job, "run_id": second_job, "upload_id": second_job},
        }
    )
    write_latest_upload_result(first_job, _persisted_result(first_job, filename="first.csv"))
    client = TestClient(create_app())

    payload = client.get("/api/evidence/latest").json()

    assert payload["status"] == "ok"
    assert payload["run"]["run_id"] == first_job


def test_upload_state_missing_persisted_data_fails_safely() -> None:
    job_id = "upload-state-missing"
    write_latest_upload_record(
        {
            "version": 1,
            "status": "complete",
            "message": None,
            "job_id": job_id,
            "run_id": job_id,
            "upload_id": job_id,
            "filename": "missing.csv",
            "session_scope": {
                "active": True,
                "status": "complete",
                "job_id": job_id,
                "run_id": job_id,
                "upload_id": job_id,
                "source_name": "missing.csv",
            },
            "traceability": {"job_id": job_id, "run_id": job_id, "upload_id": job_id},
            "summary": {"job_id": job_id, "status": "COMPLETE", "processing_state": "complete", "filename": "missing.csv"},
            "result": None,
            "replay": {"timeline": [], "frame_count": 0, "replay_ready": False},
            "evidence": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    client = TestClient(create_app())

    payload = client.get("/api/data/latest-upload?include_persisted=1").json()

    assert payload["current_upload"]["status"] == "empty"
    assert payload["latest_result"] is None
    assert payload["job_id"] is None


def test_repository_latest_result_fallback_remains_available_without_canonical_record() -> None:
    job_id = "legacy-latest-result-only"
    stale = _persisted_result(job_id, filename="legacy.csv")

    upload_state_repository.write_local_json("latest_upload_result.json", stale)
    upload_state_repository.write_shared_state("latest_upload_result", stale)

    assert upload_state_repository.read_latest_upload_result()["job_id"] == job_id
    assert upload_state_repository.read_current_upload_result() is None


def test_latest_upload_prefers_canonical_current_upload_result_over_stale_legacy_latest_result() -> None:
    current_job = "canonical-current-upload"
    stale_job = "stale-legacy-upload"
    write_latest_upload_result(current_job, _persisted_result(current_job, filename="current.csv"))
    upload_state_repository.write_latest_upload_result_payload(
        {
            **_persisted_result(stale_job, filename="stale.csv"),
            "session_scope": {
                "active": False,
                "status": "complete",
                "job_id": stale_job,
                "run_id": stale_job,
                "upload_id": stale_job,
                "source_name": "stale.csv",
            },
        }
    )
    client = TestClient(create_app())

    payload = client.get("/api/data/latest-upload?include_persisted=1").json()

    assert payload["current_upload"]["job_id"] == current_job
    assert payload["current_upload"]["result"]["job_id"] == current_job
    assert payload["latest_result"]["job_id"] == current_job


def test_upload_state_corrupted_record_fails_safely() -> None:
    latest_path = Path(upload_jobs.RUNTIME_DIR) / "latest_upload.json"
    latest_path.write_text("{not valid json", encoding="utf-8")
    client = TestClient(create_app())

    payload = client.get("/api/data/latest-upload?include_persisted=1").json()

    assert payload["current_upload"]["status"] == "empty"
    assert payload["current_upload"]["job_id"] is None
    assert payload["latest_result"] is None



def test_upload_state_malformed_runtime_db_payload_fails_safely(tmp_path: Path, monkeypatch) -> None:
    upload_jobs.configure_runtime_dir(tmp_path)
    configure_runtime_db_dir(tmp_path)
    init_runtime_db()
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    with db_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO latest_payloads (key, updated_at, payload_json)
            VALUES ('latest_upload', '2026-06-15T00:00:00+00:00', '{not valid json')
            """
        )
    client = TestClient(create_app())

    payload = client.get("/api/data/latest-upload?include_persisted=1").json()

    assert payload["current_upload"]["status"] == "empty"
    assert payload["latest_result"] is None
    assert payload["job_id"] is None


def test_upload_state_malformed_s3_payload_fails_safely(tmp_path: Path, monkeypatch) -> None:
    class _InvalidBody:
        def read(self) -> bytes:
            return b'{not valid json'

    class _InvalidS3Client:
        def get_object(self, *, Bucket: str, Key: str):
            return {"Body": _InvalidBody()}

    upload_jobs.configure_runtime_dir(tmp_path)
    configure_runtime_db_dir(tmp_path)
    monkeypatch.setenv("NERAIUM_UPLOAD_STATE_BUCKET", "shared-upload-state")
    monkeypatch.setenv("NERAIUM_DISABLE_RUNTIME_DB_LATEST", "1")
    monkeypatch.setattr(upload_state_repository, "_get_s3_client", lambda: _InvalidS3Client())
    client = TestClient(create_app())

    payload = client.get("/api/data/latest-upload?include_persisted=1").json()

    assert payload["current_upload"]["status"] == "empty"
    assert payload["latest_result"] is None
    assert payload["job_id"] is None


def test_reset_flow_does_not_preserve_stale_latest_upload_route_state() -> None:
    job_id = "reset-route-state"
    write_latest_upload_result(job_id, _persisted_result(job_id, filename="reset.csv"))
    client = TestClient(create_app())

    before = client.get("/api/data/latest-upload?include_persisted=1").json()
    reset = client.post("/api/data/reset").json()
    after = client.get("/api/data/latest-upload?include_persisted=1").json()
    second_after = client.get("/api/data/latest-upload?include_persisted=1").json()

    assert before["current_upload"]["job_id"] == job_id
    assert reset["ok"] is True
    assert reset["status"] == "reset"
    assert reset["message"] == "Workspace reset."
    assert reset["session"]["session_state"] == "empty"
    assert after["current_upload"]["status"] == "empty"
    assert after["latest_result"] is None
    assert after["job_id"] is None
    assert second_after["current_upload"]["status"] == "empty"
    assert second_after["latest_result"] is None


def test_write_shared_state_logs_runtime_db_failures(monkeypatch, caplog) -> None:
    monkeypatch.setattr(upload_state_repository, "upsert_latest_payload", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("db down")))
    monkeypatch.setattr(upload_state_repository, "_upload_state_bucket", lambda: "")

    with caplog.at_level("ERROR"):
        upload_state_repository.write_shared_state("latest_upload_result", {"job_id": "log-runtime-db"})

    assert "shared_state_write_failed backend=runtime_db key=latest_upload_result" in caplog.text
