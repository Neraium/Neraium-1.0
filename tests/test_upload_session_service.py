from fastapi.testclient import TestClient

from app.main import create_app
from app.services.upload_session_service import (
    SESSION_STATE_EMPTY,
    SESSION_STATE_PROCESSING,
    SESSION_STATE_RESTORED,
    SESSION_STATE_STALE,
    SESSION_STATE_VERIFIED,
    resolve_latest_upload_session,
    resolve_upload_status,
)
from app.services.upload_state_repository import write_latest_upload_result, write_latest_upload_summary


def _result(job_id: str) -> dict:
    return {
        "job_id": job_id,
        "run_id": job_id,
        "upload_id": job_id,
        "filename": f"{job_id}.csv",
        "row_count": 12,
        "column_count": 3,
        "engine_result": {"overall_result": "stable"},
        "room_summary": {"room_count": 1, "rooms": [{"room": "Uploaded telemetry", "row_count": 12}]},
        "sii_intelligence": {"facility_state": "Monitoring", "last_updated": "2026-06-20T00:00:00+00:00"},
        "traceability": {"job_id": job_id, "run_id": job_id, "upload_id": job_id},
        "session_scope": {"active": True, "status": "active", "job_id": job_id, "run_id": job_id, "upload_id": job_id},
        "replay_timeline": {"timeline": [{"timestamp": "2026-06-20T00:00:00+00:00"}]},
        "last_processed_at": "2026-06-20T00:00:00+00:00",
        "completed_at": "2026-06-20T00:00:00+00:00",
    }


def test_latest_upload_reports_empty_when_no_session_exists() -> None:
    client = TestClient(create_app())
    payload = client.get("/api/data/latest-upload?include_persisted=1").json()
    assert payload["session_state"] == SESSION_STATE_EMPTY


def test_latest_upload_reports_restored_when_persisted_session_is_recovered() -> None:
    job_id = "restored-session"
    write_latest_upload_result(job_id, _result(job_id))
    client = TestClient(create_app())
    payload = client.get("/api/data/latest-upload?include_persisted=1").json()
    assert payload["session_state"] in {SESSION_STATE_RESTORED, SESSION_STATE_VERIFIED}
    assert payload["upload_session_id"] == job_id


def test_startup_warmup_restores_persisted_session_after_process_restart() -> None:
    from app.services.upload_runtime_state import UPLOAD_RUNTIME_STATE
    from app.services.upload_state_repository import warm_latest_upload_cache

    job_id = "restart-restored-session"
    write_latest_upload_result(job_id, _result(job_id))
    UPLOAD_RUNTIME_STATE.jobs.clear()
    UPLOAD_RUNTIME_STATE.latest_upload_cache.update(
        {"summary": None, "result": None, "canonical": None}
    )
    UPLOAD_RUNTIME_STATE.reset_block_persisted = True

    warm_latest_upload_cache()
    payload = resolve_latest_upload_session(include_persisted=True)

    assert UPLOAD_RUNTIME_STATE.reset_block_persisted is False
    assert payload["session_state"] in {SESSION_STATE_RESTORED, SESSION_STATE_VERIFIED}
    assert payload["upload_session_id"] == job_id
    assert payload["latest_result"]["filename"] == f"{job_id}.csv"


def test_latest_upload_reports_processing_for_active_summary_without_result() -> None:
    job_id = "processing-session"
    write_latest_upload_summary(
        job_id,
        {
            "job_id": job_id,
            "run_id": job_id,
            "upload_id": job_id,
            "filename": f"{job_id}.csv",
            "status": "PROCESSING",
            "processing_state": "parsing_telemetry",
            "progress": 42,
            "message": "Normalizing telemetry...",
            "session_scope": {"active": True, "status": "processing", "job_id": job_id, "run_id": job_id, "upload_id": job_id},
        },
    )
    client = TestClient(create_app())
    payload = client.get(f"/api/data/upload-status/{job_id}").json()
    assert payload["session_state"] == SESSION_STATE_PROCESSING


def test_historical_job_status_is_marked_stale_after_session_switch() -> None:
    current_job = "current-session"
    stale_job = "stale-session"
    write_latest_upload_result(stale_job, _result(stale_job))
    write_latest_upload_result(current_job, _result(current_job))
    client = TestClient(create_app())
    payload = client.get(f"/api/data/upload-status/{stale_job}").json()
    assert payload["session_state"] == SESSION_STATE_STALE
    current_payload = client.get("/api/data/latest-upload?include_persisted=1").json()
    assert current_payload["session_state"] in {SESSION_STATE_RESTORED, SESSION_STATE_VERIFIED}


def test_status_poll_does_not_load_analysis_result_when_status_exists(monkeypatch) -> None:
    job_id = "status-only-session"
    write_latest_upload_summary(
        job_id,
        {
            "job_id": job_id,
            "filename": "status-only.csv",
            "status": "PROCESSING",
            "processing_state": "parsing_telemetry",
            "progress": 40,
        },
    )

    def fail_result_read(_job_id):
        raise AssertionError("status polling must not load analysis results")

    monkeypatch.setattr("app.services.upload_session_service.read_upload_result_by_job_id", fail_result_read)
    payload = resolve_upload_status(job_id)
    assert payload["job_id"] == job_id
    assert payload["processing_state"] == "parsing_telemetry"


def test_latest_transport_result_omits_internal_large_artifacts() -> None:
    job_id = "compact-result-session"
    result = _result(job_id)
    result["sii_result"] = {"large": ["value"] * 100}
    result["baseline_analysis"] = {"relationship_graph": {"edges": [1, 2, 3]}, "summary": "ready"}
    write_latest_upload_result(job_id, result)
    payload = resolve_latest_upload_session(include_persisted=True)
    assert "sii_result" not in payload["latest_result"]
    assert "relationship_graph" not in payload["latest_result"]["baseline_analysis"]
    assert payload["latest_result"]["transport_projection"]["version"] == 1
