from fastapi.testclient import TestClient

from app.main import create_app
from app.services.runtime_db import upsert_latest_payload
from app.services.upload_jobs import write_job, write_latest_upload_summary


def test_upload_status_complete_without_sii_contract_is_failed() -> None:
    client = TestClient(create_app())
    job_id = "contract-missing-sii"
    write_job(
        {
            "job_id": job_id,
            "filename": "contract.csv",
            "status": "COMPLETE",
            "progress_label": "Telemetry processing complete.",
            "rows_processed": 100,
            "columns_detected": 4,
            "runner_used": True,
            "runner_module": "runner",
            "core_engine": "engine",
            "started_at": "2026-05-18T00:00:00+00:00",
            "completed_at": "2026-05-18T00:05:00+00:00",
            "result_summary": {"filename": "contract.csv"},
            "result_available": True,
            "first_usable_available": True,
        }
    )
    payload = client.get(f"/api/data/upload-status/{job_id}").json()
    assert payload["status"] == "FAILED"
    assert payload["error_type"] == "sii_completion_missing"
    assert payload["sii_completed"] is False


def test_upload_status_complete_with_sii_contract_remains_complete() -> None:
    client = TestClient(create_app())
    job_id = "contract-has-sii"
    write_job(
        {
            "job_id": job_id,
            "filename": "contract.csv",
            "status": "COMPLETE",
            "progress_label": "Telemetry processing complete.",
            "rows_processed": 100,
            "columns_detected": 4,
            "runner_used": True,
            "runner_module": "runner",
            "core_engine": "engine",
            "started_at": "2026-05-18T00:00:00+00:00",
            "completed_at": "2026-05-18T00:05:00+00:00",
            "result_summary": {
                "filename": "contract.csv",
                "sii_completed": True,
                "sii_completion_artifacts": {
                    "runner_used": True,
                    "intelligence_present": True,
                    "processing_trace_present": True,
                    "engine_result_present": True,
                },
            },
            "sii_completed": True,
            "sii_completion_artifacts": {
                "runner_used": True,
                "intelligence_present": True,
                "processing_trace_present": True,
                "engine_result_present": True,
            },
            "result_available": True,
            "first_usable_available": True,
        }
    )
    payload = client.get(f"/api/data/upload-status/{job_id}").json()
    assert payload["status"] == "COMPLETE"
    assert payload["sii_completed"] is True


def test_latest_upload_requires_sii_contract_for_active_status() -> None:
    client = TestClient(create_app())
    write_latest_upload_summary(
        "latest-contract",
        {
            "filename": "latest.csv",
            "rows_processed": 20,
            "columns_detected": 4,
            "last_processed_at": "2026-05-18T00:00:00+00:00",
            "runner_used": True,
            "runner_module": "runner",
            "core_engine": "engine",
            "source": "uploaded",
            "sii_completed": False,
            "sii_completion_artifacts": {},
        },
        append_history=False,
    )
    upsert_latest_payload(
        "latest_upload_result",
        {
            "job_id": "latest-contract",
            "filename": "latest.csv",
            "row_count": 20,
            "column_count": 4,
            "sii_intelligence": {"source": "uploaded"},
            "engine_result": {"overall_result": "stable"},
            "processing_trace": {"status": "ok"},
            "data_quality": {"readiness": "ready"},
            "operator_report": {"summary": "ok"},
            "room_summary": {"room_count": 1, "rooms": [{"room": "A", "row_count": 20}]},
        },
    )
    payload = client.get("/api/data/latest-upload?include_persisted=1").json()
    assert payload["status"] != "active"
    assert payload["sii_completed"] is False
