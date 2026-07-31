from app.services.analysis_provenance import build_analysis_provenance, result_digest
from app.services.upload_jobs import process_csv_content


def _result() -> dict:
    return {
        "run_id": "analysis-1",
        "upload_id": "upload-1",
        "organization_id": "org-1",
        "portfolio_id": "portfolio-1",
        "site_id": "site-1",
        "system_id": "chw-loop-1",
        "dataset_id": "dataset-2",
        "baseline_id": "baseline-1",
        "baseline_dataset_id": "dataset-1",
        "ingestion_report": {"input_hash": "abc123"},
        "engine_result": {"overall_result": "needs_review"},
        "analysis_result": {"conditions": [{"condition_id": "condition-1"}]},
        "processing_trace": {"mode_aware_authority": {"enabled": True}},
        "active_baseline_reference": {"version": 3, "model_hash": "baseline-hash"},
    }


def test_provenance_captures_identity_versions_and_deterministic_hashes() -> None:
    first = build_analysis_provenance(_result())
    second = build_analysis_provenance(_result())

    assert first == second
    assert first["site_id"] == "site-1"
    assert first["system_id"] == "chw-loop-1"
    assert first["input_hash"] == "abc123"
    assert first["baseline_version"] == 3
    assert first["baseline_hash"] == "baseline-hash"
    assert first["configuration"]["mode_authority"] == "suppression_only"
    assert len(first["configuration_hash"]) == 64
    assert len(first["result_hash"]) == 64


def test_result_digest_ignores_runtime_noise_but_changes_with_decision() -> None:
    base = _result()
    noisy = {**base, "processing_time_seconds": 99, "completed_at": "2026-07-20T09:00:00Z"}
    changed = {**base, "engine_result": {"overall_result": "complete"}}

    assert result_digest(base) == result_digest(noisy)
    assert result_digest(base) != result_digest(changed)


def test_committed_upload_result_verifies_against_recorded_evidence_hash(client) -> None:
    rows = "\n".join(
        f"2026-07-20T{index:02d}:00:00Z,Central Plant,{40 + index * 0.1:.2f},{120 - index * 0.2:.2f},{55 + index * 0.3:.2f}"
        for index in range(18)
    )
    result = process_csv_content(
        f"timestamp,system,supply_temperature,flow,pump_speed\n{rows}\n",
        filename="integrity-hydronic.csv",
        job_id="integrity-hydronic-run",
    )

    response = client.get(f"/api/evidence/runs/{result['run_id']}/integrity")

    assert response.status_code == 200
    assert response.json()["status"] == "verified"
    assert response.json()["result_hash_matches"] is True
    assert response.json()["input_hash_recorded"] is True
