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
    }
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
