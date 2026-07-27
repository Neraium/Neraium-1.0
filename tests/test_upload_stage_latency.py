from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from app.routers import data as data_router
from app.services import upload_jobs
from app.services.runtime_db import (
    claim_next_upload_job,
    enqueue_upload_job,
    read_upload_queue_job,
)


def normal_csv(row_count: int = 1200) -> str:
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    lines = ["timestamp,temp,humidity,airflow,pressure"]
    for index in range(row_count):
        timestamp = (start + timedelta(minutes=index)).isoformat().replace("+00:00", "Z")
        lines.append(
            f"{timestamp},{72 + (index % 13) * 0.05:.3f},"
            f"{50 + (index % 17) * 0.04:.3f},"
            f"{410 + (index % 19) * 0.3:.3f},"
            f"{1.4 + (index % 7) * 0.01:.4f}"
        )
    return "\n".join(lines)


def test_upload_request_returns_timing_fields_without_running_analysis_inline(client, monkeypatch) -> None:
    monkeypatch.setattr(data_router, "_dispatch_upload_worker_for_runtime", lambda _runtime_dir: None)

    inline_attempts = []

    def fail_if_status_processes_work() -> bool:
        inline_attempts.append(True)
        raise AssertionError("status reads must not process queued analysis")

    monkeypatch.setattr(upload_jobs, "process_next_queued_upload_job", fail_if_status_processes_work)
    started_at = time.perf_counter()
    response = client.post(
        "/api/data/upload",
        files={"file": ("normal.csv", normal_csv(120), "text/csv")},
    )
    request_seconds = time.perf_counter() - started_at

    assert response.status_code == 202
    payload = response.json()
    assert request_seconds < 3.0
    assert payload["status"] == "PENDING"
    assert payload["job_created_at"]
    assert payload["enqueued_at"]
    assert payload["stage_changed_at"]
    assert payload["timings"]["upload_transfer_ms"] >= 0
    assert payload["timings"]["backend_request_handling_ms"] >= 0
    assert payload["timings"]["job_creation_ms"] >= 0
    assert payload["timings"]["request_to_job_created_ms"] >= 0

    status_response = client.get(payload["status_url"])

    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["status"] == "PENDING"
    assert status_payload["status_request_ms"] >= 0
    assert status_payload["status_server_sent_at"]
    assert inline_attempts == []


def test_normal_csv_records_every_analysis_stage_timing(caplog) -> None:
    caplog.set_level("INFO")
    started_at = time.perf_counter()

    result = upload_jobs.process_csv_content(normal_csv(), filename="normal-profile.csv")

    elapsed_seconds = time.perf_counter() - started_at
    timings = result["processing_stats"]["timings"]
    for phase in (
        "validation_ms",
        "mapping_ms",
        "baseline_creation_ms",
        "comparison_ms",
        "evidence_generation_ms",
        "persistence_ms",
        "total_job_ms",
    ):
        assert timings[phase] >= 0
    assert elapsed_seconds < 10.0
    assert result["sii_runner_result"]["rows_processed"] <= 1024
    assert result["sii_runner_result"]["sampling_applied"] is True
    assert "upload_stage_timing event=job_completed" in caplog.text


def test_duplicate_enqueue_does_not_reset_processing_job() -> None:
    upload_jobs.write_job({
        "job_id": "duplicate-active-job",
        "filename": "duplicate.csv",
        "status": "PENDING",
        "processing_state": "queued",
    })
    enqueue_upload_job("duplicate-active-job")
    assert claim_next_upload_job() == "duplicate-active-job"

    enqueue_upload_job("duplicate-active-job")

    queue_entry = read_upload_queue_job("duplicate-active-job")
    assert queue_entry is not None
    assert queue_entry["status"] == "processing"
    assert queue_entry["attempts"] == 1


def test_worker_records_queue_pickup_delay(monkeypatch) -> None:
    job_id = "worker-pickup-job"
    source = upload_jobs.UPLOAD_DIR / "worker-pickup.csv"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(normal_csv(12), encoding="utf-8")
    upload_jobs.write_job({
        "job_id": job_id,
        "filename": source.name,
        "file_path": source.name,
        "status": "PENDING",
        "processing_state": "queued",
    })
    enqueue_upload_job(job_id)
    observed = {}

    def complete_without_analysis(path, **kwargs):
        current = upload_jobs.read_upload_status(kwargs["job_id"]) or {}
        observed.update(current)
        upload_jobs.write_job({
            **current,
            "job_id": kwargs["job_id"],
            "status": "COMPLETE",
            "processing_state": "complete",
            "result_available": True,
            "sii_completed": True,
        })
        return {"job_id": kwargs["job_id"]}

    monkeypatch.setattr(upload_jobs, "process_csv_file", complete_without_analysis)

    assert upload_jobs.process_next_queued_upload_job() is True
    assert observed["worker_started_at"]
    assert observed["worker_pickup_delay_ms"] >= 0
    assert observed["timings"]["worker_pickup_delay_ms"] == observed["worker_pickup_delay_ms"]
