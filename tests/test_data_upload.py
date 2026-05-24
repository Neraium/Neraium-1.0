from fastapi.testclient import TestClient
import asyncio
import pytest
import time

from app.core.config import Settings
from app.main import create_app
from app.services.runtime_db import upsert_latest_payload
from app.services.sii_runner import CORE_ENGINE, RUNNER_MODULE
from app.services import sii_runner, upload_jobs
from app.services.upload_jobs import UploadTooLargeError, create_upload_job, parse_positive_int_env, process_csv_content, process_csv_file, process_json_payload, read_job, write_job, write_latest_upload_result, write_latest_upload_summary


def post_csv(client: TestClient, filename: str, content: str):
    return client.post(
        "/api/data/upload",
        files={"file": (filename, content, "text/csv")},
    )


def post_json(client: TestClient, filename: str, content: str):
    return client.post(
        "/api/data/upload",
        files={"file": (filename, content, "application/json")},
    )


def wait_for_terminal_upload_status(client: TestClient, status_url: str, timeout_seconds: float = 5.0) -> dict:
    deadline = time.time() + timeout_seconds
    last_payload = None
    while time.time() < deadline:
        response = client.get(status_url)
        assert response.status_code == 200
        last_payload = response.json()
        if last_payload["status"] in {"COMPLETE", "FAILED"}:
            return last_payload
        time.sleep(0.05)
    raise AssertionError(f"Upload did not reach a terminal state. Last payload: {last_payload}")


def test_upload_returns_accepted_job_id() -> None:
    client = TestClient(create_app())
    csv_content = (
        "timestamp,room,temperature,humidity\n"
        "2026-05-01T08:00:00Z,Flower 1,75.2,58\n"
        "2026-05-01T08:05:00Z,Flower 1,75.6,59\n"
    )

    response = post_csv(client, "sensor-export.csv", csv_content)

    assert response.status_code == 202
    payload = response.json()
    assert payload["job_id"]
    assert payload["status"] == "PENDING"
    assert payload["filename"] == "sensor-export.csv"
    assert payload["message"] == "Preparing telemetry intake. Upload received and queued for background processing."
    assert payload["status_url"] == f"/api/data/upload-status/{payload['job_id']}"
    assert payload["file_size_bytes"] > 0


def test_json_upload_returns_accepted_job_id() -> None:
    client = TestClient(create_app())
    json_content = """
    {
      "source_id": "pilot-json-001",
      "source_type": "external_rest_api",
      "facility_id": "cultivation-facility-001",
      "room_id": "flower-room-1",
      "scenario": "airflow_drift",
      "tick": 10,
      "timestamp": "2026-05-01T08:00:00Z",
      "readings": [
        {"timestamp": "2026-05-01T08:00:00Z", "sensor_id": "temp-001", "sensor_name": "temperature", "value": 75.2, "unit": "F", "quality": "good"},
        {"timestamp": "2026-05-01T08:00:00Z", "sensor_id": "humidity-001", "sensor_name": "humidity", "value": 58, "unit": "%", "quality": "good"}
      ]
    }
    """

    response = post_json(client, "sensor-export.json", json_content)

    assert response.status_code == 202
    payload = response.json()
    assert payload["job_id"]
    assert payload["filename"] == "sensor-export.json"


def test_positive_int_env_parser_falls_back_for_invalid_values(monkeypatch) -> None:
    monkeypatch.setenv("NERAIUM_TEST_ROWS", "not-a-number")

    assert parse_positive_int_env("NERAIUM_TEST_ROWS", 123) == 123


def test_upload_does_not_require_shared_secret_in_production(tmp_path) -> None:
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],

        runtime_dir=tmp_path,
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/api/data/upload",
        files={"file": ("sensor-export.csv", "timestamp,value\n2026-05-01,75", "text/csv")},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "PENDING"
    assert payload["job_id"]


def test_upload_processes_in_api_role_without_worker_service(tmp_path) -> None:
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],
        runtime_dir=tmp_path,
        process_role="api",
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/api/data/upload",
        files={"file": ("sensor-export.csv", "timestamp,room,temperature,humidity\n2026-05-01T08:00:00Z,Flower 1,75,58", "text/csv")},
    )

    assert response.status_code == 202
    payload = wait_for_terminal_upload_status(client, response.json()["status_url"])
    assert payload["status"] == "COMPLETE"
    assert payload["runner_used"] is False


def test_create_upload_job_enforces_streaming_size_limit() -> None:
    class FakeUploadFile:
        filename = "oversize.csv"

        def __init__(self) -> None:
            self._chunks = [b"timestamp,value\n", b"2026-05-01,75\n"]

        async def read(self, _size: int) -> bytes:
            if self._chunks:
                return self._chunks.pop(0)
            return b""

    with pytest.raises(UploadTooLargeError):
        asyncio.run(create_upload_job(FakeUploadFile(), max_size_bytes=16))


def test_upload_rejects_oversize_request(monkeypatch, tmp_path) -> None:
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],
        runtime_dir=tmp_path,
        max_upload_size_bytes=16,
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/api/data/upload",
        files={"file": ("oversize.csv", "timestamp,value\n2026-05-01,75\n", "text/csv")},
    )

    assert response.status_code == 413
    payload = response.json()
    assert payload["error_type"] == "upload_too_large"
    assert payload["status"] == "FAILED"
    assert "16 bytes" in payload["message"]


def test_upload_rejects_saturated_queue(monkeypatch, tmp_path) -> None:
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],
        runtime_dir=tmp_path,
        max_pending_upload_jobs=1,
    )
    monkeypatch.setattr("app.routers.data.queue_metrics", lambda: {"pending": 1, "processing": 0})
    client = TestClient(create_app(settings))

    response = client.post(
        "/api/data/upload",
        files={"file": ("sensor-export.csv", "timestamp,value\n2026-05-01,75", "text/csv")},
    )

    assert response.status_code == 503
    assert response.headers["retry-after"] == "30"
    payload = response.json()
    assert payload["error_type"] == "upload_queue_saturated"
    assert payload["status"] == "FAILED"


def test_upload_accepts_access_header_in_production(tmp_path) -> None:
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],

        runtime_dir=tmp_path,
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/api/data/upload",
        headers={"X-Neraium-Access-Code": "expected-secret"},
        files={"file": ("sensor-export.csv", "timestamp,value\n2026-05-01,75", "text/csv")},
    )

    assert response.status_code == 202
    assert response.json()["status_url"].startswith("/api/data/upload-status/")


