from app.services import upload_jobs
from app.services.analysis_result_contract import build_behavior_windows
from app.services.upload_jobs import process_csv_content, reset_latest_upload_state, write_job
from app.services.upload_state_repository import write_latest_upload_result


def contract_fixture_csv() -> bytes:
    baseline_rows = [
        f"2026-05-01T08:{index:02d}:00Z,{100 + index},{200 + 2 * index},{50 + (index % 3) * 0.1:.1f}"
        for index in range(21)
    ]
    recent_rows = [
        f"2026-05-01T09:{index:02d}:00Z,{140 + index},{170 - 3 * index},{51 + (index % 2) * 0.1:.1f}"
        for index in range(9)
    ]
    content = "timestamp,pump_power,flow_rate,differential_pressure\n" + "\n".join(baseline_rows + recent_rows)
    return content.encode("utf-8")


def test_csv_analysis_returns_canonical_analysis_result() -> None:
    result = process_csv_content(
        filename="canonical-contract.csv",
        content=contract_fixture_csv(),
        job_id="canonicalcontract001",
    )

    analysis = result["analysis_result"]
    assert analysis["analysis_id"] == result["run_id"]
    assert analysis["upload_id"] == result["upload_id"]
    assert analysis["source_file"] == "canonical-contract.csv"
    assert set(analysis) >= {
        "data_quality",
        "executive_summary",
        "systems",
        "relationships",
        "fingerprint",
        "insights",
        "recommendations",
        "evidence_index",
        "warnings",
        "errors",
        "change_onset",
        "stable_window",
        "deviation_window",
        "current_state_window",
    }
    assert analysis["change_onset"]
    assert analysis["stable_window"]["description"] == "Reference behavior window used for baseline comparison."
    assert analysis["deviation_window"]["description"] == "Window where current behavior diverged from the reference pattern."
    assert analysis["current_state_window"]["description"] == "Most recent behavior window represented by this analysis result."
    assert analysis["normalized_telemetry"]["records"]
    first_record = analysis["normalized_telemetry"]["records"][0]
    assert set(first_record) >= {
        "timestamp",
        "tag_name",
        "value",
        "source_column",
        "quality",
        "missing_value_flags",
        "sampling_interval",
        "detected_metric_type",
    }


def test_behavior_windows_use_adaptive_baseline_indices() -> None:
    windows = build_behavior_windows(
        result={
            "timestamp_profile": {
                "first_timestamp": "2026-04-01T00:00:00Z",
                "last_timestamp": "2026-04-02T00:00:00Z",
                "estimated_sample_interval": "15 minutes",
            },
            "row_count": 120,
        },
        baseline={
            "baseline_window_rows": 4,
            "recent_window_rows": 4,
            "adaptive_baseline": {"strategy": "lowest_variability_window", "start_index": 4, "end_index": 8},
        },
        relationships=[],
        insights=[],
    )

    assert windows["stable_window"]["start"] == "2026-04-01T01:00:00Z"
    assert windows["stable_window"]["end"] == "2026-04-01T02:00:00Z"
    assert windows["stable_window"]["time_window"] == "2026-04-01T01:00:00Z to 2026-04-01T02:00:00Z"


def test_analysis_completion_does_not_require_replay(monkeypatch) -> None:
    def fail_replay(*args, **kwargs):
        raise RuntimeError("replay disabled")

    monkeypatch.setattr(upload_jobs, "_build_replay", fail_replay)
    monkeypatch.setattr(upload_jobs, "_minimal_replay", fail_replay)

    result = process_csv_content(
        filename="no-replay.csv",
        content=contract_fixture_csv(),
        job_id="noreplay001",
    )

    assert result["analysis_result"]["status"] == "complete"
    assert result["analysis_result"]["insights"]
    assert result["replay_ready"] is False
    assert result["replay_frame_count"] == 0
    assert result["replay_timeline"]["timeline"] == []
    assert result["sii_intelligence"]["replay_timeline"]["timeline"] == []


def test_saved_analysis_result_is_viewable_without_replay(client, monkeypatch) -> None:
    def fail_replay(*args, **kwargs):
        raise RuntimeError("replay disabled")

    monkeypatch.setattr(upload_jobs, "_build_replay", fail_replay)
    monkeypatch.setattr(upload_jobs, "_minimal_replay", fail_replay)

    result = process_csv_content(
        filename="viewable-no-replay.csv",
        content=contract_fixture_csv(),
        job_id="viewablenoreplay001",
    )
    write_latest_upload_result("viewablenoreplay001", result)

    status_payload = client.get("/api/data/upload-status/viewablenoreplay001").json()
    assert status_payload["result_available"] is True
    assert status_payload["first_usable_available"] is True
    assert status_payload["replay_ready"] is False

    latest_payload = client.get("/api/data/latest-upload?include_persisted=1").json()
    assert latest_payload["analysis_result"]["status"] == "complete"
    assert latest_payload["analysis_result"]["analysis_id"] == result["analysis_result"]["analysis_id"]
    assert latest_payload["result_available"] is True
    assert latest_payload["first_usable_available"] is True
    assert latest_payload["sii_completed"] is True


def test_canonical_insights_and_fingerprint_are_evidence_backed() -> None:
    result = process_csv_content(
        filename="canonical-evidence.csv",
        content=contract_fixture_csv(),
        job_id="canonicalevidence001",
    )
    analysis = result["analysis_result"]
    evidence_index = analysis["evidence_index"]
    placeholder_titles = {
        "structural drift observed",
        "persistent structural drift observed",
        "placeholder",
    }

    assert analysis["insights"]
    for insight in analysis["insights"]:
        assert insight["title"].lower() not in placeholder_titles
        assert "pending verification" not in insight["title"].lower()
        assert insight["evidence_refs"]
        assert all(ref in evidence_index for ref in insight["evidence_refs"])
        assert insight["source_tags"]
        assert insight["time_window"]

    fingerprint = analysis["fingerprint"]
    assert fingerprint["evidence_refs"]
    assert fingerprint["explanation"]
    assert all(ref in evidence_index for ref in fingerprint["evidence_refs"])

    for relationship in analysis["relationships"]:
        assert relationship["evidence_refs"]
        assert all(ref in evidence_index for ref in relationship["evidence_refs"])

    for recommendation in analysis["recommendations"]:
        assert recommendation["evidence_refs"]
        assert all(ref in evidence_index for ref in recommendation["evidence_refs"])


def test_latest_upload_does_not_reuse_stale_analysis_for_new_upload(client) -> None:
    reset_latest_upload_state()
    completed = process_csv_content(
        filename="completed-contract.csv",
        content=contract_fixture_csv(),
        job_id="completedcontract001",
    )
    write_latest_upload_result("completedcontract001", completed)
    write_job(
        {
            "job_id": "queuedcontract001",
            "filename": "queued-contract.csv",
            "status": "PENDING",
            "processing_state": "queued",
            "message": "Upload accepted. Processing is queued.",
        }
    )

    payload = client.get("/api/data/latest-upload?include_persisted=1").json()

    assert payload["job_id"] == "queuedcontract001"
    assert payload["latest_result"] is None
    assert payload["analysis_result"]["status"] == "queued"
    assert payload["analysis_result"]["insights"] == []
