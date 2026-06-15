from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.evidence_store import upsert_evidence_run
from app.services import upload_jobs, upload_state_repository
from app.services.runtime_db import configure_runtime_dir as configure_runtime_db_dir, db_connection, init_runtime_db
from app.services.upload_jobs import (
    build_empty_latest_upload_record,
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
    assert reset == {"ok": True, "status": "reset"}
    assert after["current_upload"]["status"] == "empty"
    assert after["latest_result"] is None
    assert after["job_id"] is None
    assert second_after["current_upload"]["status"] == "empty"
    assert second_after["latest_result"] is None