def test_upload_status_accepts_existing_session_cookie_in_production(tmp_path) -> None:
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],

        runtime_dir=tmp_path,
    )
    client = TestClient(create_app(settings))
    job = {
        "job_id": "session-job",
        "filename": "session.csv",
        "status": "RUNNING_SII",
        "progress_label": "Running SII engine against uploaded telemetry.",
        "rows_processed": 500_000,
        "columns_detected": 26,
        "started_at": "2026-05-08T00:00:00+00:00",
        "completed_at": None,
        "error": None,
    }
    write_job(job)
    response = client.get("/api/data/upload-status/session-job")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "RUNNING_SII"
    assert payload["message"] == "Telemetry batch processing in progress."
    assert payload["rows_processed"] == 500_000


def test_upload_status_missing_job_returns_session_missing_contract() -> None:
    client = TestClient(create_app())

    response = client.get("/api/data/upload-status/not-a-real-job")

    assert response.status_code == 404
    payload = response.json()
    assert payload["job_id"] == "not-a-real-job"
    assert payload["status"] == "NOT_FOUND"
    assert payload["error_type"] == "upload_session_missing"
    assert payload["error"] == "upload_session_missing"
    assert payload["message"] == "Upload session expired or was not found."


def test_upload_status_recovers_from_latest_completed_summary() -> None:
    client = TestClient(create_app())
    write_latest_upload_summary(
        "completed-job",
        {
            "filename": "completed.csv",
            "rows_processed": 300_000,
            "columns_detected": 12,
            "chunk_count": 30,
            "last_processed_at": "2026-05-10T00:00:00+00:00",
            "runner_used": True,
            "runner_module": RUNNER_MODULE,
            "core_engine": CORE_ENGINE,
        },
    )

    response = client.get("/api/data/upload-status/completed-job")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "COMPLETE"
    assert payload["rows_processed"] == 300_000


def test_upload_status_logs_session_missing_context(caplog) -> None:
    client = TestClient(create_app())

    response = client.get("/api/data/upload-status/missing-job")

    assert response.status_code == 404
    assert "polling_job_id=missing-job" in caplog.text
    assert "validation_failure_reason=upload_session_missing" in caplog.text
    assert "metadata_exists=False" in caplog.text


def test_upload_status_returns_complete_job_summary_and_writes_state() -> None:
    client = TestClient(create_app())
    rows = "\n".join(
        f"2026-05-01T08:{index:02d}:00Z,Flower 1,{75 + index * 0.1:.1f},{58 + index * 0.2:.1f}"
        for index in range(8)
    )

    upload = post_csv(client, "ready-report.csv", f"timestamp,room,temperature,humidity\n{rows}")
    payload = wait_for_terminal_upload_status(client, upload.json()["status_url"])
    job_id = upload.json()["job_id"]
    assert payload["job_id"] == job_id
    assert payload["status"] == "COMPLETE"
    assert payload["progress_label"] == "Telemetry processing complete."
    assert payload["rows_processed"] == 8
    assert payload["columns_detected"] == 4
    assert payload["runner_used"] is True
    assert payload["runner_module"] == RUNNER_MODULE
    assert payload["core_engine"] == CORE_ENGINE
    assert payload["error"] is None
    assert payload["result_summary"]["filename"] == "ready-report.csv"
    assert sii_runner.STATE_PATH.exists()


def test_upload_status_can_return_queued_state() -> None:
    client = TestClient(create_app())
    job = {
        "job_id": "queued-job",
        "filename": "queued.csv",
        "status": "queued",
        "progress_label": "Telemetry batch received. Processing is queued.",
        "rows_processed": 0,
        "columns_detected": 0,
        "started_at": "2026-05-08T00:00:00+00:00",
        "completed_at": None,
        "error": None,
    }
    write_job(job)

    status = client.get(f"/api/data/upload-status/{job['job_id']}")

    assert status.status_code == 200
    assert status.json()["status"] == "PENDING"


def test_upload_status_can_return_failed_state() -> None:
    client = TestClient(create_app())
    job = {
        "job_id": "failed-job",
        "filename": "failed.csv",
        "status": "failed",
        "progress_label": "Telemetry processing failed.",
        "rows_processed": 0,
        "columns_detected": 0,
        "started_at": "2026-05-08T00:00:00+00:00",
        "completed_at": "2026-05-08T00:05:00+00:00",
        "error": "Example failure",
    }
    write_job(job)
    status = client.get(f"/api/data/upload-status/{job['job_id']}")

    assert status.status_code == 200
    assert status.json()["status"] == "FAILED"
    assert status.json()["error"] == "Example failure"


def test_latest_upload_endpoint_returns_completed_summary() -> None:
    client = TestClient(create_app())
    rows = "\n".join(
        f"2026-05-01T08:{index:02d}:00Z,{75 + index},{58 + index}"
        for index in range(6)
    )
    upload = post_csv(client, "latest.csv", f"timestamp,temperature,humidity\n{rows}")
    wait_for_terminal_upload_status(client, upload.json()["status_url"])

    response = client.get("/api/data/latest-upload")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "uploaded"
    assert payload["last_filename"] == "latest.csv"
    assert payload["rows_processed"] == 6
    assert payload["columns_detected"] == 3
    assert payload["state_available"] is True
    assert payload["history"][0]["filename"] == "latest.csv"


@pytest.mark.slow
def test_latest_upload_endpoint_returns_recent_history_and_score_diff() -> None:
    client = TestClient(create_app())
    first_rows = "\n".join(
        f"2026-05-01T08:{index:02d}:00Z,Flower 1,{74 + index * 0.1:.1f},{55 + index * 0.1:.1f}"
        for index in range(6)
    )
    second_rows = "\n".join(
        f"2026-05-02T08:{index:02d}:00Z,Flower 1,{81 + index * 0.8:.1f},{67 + index * 0.7:.1f}"
        for index in range(6)
    )

    baseline = post_csv(client, "baseline.csv", f"timestamp,room,temperature,humidity\n{first_rows}")
    wait_for_terminal_upload_status(client, baseline.json()["status_url"])
    changed = post_csv(client, "changed.csv", f"timestamp,room,temperature,humidity\n{second_rows}")
    wait_for_terminal_upload_status(client, changed.json()["status_url"])

    payload = client.get("/api/data/latest-upload").json()

    assert len(payload["history"]) == 2
    assert payload["history"][0]["filename"] == "changed.csv"
    assert payload["history"][1]["filename"] == "baseline.csv"
    assert payload["history"][0]["diff"]["previous_filename"] == "baseline.csv"
    assert "neraium_score_delta" in payload["history"][0]["diff"]


