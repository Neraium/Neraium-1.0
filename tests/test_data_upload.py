from fastapi.testclient import TestClient

from app.main import create_app
from app.services.sii_runner import STATE_PATH
from app.services.upload_jobs import JOB_DIR, process_csv_content, process_csv_file, read_job, write_job


def post_csv(client: TestClient, filename: str, content: str):
    return client.post(
        "/api/data/upload",
        files={"file": (filename, content, "text/csv")},
    )


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
    assert payload["message"] == "Telemetry batch received. Processing started."
    assert payload["status_url"] == f"/api/data/upload-status/{payload['job_id']}"
    assert payload["file_size_bytes"] > 0


def test_upload_status_returns_complete_job_summary_and_writes_state() -> None:
    client = TestClient(create_app())
    rows = "\n".join(
        f"2026-05-01T08:{index:02d}:00Z,Flower 1,{75 + index * 0.1:.1f},{58 + index * 0.2:.1f}"
        for index in range(8)
    )

    upload = post_csv(client, "ready-report.csv", f"timestamp,room,temperature,humidity\n{rows}")
    job_id = upload.json()["job_id"]
    status = client.get(f"/api/data/upload-status/{job_id}")

    assert status.status_code == 200
    payload = status.json()
    assert payload["job_id"] == job_id
    assert payload["status"] == "COMPLETE"
    assert payload["progress_label"] == "Telemetry processing complete."
    assert payload["rows_processed"] == 8
    assert payload["columns_detected"] == 4
    assert payload["runner_used"] is True
    assert payload["runner_module"] == "neraium_core.sii_engine_adapter.SIIEngineAdapter"
    assert payload["core_engine"] == "neraium_core.sii_engine_unified.SIIEngine"
    assert payload["error"] is None
    assert payload["result_summary"]["filename"] == "ready-report.csv"
    assert STATE_PATH.exists()


def test_upload_status_can_return_queued_state() -> None:
    client = TestClient(create_app())
    response = post_csv(client, "queued.csv", "timestamp,temperature,humidity\n2026-05-01T08:00:00Z,74,55\n")
    job = read_job(response.json()["job_id"])

    assert job is not None
    job["status"] = "queued"
    write_job(job)
    status = client.get(f"/api/data/upload-status/{job['job_id']}")

    assert status.status_code == 200
    assert status.json()["status"] == "PENDING"


def test_upload_status_can_return_failed_state() -> None:
    client = TestClient(create_app())
    response = post_csv(client, "failed.csv", "timestamp,temperature\n2026-05-01T08:00:00Z,74\n")
    job = read_job(response.json()["job_id"])

    assert job is not None
    job["status"] = "failed"
    job["error"] = "Example failure"
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
    post_csv(client, "latest.csv", f"timestamp,temperature,humidity\n{rows}")

    response = client.get("/api/data/latest-upload")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "uploaded"
    assert payload["last_filename"] == "latest.csv"
    assert payload["rows_processed"] == 6
    assert payload["columns_detected"] == 3
    assert payload["state_available"] is True


def test_facility_systems_uses_latest_state_after_upload() -> None:
    client = TestClient(create_app())
    rows = "\n".join(
        f"2026-05-01T08:{index:02d}:00Z,Flower 1,{75 + index},{58 + index}"
        for index in range(6)
    )
    post_csv(client, "facility-state.csv", f"timestamp,room,temperature,humidity\n{rows}")

    response = client.get("/api/facility/systems")

    assert response.status_code == 200
    payload = response.json()
    assert payload["intelligence"]["source"] == "uploaded"
    assert payload["intelligence"]["runner_module"] == "neraium_core.sii_engine_adapter.SIIEngineAdapter"


def test_one_column_csv_reports_runner_error_without_failed_job() -> None:
    client = TestClient(create_app())
    rows = "\n".join(f"2026-05-01T08:{index:02d}:00Z,{75 + index}" for index in range(6))

    upload = post_csv(client, "one-column.csv", f"timestamp,temperature\n{rows}")
    status = client.get(upload.json()["status_url"])

    assert status.status_code == 200
    payload = status.json()
    assert payload["status"] == "COMPLETE"
    assert payload["runner_used"] is False
    assert payload["error"] is None
    assert payload["result_summary"]["runner_errors"]


def test_upload_rejects_invalid_extension() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/data/upload",
        files={"file": ("sensor-export.txt", "timestamp,value\n2026-05-01,75", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only .csv files are supported."


def test_upload_rejects_empty_csv() -> None:
    client = TestClient(create_app())

    response = post_csv(client, "empty.csv", "")

    assert response.status_code == 400
    assert response.json()["detail"] == "CSV file is empty."


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
    assert result["sii_runner_result"]["runner_module"] == "neraium_core.sii_engine_adapter.SIIEngineAdapter"


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
    assert result["processing_stats"]["sampled_rows"] == 50_000
    assert result["processing_stats"]["chunk_count"] == 10


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
    assert result["processing_stats"]["sampled_rows"] == 50_000
    assert result["processing_stats"]["chunk_count"] == 30
    assert result["processing_stats"]["memory_estimate_bytes"] > 0
    assert result["processing_trace"]["rows_processed"] == 300_000


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
        "runner_module": "neraium_core.sii_engine_adapter.SIIEngineAdapter",
        "core_engine": "neraium_core.sii_engine_unified.SIIEngine",
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
    assert (JOB_DIR / "polling-job.json").exists()


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
