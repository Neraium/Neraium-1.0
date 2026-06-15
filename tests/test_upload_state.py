from app.services.upload_state import (
    build_empty_latest_upload_record,
    build_latest_upload_record,
    build_session_scope,
    build_replay_payload_from_result,
    select_current_upload_result,
)


def test_build_latest_upload_record_preserves_canonical_identity_and_lineage() -> None:
    result = {
        "job_id": "canonical-job",
        "run_id": "canonical-run",
        "upload_id": "canonical-upload",
        "filename": "canonical.csv",
        "session_scope": build_session_scope("canonical-job", filename="canonical.csv", status="active"),
        "traceability": {"job_id": "canonical-job", "aligned": True},
        "replay_timeline": {"meta": {"mode": "live"}, "timeline": [{"frame_index": 0}]},
    }
    summary = {
        "job_id": "canonical-job",
        "run_id": "canonical-run",
        "upload_id": "canonical-upload",
        "processing_state": "complete",
        "status": "COMPLETE",
    }

    record = build_latest_upload_record(summary=summary, result=result, evidence={"run_id": "canonical-job"})

    assert record["job_id"] == "canonical-job"
    assert record["run_id"] == "canonical-run"
    assert record["upload_id"] == "canonical-upload"
    assert record["replay"]["job_id"] == "canonical-job"
    assert record["replay"]["traceability"]["aligned"] is True
    assert record["session_scope"]["active"] is True


def test_select_current_upload_result_rejects_missing_active_scope() -> None:
    record = {
        "job_id": "stale-job",
        "result": {
            "job_id": "stale-job",
            "session_scope": {"active": False, "job_id": "stale-job"},
        },
    }

    assert select_current_upload_result(record) is None


def test_build_empty_latest_upload_record_stays_explicitly_empty() -> None:
    record = build_empty_latest_upload_record()
    replay = build_replay_payload_from_result(None)

    assert record["status"] == "empty"
    assert record["session_scope"]["active"] is False
    assert replay["timeline"] == []
    assert replay["replay_ready"] is False