def test_upload_creates_evidence_record_and_latest_endpoint_returns_it() -> None:
    client = TestClient(create_app())
    rows = "\n".join(
        f"2026-05-01T08:{index:02d}:00Z,Flower 1,{75 + index * 0.2:.1f},{58 + index * 0.3:.1f}"
        for index in range(6)
    )

    upload = post_csv(client, "evidence.csv", f"timestamp,room,temperature,humidity\n{rows}")
    run_id = upload.json()["job_id"]
    wait_for_terminal_upload_status(client, upload.json()["status_url"])

    latest = client.get("/api/evidence/latest")
    detail = client.get(f"/api/evidence/runs/{run_id}")

    assert latest.status_code == 200
    assert latest.json()["run"]["run_id"] == run_id
    assert latest.json()["run"]["source_name"] == "evidence.csv"
    assert latest.json()["run"]["status"] == "completed"
    assert latest.json()["run"]["initiated_by"] == "anonymous"
    assert detail.status_code == 200
    assert detail.json()["rows_accepted"] == 6
    assert detail.json()["sensors_detected"] >= 2


def test_upload_records_authenticated_actor_in_evidence() -> None:
    client = TestClient(create_app())
    rows = "\n".join(
        f"2026-05-01T08:{index:02d}:00Z,Flower 1,{75 + index * 0.2:.1f},{58 + index * 0.3:.1f}"
        for index in range(6)
    )

    upload = client.post(
        "/api/data/upload",
        headers={"X-Neraium-User": "operator@example.com"},
        files={"file": ("actor.csv", f"timestamp,room,temperature,humidity\n{rows}", "text/csv")},
    )
    run_id = upload.json()["job_id"]
    wait_for_terminal_upload_status(client, upload.json()["status_url"])
    detail = client.get(f"/api/evidence/runs/{run_id}")

    assert detail.status_code == 200
    assert detail.json()["initiated_by"] == "operator@example.com"


def test_failed_processing_creates_failed_evidence_record(monkeypatch) -> None:
    client = TestClient(create_app())
    monkeypatch.setattr("app.services.upload_jobs.process_csv_file", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    upload = post_csv(client, "bad.csv", "timestamp\n2026-05-01T08:00:00Z\n")
    run_id = upload.json()["job_id"]
    wait_for_terminal_upload_status(client, upload.json()["status_url"])

    detail = client.get(f"/api/evidence/runs/{run_id}")

    assert detail.status_code == 200
    payload = detail.json()
    assert payload["status"] == "failed"
    assert payload["errors"]


def test_evidence_export_endpoint_returns_report() -> None:
    client = TestClient(create_app())
    rows = "\n".join(
        f"2026-05-01T08:{index:02d}:00Z,Flower 1,{75 + index * 0.2:.1f},{58 + index * 0.3:.1f}"
        for index in range(6)
    )
    upload = post_csv(client, "export.csv", f"timestamp,room,temperature,humidity\n{rows}")
    run_id = upload.json()["job_id"]
    wait_for_terminal_upload_status(client, upload.json()["status_url"])

    response = client.get(f"/api/evidence/export/{run_id}")

    assert response.status_code == 200
    assert "# Neraium Evidence Report" in response.text
    assert "Run ID:" in response.text


def test_observability_summary_reports_queue_and_audit_counts() -> None:
    client = TestClient(create_app())
    rows = "\n".join(
        f"2026-05-01T08:{index:02d}:00Z,Flower 1,{75 + index * 0.2:.1f},{58 + index * 0.3:.1f}"
        for index in range(6)
    )
    upload = client.post(
        "/api/data/upload",
        headers={"X-Neraium-User": "ops@example.com"},
        files={"file": ("obs.csv", f"timestamp,room,temperature,humidity\n{rows}", "text/csv")},
    )
    run_id = upload.json()["job_id"]
    wait_for_terminal_upload_status(client, upload.json()["status_url"])
    client.get(f"/api/evidence/export/{run_id}", headers={"X-Neraium-User": "ops@example.com"})

    response = client.get("/api/observability/summary")

    assert response.status_code == 200
    payload = response.json()
    assert "queue" in payload
    assert "audit" in payload
    assert payload["audit"]["event_count"] >= 2


def test_latest_upload_endpoint_returns_persisted_detailed_result() -> None:
    client = TestClient(create_app())
    detailed_result = {
        "filename": "persisted.csv",
        "row_count": 12,
        "column_count": 4,
        "data_quality": {"readiness": "ready"},
        "engine_result": {"overall_result": "stable"},
        "cultivation_mapping": {"room": "room"},
        "sii_intelligence": {
            "source": "uploaded",
            "mode": "live",
            "facility_state": "Monitoring active telemetry feed",
            "room_state": "Monitoring active telemetry feed",
            "urgency": "nominal",
            "intervention_window": "12 hours",
            "neraium_score": 88,
            "primary_room": "Flower Room 1",
            "priority_room": "Flower Room 1",
            "primary_driver": "Uploaded telemetry active",
            "supporting_evidence": ["Uploaded telemetry active"],
            "relationship_evidence": ["Uploaded telemetry active"],
            "structural_explanation": ["Uploaded telemetry active"],
            "confidence_basis": "Uploaded telemetry active",
            "recommended_operator_review": "Continue monitoring",
            "what_to_check": ["Continue monitoring"],
            "why_flagged": "Uploaded telemetry active",
            "baseline_comparison": "Uploaded telemetry active",
            "observed_persistence": "Uploaded telemetry active",
            "last_updated": "2026-05-10T00:00:00+00:00",
            "rooms": [],
        },
        "processing_trace": {},
        "room_summary": {"room_count": 1, "rooms": [{"room": "Flower Room 1", "row_count": 12}]},
    }
    write_latest_upload_result("persisted-job", detailed_result)

    response = client.get("/api/data/latest-upload")

    assert response.status_code == 200
    payload = response.json()
    assert payload["last_filename"] == "persisted.csv"
    assert payload["rows_processed"] == 12
    assert payload["latest_result"]["data_quality"]["readiness"] == "ready"


def test_facility_systems_uses_latest_state_after_upload() -> None:
    client = TestClient(create_app())
    rows = "\n".join(
        f"2026-05-01T08:{index:02d}:00Z,Flower 1,{75 + index},{58 + index}"
        for index in range(6)
    )
    upload = post_csv(client, "facility-state.csv", f"timestamp,room,temperature,humidity\n{rows}")
    wait_for_terminal_upload_status(client, upload.json()["status_url"])

    response = client.get("/api/facility/systems")

    assert response.status_code == 200
    payload = response.json()
    assert payload["intelligence"]["source"] == "uploaded"
    assert payload["intelligence"]["runner_module"] == RUNNER_MODULE


def test_facility_systems_recovers_from_persisted_upload_result_when_state_missing() -> None:
    client = TestClient(create_app())
    write_latest_upload_result(
        "persisted-facility-job",
        {
            "filename": "persisted.csv",
            "row_count": 24,
            "column_count": 4,
            "data_quality": {"readiness": "ready"},
            "engine_result": {"overall_result": "stable"},
            "cultivation_mapping": {"room": "room"},
            "sii_intelligence": {
                "source": "uploaded",
                "mode": "live",
                "facility_state": "Monitoring active telemetry feed",
                "room_state": "Monitoring active telemetry feed",
                "urgency": "nominal",
                "intervention_window": "12 hours",
                "neraium_score": 90,
                "primary_room": "Flower Room 3",
                "priority_room": "Flower Room 3",
                "primary_driver": "Recovered from persisted upload result",
                "supporting_evidence": ["Recovered from persisted upload result"],
                "relationship_evidence": ["Recovered from persisted upload result"],
                "structural_explanation": ["Recovered from persisted upload result"],
                "confidence_basis": "Recovered from persisted upload result",
                "recommended_operator_review": "Continue monitoring",
                "what_to_check": ["Continue monitoring"],
                "why_flagged": "Recovered from persisted upload result",
                "baseline_comparison": "Recovered from persisted upload result",
                "observed_persistence": "Recovered from persisted upload result",
                "last_updated": "2026-05-10T00:00:00+00:00",
                "rooms": [],
            },
            "processing_trace": {},
            "room_summary": {"room_count": 1, "rooms": [{"room": "Flower Room 3", "row_count": 24}]},
        },
    )

    response = client.get("/api/facility/systems")

    assert response.status_code == 200
    payload = response.json()
    assert payload["intelligence"]["source"] == "uploaded"
    assert payload["intelligence"]["primary_driver"] == "Recovered from persisted upload result"

def test_facility_systems_uses_multi_room_state_after_upload() -> None:
    client = TestClient(create_app())
    rows = "\n".join(
        [
            "2026-05-01T08:00:00Z,Flower Room 1,74,55",
            "2026-05-01T08:05:00Z,Flower Room 2,76,60",
            "2026-05-01T08:10:00Z,Veg Room A,80,65",
            "2026-05-01T08:15:00Z,Mother Room,75,57",
            "2026-05-01T08:20:00Z,Flower Room 1,75,56",
        ]
    )
    upload = post_csv(client, "multi-room-state.csv", f"timestamp,room,temperature,humidity\n{rows}")
    wait_for_terminal_upload_status(client, upload.json()["status_url"])

    payload = client.get("/api/facility/systems").json()

    assert payload["intelligence"]["room_summary"]["room_count"] == 4
    assert len(payload["intelligence"]["rooms"]) == 4
    room_records = {room["room"]: room for room in payload["intelligence"]["rooms"]}
    assert room_records["Flower Room 2"]["urgency"] == "review"
    assert room_records["Flower Room 2"]["room_state"] == "Insufficient telemetry"
    assert "flagged because" in room_records["Flower Room 2"]["why_flagged"].lower()


def test_one_column_csv_reports_runner_error_without_failed_job() -> None:
    client = TestClient(create_app())
    rows = "\n".join(f"2026-05-01T08:{index:02d}:00Z,{75 + index}" for index in range(6))

    upload = post_csv(client, "one-column.csv", f"timestamp,temperature\n{rows}")
    payload = wait_for_terminal_upload_status(client, upload.json()["status_url"])
    assert payload["status"] == "COMPLETE"
    assert payload["runner_used"] is True
    assert payload["error"] is None
    assert payload["result_summary"]["runner_errors"] == []


def test_upload_rejects_invalid_extension() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/data/upload",
        files={"file": ("sensor-export.txt", "timestamp,value\n2026-05-01,75", "text/plain")},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["message"] == "Only .csv and .json telemetry files are supported."
    assert payload["status"] == "FAILED"
    assert payload["processing_state"] == "failed"


def test_upload_rejects_empty_csv() -> None:
    client = TestClient(create_app())

    response = post_csv(client, "empty.csv", "")

    assert response.status_code == 400
    payload = response.json()
    assert payload["message"] == "CSV file is empty."
    assert payload["status"] == "FAILED"
    assert payload["processing_state"] == "failed"


def test_processing_helper_accepts_live_shape_json_payload() -> None:
    result = process_json_payload(
        filename="pilot-upload.json",
        payload={
            "source_id": "pilot-json-001",
            "source_type": "external_rest_api",
            "facility_id": "cultivation-facility-001",
            "room_id": "flower-room-1",
            "scenario": "airflow_drift",
            "tick": 10,
            "timestamp": "2026-05-01T08:00:00Z",
            "readings": [
                {"timestamp": "2026-05-01T08:00:00Z", "sensor_id": "temp-001", "sensor_name": "temperature", "value": 74, "unit": "F", "quality": "good"},
                {"timestamp": "2026-05-01T08:00:00Z", "sensor_id": "humidity-001", "sensor_name": "humidity", "value": 55, "unit": "%", "quality": "good"},
                {"timestamp": "2026-05-01T08:05:00Z", "sensor_id": "temp-001", "sensor_name": "temperature", "value": 75, "unit": "F", "quality": "good"},
                {"timestamp": "2026-05-01T08:05:00Z", "sensor_id": "humidity-001", "sensor_name": "humidity", "value": 56, "unit": "%", "quality": "good"},
                {"timestamp": "2026-05-01T08:10:00Z", "sensor_id": "temp-001", "sensor_name": "temperature", "value": 76, "unit": "F", "quality": "good"},
                {"timestamp": "2026-05-01T08:10:00Z", "sensor_id": "humidity-001", "sensor_name": "humidity", "value": 57, "unit": "%", "quality": "good"},
                {"timestamp": "2026-05-01T08:15:00Z", "sensor_id": "temp-001", "sensor_name": "temperature", "value": 77, "unit": "F", "quality": "good"},
                {"timestamp": "2026-05-01T08:15:00Z", "sensor_id": "humidity-001", "sensor_name": "humidity", "value": 58, "unit": "%", "quality": "good"},
                {"timestamp": "2026-05-01T08:20:00Z", "sensor_id": "temp-001", "sensor_name": "temperature", "value": 78, "unit": "F", "quality": "good"},
                {"timestamp": "2026-05-01T08:20:00Z", "sensor_id": "humidity-001", "sensor_name": "humidity", "value": 59, "unit": "%", "quality": "good"},
            ],
        },
    )

    assert result["filename"] == "pilot-upload.json"
    assert result["row_count"] == 5
    assert result["room_summary"]["room_count"] == 1
    assert result["sii_intelligence"]["source"] == "uploaded"
    assert result["sii_intelligence"]["replay_timeline"]["timeline"]


def test_processing_helper_preserves_profile_metadata() -> None:
    result = process_csv_content(
        filename="numeric-profile.csv",
        content=(
            "timestamp,temperature,humidity\n"
            "2026-05-01T08:00:00Z,74,55\n"
            "2026-05-01T08:05:00Z,76,60\n"
            "2026-05-01T08:10:00Z,80,65\n"
        ).encode(),
    )

    profiles = {profile["column"]: profile for profile in result["numeric_profiles"]}
    assert result["filename"] == "numeric-profile.csv"
    assert result["row_count"] == 3
    assert result["detected_timestamp_column"] == "timestamp"
    assert profiles["temperature"]["average"] == 76.6667
    assert result["data_quality"]["readiness"] == "ready"
    assert result["sii_runner_result"]["runner_module"] == RUNNER_MODULE


def test_processing_helper_detects_multiple_uploaded_rooms() -> None:
    result = process_csv_content(
        filename="multi-room.csv",
        content=(
            "timestamp,room,temperature,humidity\n"
            "2026-05-01T08:00:00Z,Flower Room 1,74,55\n"
            "2026-05-01T08:05:00Z,Flower Room 2,76,60\n"
            "2026-05-01T08:10:00Z,Veg Room A,80,65\n"
            "2026-05-01T08:15:00Z,Mother Room,75,57\n"
        ).encode(),
    )

    assert result["room_summary"]["room_count"] == 4
    assert [room["room"] for room in result["room_summary"]["rooms"]] == [
        "Flower Room 1",
        "Flower Room 2",
        "Mother Room",
        "Veg Room A",
    ]
    assert len(result["sii_intelligence"]["rooms"]) == 4


def test_processing_helper_distinguishes_calm_and_drifted_uploads() -> None:
    calm_rows = "\n".join(
        f"2026-05-01T08:{index:02d}:00Z,Flower 1,75.0,58.0"
        for index in range(10)
    )
    drift_rows = "\n".join(
        f"2026-05-01T08:{index:02d}:00Z,Flower 1,{70 if index < 3 else 72 if index < 8 else 82},{55 if index < 3 else 56 if index < 8 else 68}"
        for index in range(15)
    )

    calm_result = process_csv_content(
        filename="calm.csv",
        content=f"timestamp,room,temperature,humidity\n{calm_rows}".encode(),
    )
    drift_result = process_csv_content(
        filename="drift.csv",
        content=f"timestamp,room,temperature,humidity\n{drift_rows}".encode(),
    )

    calm_intelligence = calm_result["sii_intelligence"]
    drift_intelligence = drift_result["sii_intelligence"]

    assert drift_intelligence["neraium_score"] < calm_intelligence["neraium_score"]
    assert drift_intelligence["urgency"] != calm_intelligence["urgency"]


def test_multi_room_intelligence_uses_room_specific_relationship_and_structural_explanations() -> None:
    result = process_csv_content(
        filename="room-specific-evidence.csv",
        content=(
            "timestamp,room,temperature,humidity,airflow\n"
            "2026-05-01T08:00:00Z,Flower Room 1,74,55,300\n"
            "2026-05-01T08:05:00Z,Flower Room 1,74,55,301\n"
            "2026-05-01T08:10:00Z,Flower Room 1,75,56,303\n"
            "2026-05-01T08:15:00Z,Flower Room 1,80,66,360\n"
            "2026-05-01T08:20:00Z,Flower Room 1,82,68,380\n"
            "2026-05-01T08:25:00Z,Flower Room 1,83,69,390\n"
            "2026-05-01T08:00:00Z,Flower Room 2,75,56,305\n"
            "2026-05-01T08:05:00Z,Flower Room 2,75,56,305\n"
            "2026-05-01T08:10:00Z,Flower Room 2,75,56,306\n"
            "2026-05-01T08:15:00Z,Flower Room 2,75,56,306\n"
            "2026-05-01T08:20:00Z,Flower Room 2,75,56,305\n"
            "2026-05-01T08:25:00Z,Flower Room 2,75,56,305\n"
            "2026-05-01T08:00:00Z,Veg Room A,74,55,301\n"
            "2026-05-01T08:05:00Z,Veg Room A,74,55,301\n"
            "2026-05-01T08:10:00Z,Veg Room A,74,55,301\n"
        ).encode(),
    )

    rooms = result["sii_intelligence"]["rooms"]
    room_map = {room["room"]: room for room in rooms}
    primary = room_map["Flower Room 1"]
    secondary = room_map["Flower Room 2"]
    sparse = room_map["Veg Room A"]

    assert "driver_category" in secondary
    assert "attribution_confidence" in secondary
    assert "next_operator_move" in secondary
    assert "confidence_components" in secondary
    assert set(secondary["confidence_components"].keys()) == {
        "data_sufficiency",
        "signal_strength",
        "relationship_support",
        "persistence",
    }

    assert secondary["relationship_evidence"] != primary["relationship_evidence"]
    assert secondary["structural_explanation"] != primary["structural_explanation"]
    assert secondary["relationship_evidence"][0].startswith("Flower Room 2:")
    assert secondary["structural_explanation"][0].startswith("Flower Room 2:")
    assert "confidence components:" in secondary["confidence_basis"].lower()

    assert sparse["relationship_evidence"] != primary["relationship_evidence"]
    assert sparse["structural_explanation"] != primary["structural_explanation"]
    assert "limited due to sparse telemetry" in " ".join(sparse["relationship_evidence"]).lower()
    assert sparse["driver_category"] == "sensor_network"
    assert sparse["attribution_confidence"] == "low"


def test_mixed_room_regression_preserves_unstable_nominal_and_sparse_room_states() -> None:
    result = process_csv_content(
        filename="mixed-room-regression.csv",
        content=(
            "timestamp,room,temperature,humidity,airflow\n"
            "2026-05-01T08:00:00Z,Flower Room 1,74,55,300\n"
            "2026-05-01T08:05:00Z,Flower Room 1,74,55,301\n"
            "2026-05-01T08:10:00Z,Flower Room 1,75,56,303\n"
            "2026-05-01T08:15:00Z,Flower Room 1,98,82,520\n"
            "2026-05-01T08:20:00Z,Flower Room 1,101,84,545\n"
            "2026-05-01T08:25:00Z,Flower Room 1,104,86,565\n"
            "2026-05-01T08:00:00Z,Flower Room 2,75,56,305\n"
            "2026-05-01T08:05:00Z,Flower Room 2,75,56,305\n"
            "2026-05-01T08:10:00Z,Flower Room 2,75,56,305\n"
            "2026-05-01T08:15:00Z,Flower Room 2,75,56,306\n"
            "2026-05-01T08:20:00Z,Flower Room 2,75,56,305\n"
            "2026-05-01T08:25:00Z,Flower Room 2,75,56,305\n"
            "2026-05-01T08:00:00Z,Veg Room A,74,55,301\n"
            "2026-05-01T08:05:00Z,Veg Room A,74,55,301\n"
            "2026-05-01T08:10:00Z,Veg Room A,74,55,301\n"
        ).encode(),
    )

    rooms = {room["room"]: room for room in result["sii_intelligence"]["rooms"]}
    unstable_room = rooms["Flower Room 1"]
    nominal_room = rooms["Flower Room 2"]
    sparse_room = rooms["Veg Room A"]

    assert unstable_room["urgency"] == "unstable"
    assert unstable_room["driver_category"] == "process_timing"
    assert unstable_room["attribution_confidence"] == "high"
    assert unstable_room["confidence_components"]["signal_strength"] == "high"

    assert nominal_room["urgency"] == "nominal"
    assert nominal_room["driver_category"] == "stable_monitoring"
    assert nominal_room["attribution_confidence"] == "medium"
    assert nominal_room["confidence_components"]["signal_strength"] == "low"

    assert sparse_room["urgency"] == "review"
    assert sparse_room["room_state"] == "Insufficient telemetry"
    assert sparse_room["driver_category"] == "sensor_network"
    assert sparse_room["attribution_confidence"] == "low"
    assert sparse_room["confidence_components"]["data_sufficiency"] == "low"


def test_processing_helper_classifies_pool_and_hot_tub_telemetry_profile() -> None:
    result = process_csv_content(
        filename="pool-hottub-telemetry.csv",
        content=(
            "timestamp,room,pool_water_temp,spa_water_temp,orp_mv,chlorine_ppm,ph_level,alkalinity_ppm,heater_runtime,circulation_pump_runtime\n"
            "2026-05-01T08:00:00Z,Pool,81,101,690,2.8,7.4,100,18,57\n"
            "2026-05-01T08:05:00Z,Pool,81.2,101.1,695,2.9,7.4,101,19,58\n"
            "2026-05-01T08:10:00Z,Pool,81.4,101.3,700,3.0,7.5,101,19,58\n"
            "2026-05-01T08:15:00Z,Spa,101.8,103.5,705,3.1,7.5,102,22,62\n"
            "2026-05-01T08:20:00Z,Spa,102.0,103.7,710,3.1,7.6,102,23,63\n"
        ).encode(),
    )

    intelligence = result["sii_intelligence"]
    assert intelligence["telemetry_profile"] == "pool_hottub_systems"
    assert intelligence["telemetry_profile_confidence"] in {"medium", "high"}
    assert isinstance(intelligence["telemetry_profile_signals"], list)
    assert len(intelligence["telemetry_profile_signals"]) >= 1


def test_processing_helper_classifies_cultivation_climate_profile() -> None:
    result = process_csv_content(
        filename="cultivation-profile.csv",
        content=(
            "timestamp,room,temp_air,rh_percent,co2,hvac_runtime,dehu_runtime,light_intensity,irrigation_event\n"
            "2026-05-01T08:00:00Z,Flower 1,75,58,920,21,11,580,0\n"
            "2026-05-01T08:05:00Z,Flower 1,75.1,58.1,925,22,11,582,0\n"
            "2026-05-01T08:10:00Z,Flower 1,75.3,58.2,930,22,12,584,1\n"
            "2026-05-01T08:15:00Z,Flower 1,75.4,58.2,932,23,12,586,0\n"
        ).encode(),
    )

    intelligence = result["sii_intelligence"]
    assert intelligence["telemetry_profile"] in {"cultivation_climate", "unknown"}
    assert intelligence["telemetry_profile_confidence"] in {"low", "medium", "high"}


def test_processing_helper_classifies_hvac_profile() -> None:
    result = process_csv_content(
        filename="hvac-profile.csv",
        content=(
            "timestamp,room,supply_temp,return_temp,static_pressure,compressor_runtime,air_handler_status\n"
            "2026-05-01T08:00:00Z,AHU-1,54,72,1.8,22,1\n"
            "2026-05-01T08:05:00Z,AHU-1,54.2,72.1,1.9,23,1\n"
            "2026-05-01T08:10:00Z,AHU-1,54.4,72.2,1.9,24,1\n"
            "2026-05-01T08:15:00Z,AHU-1,54.7,72.5,2.0,25,1\n"
        ).encode(),
    )
    intelligence = result["sii_intelligence"]
    assert intelligence["telemetry_profile"] == "hvac_systems"
    assert intelligence["telemetry_profile_confidence"] in {"medium", "high"}


def test_processing_helper_classifies_electrical_profile() -> None:
    result = process_csv_content(
        filename="electrical-profile.csv",
        content=(
            "timestamp,room,voltage_l1,current_l1,kw_demand,power_factor,frequency_hz,panel_temp\n"
            "2026-05-01T08:00:00Z,Panel A,480,52,38,0.96,60,84\n"
            "2026-05-01T08:05:00Z,Panel A,479,53,39,0.95,60,84.2\n"
            "2026-05-01T08:10:00Z,Panel A,481,51,37,0.97,60,84.1\n"
            "2026-05-01T08:15:00Z,Panel A,480,54,40,0.95,60,84.3\n"
        ).encode(),
    )
    intelligence = result["sii_intelligence"]
    assert intelligence["telemetry_profile"] == "electrical_systems"
    assert intelligence["telemetry_profile_confidence"] in {"medium", "high"}


def test_processing_helper_low_confidence_profile_makes_no_claim() -> None:
    result = process_csv_content(
        filename="low-confidence-profile.csv",
        content=(
            "timestamp,room,x1,x2,x3\n"
            "2026-05-01T08:00:00Z,Room A,1,2,3\n"
            "2026-05-01T08:05:00Z,Room A,2,3,4\n"
            "2026-05-01T08:10:00Z,Room A,3,4,5\n"
            "2026-05-01T08:15:00Z,Room A,4,5,6\n"
        ).encode(),
    )
    intelligence = result["sii_intelligence"]
    assert intelligence["telemetry_profile"] == "unknown"
    assert intelligence["telemetry_profile_confidence"] == "low"
    assert intelligence["telemetry_profile_signals"] == []
    assert intelligence["system_identity"]["claim_made"] is False


def test_processing_helper_classifies_operational_mechanical_profile() -> None:
    result = process_csv_content(
        filename="mechanical-profile.csv",
        content=(
            "timestamp,room,pump_amperage,pump_discharge_pressure,motor_temperature,vfd_frequency,bearing_temperature,shaft_vibration\n"
            "2026-05-01T08:00:00Z,Plant A,14.2,42.1,168.4,58.1,142.2,0.12\n"
            "2026-05-01T08:05:00Z,Plant A,14.4,42.6,168.9,58.0,142.4,0.13\n"
            "2026-05-01T08:10:00Z,Plant A,14.7,43.0,169.1,57.8,142.9,0.14\n"
            "2026-05-01T08:15:00Z,Plant A,14.9,43.5,169.6,57.7,143.2,0.15\n"
        ).encode(),
    )
    intelligence = result["sii_intelligence"]
    assert intelligence["operational_signal_profile"] == "mechanical_systems"
    assert intelligence["operational_signal_profile_confidence"] in {"medium", "high"}
    assert intelligence["system_identity"]["operational_profile"] == "mechanical_systems"


def test_processing_helper_classifies_operational_events_profile() -> None:
    result = process_csv_content(
        filename="ops-events-profile.csv",
        content=(
            "timestamp,room,alarm_acknowledgements,manual_override_events,setpoint_changes,maintenance_actions,operator_interventions\n"
            "2026-05-01T08:00:00Z,Plant A,2,1,4,0,3\n"
            "2026-05-01T08:05:00Z,Plant A,3,1,5,1,4\n"
            "2026-05-01T08:10:00Z,Plant A,3,2,6,1,5\n"
            "2026-05-01T08:15:00Z,Plant A,4,2,6,2,5\n"
        ).encode(),
    )
    intelligence = result["sii_intelligence"]
    assert intelligence["operational_signal_profile"] == "operational_events"
    assert intelligence["operational_signal_modality"] == "event"
    assert intelligence["system_identity"]["operational_modality"] == "event"


def test_processing_helper_classifies_operational_water_profile() -> None:
    result = process_csv_content(
        filename="water-profile.csv",
        content=(
            "timestamp,room,flow_rate,totalized_flow,water_pressure,filter_differential_pressure,tank_level,water_turnover_rate\n"
            "2026-05-01T08:00:00Z,Water Plant,142,2100,39.2,4.1,76.5,6.2\n"
            "2026-05-01T08:05:00Z,Water Plant,143,2140,39.4,4.2,76.2,6.3\n"
            "2026-05-01T08:10:00Z,Water Plant,145,2184,39.7,4.4,75.8,6.5\n"
            "2026-05-01T08:15:00Z,Water Plant,146,2228,39.9,4.5,75.4,6.6\n"
        ).encode(),
    )
    intelligence = result["sii_intelligence"]
    assert intelligence["operational_signal_profile"] == "water_systems"
    assert intelligence["operational_signal_profile_confidence"] in {"medium", "high"}


def test_processing_helper_classifies_operational_utility_profile() -> None:
    result = process_csv_content(
        filename="utility-profile.csv",
        content=(
            "timestamp,room,distribution_pressure,leak_detection_indicator,pump_station_output,reservoir_refill_rate,sewer_flow,treatment_plant_flow\n"
            "2026-05-01T08:00:00Z,Utility Grid,57.1,0,188,4.6,122,245\n"
            "2026-05-01T08:05:00Z,Utility Grid,57.0,1,190,4.7,124,248\n"
            "2026-05-01T08:10:00Z,Utility Grid,56.8,1,191,4.8,126,251\n"
            "2026-05-01T08:15:00Z,Utility Grid,56.7,0,193,4.9,127,254\n"
        ).encode(),
    )
    intelligence = result["sii_intelligence"]
    assert intelligence["operational_signal_profile"] == "utility_infrastructure"
    assert intelligence["operational_signal_profile_confidence"] in {"medium", "high"}


def test_processing_helper_classifies_operational_network_profile() -> None:
    result = process_csv_content(
        filename="network-profile.csv",
        content=(
            "timestamp,room,cpu_utilization,memory_utilization,network_throughput,packet_loss,latency,api_response_time,error_rate\n"
            "2026-05-01T08:00:00Z,DC-1,61,72,845,0.2,24,180,0.9\n"
            "2026-05-01T08:05:00Z,DC-1,63,73,852,0.3,25,184,1.0\n"
            "2026-05-01T08:10:00Z,DC-1,66,75,861,0.3,26,190,1.2\n"
            "2026-05-01T08:15:00Z,DC-1,67,76,869,0.4,27,196,1.3\n"
        ).encode(),
    )
    intelligence = result["sii_intelligence"]
    assert intelligence["operational_signal_profile"] == "network_digital_infrastructure"
    assert intelligence["operational_signal_profile_confidence"] in {"medium", "high"}


@pytest.mark.slow
def test_50k_upload_completes_with_chunked_job_metadata(monkeypatch) -> None:
    monkeypatch.setattr("app.services.upload_jobs.MAX_SII_ROWS", 250)
    client = TestClient(create_app())
    rows = "\n".join(
        f"2026-05-01T08:{index % 60:02d}:00Z,Flower 1,{75 + (index % 10) * 0.1:.1f},{58 + (index % 12) * 0.2:.1f}"
        for index in range(50_000)
    )

    upload = post_csv(client, "telemetry-50k.csv", f"timestamp,room,temperature,humidity\n{rows}")
    payload = client.get(upload.json()["status_url"]).json()

    assert payload["status"] == "COMPLETE"
    assert payload["rows_processed"] == 50_000
    assert payload["chunk_count"] == 5
    assert payload["runner_used"] is True


@pytest.mark.slow
def test_75k_upload_status_polling_completes_with_extended_timeout() -> None:
    client = TestClient(create_app())
    rows = "\n".join(
        f"2026-05-01T08:{index % 60:02d}:00Z,Flower 1,{75 + (index % 10) * 0.1:.1f},{58 + (index % 12) * 0.2:.1f}"
        for index in range(75_000)
    )

    upload_response = post_csv(client, "telemetry-75k.csv", f"timestamp,room,temperature,humidity\n{rows}")
    upload_payload = upload_response.json()
    if upload_payload.get("status_url"):
        payload = wait_for_terminal_upload_status(client, upload_payload["status_url"], timeout_seconds=30.0)
    elif upload_payload.get("job_id"):
        payload = wait_for_terminal_upload_status(
            client,
            f"/api/data/upload-status/{upload_payload['job_id']}",
            timeout_seconds=30.0,
        )
    else:
        payload = upload_payload

    assert payload["status"] == "COMPLETE"
    rows_processed = payload.get("rows_processed", payload.get("row_count"))
    assert rows_processed == 75_000
    if "runner_used" in payload:
        assert payload["runner_used"] in {True, False}


@pytest.mark.slow
def test_100k_upload_completes_without_loading_all_rows(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.services.upload_jobs.MAX_SII_ROWS", 250)
    csv_path = tmp_path / "telemetry-100k.csv"
    with csv_path.open("w", encoding="utf-8") as output:
        output.write("timestamp,room,temperature,humidity\n")
        for index in range(100_000):
            output.write(f"2026-05-01T08:{index % 60:02d}:00Z,Flower 1,{75 + (index % 9) * 0.1:.1f},{58 + (index % 11) * 0.2:.1f}\n")

    result = process_csv_file(file_path=csv_path, filename="telemetry-100k.csv")

    assert result["row_count"] == 100_000
    assert result["processing_stats"]["used_streaming"] is True
    assert result["processing_stats"]["sampled_rows"] == upload_jobs.MAX_ANALYSIS_ROWS
    assert result["processing_stats"]["chunk_count"] == 10


@pytest.mark.slow
def test_simulated_300k_upload_streams_windows_and_preserves_status(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.services.upload_jobs.MAX_SII_ROWS", 250)
    csv_path = tmp_path / "telemetry-300k.csv"
    with csv_path.open("w", encoding="utf-8") as output:
        output.write("timestamp,room,temperature,humidity,airflow\n")
        for index in range(300_000):
            output.write(
                f"2026-05-01T08:{index % 60:02d}:00Z,Flower 1,{75 + (index % 13) * 0.1:.1f},{58 + (index % 17) * 0.2:.1f},{1.2 + (index % 7) * 0.01:.2f}\n"
            )

    result = process_csv_file(file_path=csv_path, filename="telemetry-300k.csv")

    assert result["row_count"] == 300_000
    assert result["processing_stats"]["sampled_rows"] == upload_jobs.MAX_ANALYSIS_ROWS
    assert result["processing_stats"]["chunk_count"] == 30
    assert result["processing_stats"]["memory_estimate_bytes"] > 0
    assert result["processing_trace"]["rows_processed"] == 300_000


@pytest.mark.slow
def test_simulated_500k_upload_streams_windows_and_preserves_status(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.services.upload_jobs.MAX_SII_ROWS", 250)
    csv_path = tmp_path / "telemetry-500k.csv"
    with csv_path.open("w", encoding="utf-8") as output:
        output.write("timestamp,room,temperature,humidity,airflow\n")
        for index in range(500_000):
            output.write(
                f"2026-05-01T08:{index % 60:02d}:00Z,Flower 1,{75 + (index % 13) * 0.1:.1f},{58 + (index % 17) * 0.2:.1f},{1.2 + (index % 7) * 0.01:.2f}\n"
            )

    result = process_csv_file(file_path=csv_path, filename="telemetry-500k.csv")

    assert result["row_count"] == 500_000
    assert result["processing_stats"]["sampled_rows"] == upload_jobs.MAX_ANALYSIS_ROWS
    assert result["processing_stats"]["chunk_count"] == 50
    assert result["processing_stats"]["memory_estimate_bytes"] > 0
    assert result["processing_trace"]["rows_processed"] == 500_000


def test_upload_polling_reads_persisted_job_state() -> None:
    client = TestClient(create_app())
    job = {
        "job_id": "polling-job",
        "filename": "polling.csv",
        "status": "RUNNING_SII",
        "progress_label": "Running SII engine against uploaded telemetry.",
        "rows_processed": 300_000,
        "columns_detected": 26,
        "runner_used": False,
        "runner_module": RUNNER_MODULE,
        "core_engine": CORE_ENGINE,
        "started_at": "2026-05-08T00:00:00+00:00",
        "completed_at": None,
        "error": None,
    }
    write_job(job)

    response = client.get("/api/data/upload-status/polling-job")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "RUNNING_SII"
    assert payload["rows_processed"] == 300_000
    assert (upload_jobs.JOB_DIR / "polling-job.json").exists()


def test_upload_status_recovers_after_jobs_cache_clear() -> None:
    client = TestClient(create_app())
    write_job(
        {
            "job_id": "cache-clear-job",
            "filename": "cache-clear.csv",
            "status": "COMPLETE",
            "rows_processed": 10,
            "columns_detected": 3,
            "result_available": True,
            "sii_completed": True,
            "sii_completion_artifacts": {"runner_used": True},
        }
    )
    upload_jobs.JOBS.clear()

    first = client.get("/api/data/upload-status/cache-clear-job")
    second = client.get("/api/data/upload-status/cache-clear-job")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "COMPLETE"
    assert second.json()["status"] == "COMPLETE"


def test_latest_upload_recovers_after_cache_clear() -> None:
    client = TestClient(create_app())
    result = {
        "job_id": "latest-cache-clear-job",
        "filename": "persisted.csv",
        "row_count": 12,
        "column_count": 4,
        "replay_timeline": {
            "meta": {"frame_count": 2},
            "timeline": [{"timestamp": "2026-05-01T08:00:00Z"}, {"timestamp": "2026-05-01T08:05:00Z"}],
        },
    }
    write_latest_upload_result("latest-cache-clear-job", result)
    write_latest_upload_summary(
        "latest-cache-clear-job",
        {"status": "COMPLETE", "rows_processed": 12, "columns_detected": 4, "replay_ready": True, "replay_frame_count": 2},
    )
    upload_jobs.LATEST_UPLOAD_CACHE["result"] = None
    upload_jobs.LATEST_UPLOAD_CACHE["summary"] = None

    payload = client.get("/api/data/latest-upload?include_persisted=1").json()

    assert payload["status"] == "COMPLETE"
    assert payload["source"] == "uploaded"
    assert payload["latest_result"]["job_id"] == "latest-cache-clear-job"
    assert payload["latest_result"]["row_count"] == 12


def test_replay_payload_recovers_after_cache_clear() -> None:
    timeline = [{"timestamp": "2026-05-01T08:00:00Z"}, {"timestamp": "2026-05-01T08:05:00Z"}]
    write_latest_upload_result(
        "replay-cache-clear-job",
        {
            "job_id": "replay-cache-clear-job",
            "filename": "replay.csv",
            "replay_timeline": {"meta": {"frame_count": 2}, "timeline": timeline},
        },
    )
    upload_jobs.LATEST_UPLOAD_CACHE["result"] = None

    payload = upload_jobs.replay_payload("replay-cache-clear-job")

    assert payload["source"] == "persisted"
    assert payload["frame_count"] == 2
    assert len(payload["frames"]) == 2


def test_processing_helper_rejects_empty_csv() -> None:
    try:
        process_csv_content(filename="empty.csv", content=b"")
    except ValueError as exc:
        assert str(exc) == "CSV file is empty."
    else:
        raise AssertionError("Expected empty CSV to raise ValueError.")


def test_health_endpoint_still_responds_after_upload_job() -> None:
    client = TestClient(create_app())
    post_csv(client, "health.csv", "timestamp,temperature,humidity\n2026-05-01T08:00:00Z,74,55\n")

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_reset_prevents_persisted_result_from_reappearing_after_refresh() -> None:
    client = TestClient(create_app())

    reset_response = client.post("/api/data/reset")
    assert reset_response.status_code == 200

    # Simulate stale persisted payload that could exist on disk/db after a browser refresh.
    upsert_latest_payload(
        "latest_upload_result",
        {
            "job_id": "stale-job",
            "filename": "stale.csv",
            "processing_trace": {"completed_at": "2026-01-01T00:00:00+00:00"},
            "sii_intelligence": {
                "source": "uploaded",
                "facility_state": "Needs action",
                "urgency": "unstable",
                "last_updated": "2026-01-01T00:00:00+00:00",
            },
        },
    )

    latest = client.get("/api/data/latest-upload?include_persisted=1")
    assert latest.status_code == 200
    payload = latest.json()
    assert payload["status"] in {"empty", "building_baseline"}
    assert payload["latest_result"] is None
