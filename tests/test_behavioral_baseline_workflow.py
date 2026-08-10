from __future__ import annotations

import time

import pytest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import create_app
from app.services import behavioral_baseline, behavioral_model_repository, upload_jobs, upload_pipeline
from app.services.baseline_analysis_repository import persist_completed_analysis, stamp_comparison_analysis_identity
from app.services.dataset_scope import attach_dataset_scope, current_dataset_scope
from app.services.baseline_contracts import (
    PROHIBITED_BASELINE_OUTPUT_KEYS,
    prohibited_keys_present,
)
from app.services.behavioral_model_repository import (
    read_active_behavioral_model,
    read_baseline_result,
)
from app.services.evidence_store import read_evidence_run
from app.services.upload_state_repository import write_latest_upload_summary, write_upload_result
from app.services.upload_status_contract import normalize_upload_status_payload


def _baseline_csv(rows: int = 72) -> str:
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    body = []
    for index in range(rows):
        timestamp = (started + timedelta(minutes=5 * index)).isoformat().replace("+00:00", "Z")
        stage = 1 if (index // 18) % 2 == 0 else 2
        load = 35 + stage * 18 + (index % 9)
        flow = 80 + load * 1.7
        pressure = 12 + flow * 0.08
        body.append(f"{timestamp},{stage},{load:.3f},{flow:.3f},{pressure:.3f}")
    return "timestamp,equipment_stage,load_pct,flow_gpm,pressure_psi\n" + "\n".join(body)


def _wait(client: TestClient, status_url: str, headers: dict[str, str] | None = None) -> dict:
    deadline = time.time() + 15
    last = {}
    while time.time() < deadline:
        response = client.get(status_url, headers=headers)
        assert response.status_code == 200
        last = response.json()
        if last.get("status") in {"COMPLETE", "FAILED"}:
            return last
        time.sleep(0.05)
    raise AssertionError(f"baseline job did not complete: {last}")


def _post(
    client: TestClient,
    workflow: str,
    filename: str = "historical.csv",
    *,
    headers: dict[str, str] | None = None,
    approval_required: bool | None = None,
):
    data: dict[str, str] = {"workflow": workflow}
    if approval_required is not None:
        data["approval_required"] = "true" if approval_required else "false"
    return client.post(
        "/api/data/upload",
        data=data,
        files={"file": (filename, _baseline_csv(), "text/csv")},
        headers=headers,
    )


def test_create_baseline_never_invokes_sii_or_persists_detection_evidence(monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("the full SII runner must not be invoked for a baseline upload")

    monkeypatch.setattr(upload_pipeline, "evaluate_sii", fail_if_called)
    client = TestClient(create_app())

    accepted = _post(client, "create_baseline")

    assert accepted.status_code == 202
    queued = accepted.json()
    assert queued["workflow"] == "create_baseline"
    assert queued["sii_engine_invoked"] is False
    terminal = _wait(client, queued["status_url"])
    assert terminal["status"] == "COMPLETE"
    assert terminal["sii_completed"] is False
    assert terminal["sii_engine_invoked"] is False
    assert terminal["baseline_candidate_created"] is True
    assert terminal["evidence_persisted"] is False

    result_response = client.get(queued["baseline_result_url"])
    assert result_response.status_code == 200
    result = result_response.json()
    assert result["processing_trace"] == {
        **result["processing_trace"],
        "sii_engine_invoked": False,
        "detection_pipeline_invoked": False,
        "evidence_pipeline_invoked": False,
        "replay_generated": False,
    }
    assert prohibited_keys_present(result) == []
    assert not (set(result) & PROHIBITED_BASELINE_OUTPUT_KEYS)
    assert read_evidence_run(queued["job_id"]) is None
    latest_analysis = client.get("/api/data/latest-upload").json()
    assert latest_analysis["latest_result"] is None


def test_completed_baseline_contract_propagates_id_and_supports_recovery_lookups() -> None:
    client = TestClient(create_app())
    accepted = _post(client, "create_baseline").json()
    terminal = _wait(client, accepted["status_url"])

    baseline_id = terminal["baselineId"]
    expected_contract = {
        "status": "completed",
        "datasetId": terminal["datasetId"],
        "jobId": terminal["jobId"],
        "baselineId": baseline_id,
        "workspacePath": f"/baselines/{baseline_id}/ready",
        "createdAt": terminal["createdAt"],
        "portfolioId": "default",
        "systemId": "default",
    }
    assert terminal["job_id"] == expected_contract["jobId"]
    assert terminal["dataset_id"] == expected_contract["datasetId"]
    assert terminal["result_available"] is True
    assert client.get(f"/api/data/jobs/{terminal['jobId']}/result").json() == expected_contract
    assert client.get(f"/api/data/datasets/{terminal['datasetId']}/baseline").json() == expected_contract

    persisted = read_baseline_result(terminal["jobId"])
    assert persisted["baselineId"] == baseline_id
    assert persisted["candidate_model"]["model_id"] == baseline_id
    assert persisted["candidate_model"]["baseline_id"] == baseline_id
    detail = client.get(f"/api/data/portfolios/default/baselines/{baseline_id}")
    assert detail.status_code == 200
    assert detail.json()["baseline_id"] == baseline_id


def test_dataset_baseline_lookup_uses_index_references_without_model_scan(monkeypatch) -> None:
    client = TestClient(create_app())
    accepted = _post(client, "create_baseline").json()
    terminal = _wait(client, accepted["status_url"])

    index_entry = next(
        entry
        for entry in behavioral_model_repository.read_model_index()["models"]
        if entry["model_id"] == terminal["baselineId"]
    )
    assert index_entry["dataset_id"] == terminal["datasetId"]
    assert index_entry["job_id"] == terminal["jobId"]

    def reject_model_scan(_model_id: str):
        raise AssertionError("indexed dataset lookup should not scan model records")

    monkeypatch.setattr(behavioral_model_repository, "read_model", reject_model_scan)
    result = behavioral_model_repository.read_baseline_result_by_dataset_id(terminal["datasetId"])

    assert result["baselineId"] == terminal["baselineId"]
    assert result["jobId"] == terminal["jobId"]


def test_completed_baseline_status_is_rejected_without_baseline_id() -> None:
    normalized = normalize_upload_status_payload({
        "status": "COMPLETE",
        "processing_state": "complete",
        "workflow": "create_baseline",
        "job_id": "job-without-baseline",
        "dataset_id": "dataset-without-baseline",
        "completed_at": "2026-07-30T00:00:00+00:00",
        "result_available": True,
        "baseline_result_available": True,
    })

    assert normalized["status"] == "FAILED"
    assert normalized["job_state"] == "failed"
    assert normalized["result_available"] is False
    assert normalized["baseline_result_available"] is False
    assert normalized["error_type"] == "baseline_identifier_missing"


def test_candidate_requires_approval_and_activation_is_separate() -> None:
    client = TestClient(create_app())
    queued = _post(client, "create_baseline").json()
    terminal = _wait(client, queued["status_url"])
    result = client.get(queued["baseline_result_url"]).json()
    candidate = result["candidate_model"]

    assert terminal["baseline_activation_state"] == "awaiting_approval"
    assert candidate["status"] == "awaiting_approval"
    assert read_active_behavioral_model() is None

    approval = client.post(
        f"/api/data/baselines/candidates/{candidate['model_id']}/approve",
        json={"note": "Historical period reviewed by operations."},
    )

    assert approval.status_code == 200
    assert approval.json()["active_model"]["status"] == "active"
    assert read_active_behavioral_model()["model_id"] == candidate["model_id"]
    persisted = read_baseline_result(queued["job_id"])
    assert persisted["activation"]["state"] == "active"


def test_approval_can_be_disabled_by_controlled_policy() -> None:
    client = TestClient(create_app())
    accepted = client.post(
        "/api/data/upload",
        data={"workflow": "create_baseline", "approval_required": "false"},
        files={"file": ("historical.csv", _baseline_csv(), "text/csv")},
    )

    terminal = _wait(client, accepted.json()["status_url"])
    result = client.get(accepted.json()["baseline_result_url"]).json()

    assert terminal["baseline_activation_state"] == "active"
    assert result["candidate_model"]["status"] == "active"
    assert result["activation"]["approved_by"] == "automatic_policy"


def test_analysis_and_controlled_extension_require_an_active_baseline() -> None:
    client = TestClient(create_app())

    analyze = _post(client, "analyze_new_data", "current.csv")
    extend = _post(client, "extend_baseline", "additional-history.csv")

    assert analyze.status_code == 409
    assert analyze.json()["error_type"] == "active_behavioral_baseline_required"
    assert extend.status_code == 409
    assert extend.json()["error_type"] == "active_behavioral_baseline_required"


def test_controlled_extension_creates_a_child_candidate_without_sii(monkeypatch) -> None:
    client = TestClient(create_app())
    initial = _post(client, "create_baseline").json()
    _wait(client, initial["status_url"])
    initial_result = client.get(initial["baseline_result_url"]).json()
    parent = initial_result["candidate_model"]
    client.post(
        f"/api/data/baselines/candidates/{parent['model_id']}/approve",
        json={},
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("controlled learning must not invoke the SII runner")

    monkeypatch.setattr(upload_pipeline, "evaluate_sii", fail_if_called)
    extension = _post(client, "extend_baseline", "extension.csv")

    assert extension.status_code == 202
    queued = extension.json()
    terminal = _wait(client, queued["status_url"])
    result = client.get(queued["baseline_result_url"]).json()
    child = result["candidate_model"]
    assert terminal["sii_engine_invoked"] is False
    assert child["lineage"]["parent_model_id"] == parent["model_id"]
    assert child["lineage"]["parent_version"] == parent["version"]
    assert child["version"] == parent["version"] + 1


def test_exact_baseline_routes_survive_newer_activation_and_retry() -> None:
    client = TestClient(create_app())
    first = _post(client, "create_baseline", "baseline-a.csv", approval_required=False).json()
    first_terminal = _wait(client, first["status_url"])
    first_result = client.get(first["baseline_result_url"]).json()
    first_id = first_result["established_baseline_id"]

    second = _post(client, "create_baseline", "baseline-b.csv", approval_required=False).json()
    _wait(client, second["status_url"])
    second_result = client.get(second["baseline_result_url"]).json()
    second_id = second_result["established_baseline_id"]

    active = client.get("/api/data/baselines").json()
    exact_first = client.get(f"/api/data/baselines/{first_id}")
    exact_second = client.get(f"/api/data/baselines/{second_id}")
    retry = client.post(f"/api/data/upload/{first['job_id']}/retry")

    assert first_terminal["status"] == "COMPLETE"
    assert first_id != second_id
    assert active["active_baseline_id"] == second_id
    assert active["active_model"]["model_id"] == second_id
    assert exact_first.status_code == 200
    assert exact_first.json()["filename"] == "baseline-a.csv"
    assert exact_first.json()["candidate_model"]["status"] == "superseded"
    assert exact_second.status_code == 200
    assert exact_second.json()["filename"] == "baseline-b.csv"
    assert retry.status_code == 202
    assert retry.json()["retry_reused_existing_job"] is True
    assert client.get(first["baseline_result_url"]).json()["established_baseline_id"] == first_id


def test_baseline_state_and_exact_ids_are_isolated_between_portfolios() -> None:
    client = TestClient(create_app())
    north_headers = {"X-Neraium-Workspace-Id": "north-plant"}
    south_headers = {"X-Neraium-Workspace-Id": "south-plant"}

    north = _post(client, "create_baseline", "north.csv", headers=north_headers, approval_required=False).json()
    _wait(client, north["status_url"], headers=north_headers)
    north_result = client.get(north["baseline_result_url"], headers=north_headers).json()
    south = _post(client, "create_baseline", "south.csv", headers=south_headers, approval_required=False).json()
    _wait(client, south["status_url"], headers=south_headers)
    south_result = client.get(south["baseline_result_url"], headers=south_headers).json()

    north_id = north_result["established_baseline_id"]
    south_id = south_result["established_baseline_id"]
    assert north_result["portfolio_id"] == "north-plant"
    assert south_result["portfolio_id"] == "south-plant"
    assert client.get("/api/data/baselines", headers=north_headers).json()["active_baseline_id"] == north_id
    assert client.get("/api/data/baselines", headers=south_headers).json()["active_baseline_id"] == south_id
    assert client.get(f"/api/data/baselines/{north_id}", headers=north_headers).status_code == 200
    assert client.get(f"/api/data/baselines/{north_id}", headers=south_headers).status_code == 404
    assert client.get(f"/api/data/baselines/{south_id}", headers=south_headers).json()["filename"] == "south.csv"


def test_activation_failure_cannot_replace_the_previous_active_pointer(monkeypatch) -> None:
    client = TestClient(create_app())
    first = _post(client, "create_baseline", "active.csv", approval_required=False).json()
    _wait(client, first["status_url"])
    first_result = client.get(first["baseline_result_url"]).json()
    first_id = first_result["established_baseline_id"]

    second = _post(client, "create_baseline", "candidate.csv").json()
    _wait(client, second["status_url"])
    second_result = client.get(second["baseline_result_url"]).json()
    second_id = second_result["established_baseline_id"]
    original_write = behavioral_model_repository._write

    def fail_active_pointer(name: str, payload: dict) -> None:
        if name == "active":
            raise RuntimeError("simulated_active_pointer_failure")
        original_write(name, payload)

    monkeypatch.setattr(behavioral_model_repository, "_write", fail_active_pointer)
    with pytest.raises(RuntimeError, match="simulated_active_pointer_failure"):
        behavioral_model_repository.activate_candidate(second_id, approved_by="test")

    assert behavioral_model_repository.read_active_behavioral_model()["model_id"] == first_id
    persisted_second = behavioral_model_repository.read_baseline_result(second["job_id"])
    assert persisted_second["candidate_model"]["status"] == "awaiting_approval"
    assert persisted_second["activation"]["state"] == "awaiting_approval"


def _completed_comparison(baseline_result: dict, run_id: str, **overrides) -> dict:
    baseline = baseline_result["candidate_model"]
    source = baseline["source"]
    scope = current_dataset_scope()
    comparison_dataset_id = f"dataset-{run_id}"
    payload = {
        "job_id": run_id,
        "run_id": run_id,
        "upload_id": run_id,
        "dataset_id": comparison_dataset_id,
        "organization_id": scope.tenant_id,
        "portfolio_id": source["portfolio_id"],
        "system_id": source["system_id"],
        "baseline_id": baseline["model_id"],
        "baseline_dataset_id": source["dataset_id"],
        "comparison_dataset_id": comparison_dataset_id,
        "comparison_analysis_id": run_id,
        "analysis_run_id": run_id,
        "workflow": "analyze_new_data",
        "status": "COMPLETE",
        "processing_state": "complete",
        "sii_completed": True,
        "filename": f"{run_id}.csv",
        "completed_at": "2026-07-30T00:00:00+00:00",
        "active_baseline_reference": {"model_id": baseline["model_id"], "version": baseline["version"], "dataset_id": source["dataset_id"]},
        "conditions": [{"id": f"condition-{run_id}", "headline": "Real comparison condition"}],
    }
    payload.update(overrides)
    scoped = attach_dataset_scope(payload, scope=scope, dataset_id=payload.get("dataset_id"))
    return stamp_comparison_analysis_identity(scoped)


def _persist_comparison(baseline_result: dict, run_id: str) -> dict:
    result = _completed_comparison(baseline_result, run_id)
    write_upload_result(run_id, result)
    persist_completed_analysis(result)
    return result


def test_explicit_baseline_detail_is_baseline_only_until_an_exact_analysis_exists() -> None:
    client = TestClient(create_app())
    queued = _post(client, "create_baseline", "baseline-only.csv", approval_required=False).json()
    _wait(client, queued["status_url"])
    baseline_result = client.get(queued["baseline_result_url"]).json()
    baseline_id = baseline_result["established_baseline_id"]
    system_id = baseline_result["system_id"]

    baseline_response = client.get(f"/api/data/portfolios/default/baselines/{baseline_id}")

    assert baseline_response.status_code == 200
    baseline_payload = baseline_response.json()
    assert baseline_payload["baseline_id"] == baseline_id
    assert baseline_payload["portfolio_id"] == "default"
    assert baseline_payload["system_id"] == system_id
    assert baseline_payload["analysis_state"] == {"status": "empty", "count": 0, "analyses": []}
    assert "conditions" not in baseline_payload
    assert "findings" not in baseline_payload

    run_id = "comparison-run-a"
    _persist_comparison(baseline_result, run_id)

    linked_baseline = client.get(f"/api/data/portfolios/default/baselines/{baseline_id}").json()
    assert linked_baseline["analysis_state"]["status"] == "available"
    assert linked_baseline["analysis_state"]["count"] == 1
    assert linked_baseline["analysis_state"]["analyses"][0]["analysis_run_id"] == run_id

    analysis_response = client.get(
        f"/api/data/portfolios/default/systems/{system_id}/baselines/{baseline_id}/analyses/{run_id}"
    )
    assert analysis_response.status_code == 200
    assert analysis_response.json()["baseline_id"] == baseline_id
    assert analysis_response.json()["comparison_dataset_id"] == f"dataset-{run_id}"
    assert analysis_response.json()["comparison_dataset_id"] != baseline_result["dataset_id"]
    assert analysis_response.json()["comparison_analysis_id"] == run_id


def test_baseline_a_never_lists_or_serves_baseline_b_analysis() -> None:
    client = TestClient(create_app())
    first = _post(client, "create_baseline", "baseline-a.csv", approval_required=False).json()
    _wait(client, first["status_url"])
    baseline_a = client.get(first["baseline_result_url"]).json()
    second = _post(client, "create_baseline", "baseline-b.csv", approval_required=False).json()
    _wait(client, second["status_url"])
    baseline_b = client.get(second["baseline_result_url"]).json()

    run_id = "baseline-b-run"
    _persist_comparison(baseline_b, run_id)

    baseline_a_id = baseline_a["established_baseline_id"]
    baseline_b_id = baseline_b["established_baseline_id"]
    system_id = baseline_b["system_id"]
    opened_a = client.get(f"/api/data/portfolios/default/baselines/{baseline_a_id}").json()

    assert opened_a["analysis_state"] == {"status": "empty", "count": 0, "analyses": []}
    assert client.get(
        f"/api/data/portfolios/default/systems/{system_id}/baselines/{baseline_a_id}/analyses/{run_id}"
    ).status_code == 404
    assert client.get(
        f"/api/data/portfolios/default/systems/{system_id}/baselines/{baseline_b_id}/analyses/{run_id}"
    ).status_code == 200


def test_analysis_persistence_rejects_mismatched_baseline_and_scope() -> None:
    client = TestClient(create_app())
    queued = _post(client, "create_baseline", "baseline-a.csv", approval_required=False).json()
    _wait(client, queued["status_url"])
    baseline = client.get(queued["baseline_result_url"]).json()

    with pytest.raises(ValueError, match="analysis_baseline_reference_mismatch"):
        persist_completed_analysis(_completed_comparison(
            baseline,
            "mismatch-run",
            active_baseline_reference={"model_id": "another-baseline", "version": 1},
        ))

    baseline_id = baseline["established_baseline_id"]
    wrong_portfolio = client.get(
        f"/api/data/portfolios/another-portfolio/baselines/{baseline_id}",
        headers={"X-Neraium-Workspace-Id": "default"},
    )
    assert wrong_portfolio.status_code == 404


def test_comparison_upload_rejects_a_requested_baseline_from_another_identity() -> None:
    client = TestClient(create_app())
    queued = _post(client, "create_baseline", "baseline-a.csv", approval_required=False).json()
    _wait(client, queued["status_url"])
    baseline = client.get(queued["baseline_result_url"]).json()

    wrong_baseline = client.post(
        "/api/data/upload",
        data={
            "workflow": "analyze_new_data",
            "baseline_id": "another-baseline",
            "portfolio_id": "default",
            "system_id": baseline["system_id"],
        },
        files={"file": ("comparison.csv", _baseline_csv(), "text/csv")},
    )
    wrong_portfolio = client.post(
        "/api/data/upload",
        data={
            "workflow": "analyze_new_data",
            "baseline_id": baseline["established_baseline_id"],
            "portfolio_id": "another-portfolio",
            "system_id": baseline["system_id"],
        },
        files={"file": ("comparison.csv", _baseline_csv(), "text/csv")},
    )

    assert wrong_baseline.status_code == 409
    assert wrong_baseline.json()["error_type"] == "active_behavioral_baseline_required"
    assert wrong_portfolio.status_code == 409
    assert wrong_portfolio.json()["error_type"] == "analysis_portfolio_mismatch"



def test_completed_comparison_uses_distinct_dataset_and_analysis_ids_and_scopes_findings() -> None:
    client = TestClient(create_app())
    baseline_job = _post(client, "create_baseline", "baseline.csv", approval_required=False).json()
    _wait(client, baseline_job["status_url"])
    baseline = client.get(baseline_job["baseline_result_url"]).json()

    comparison_job = _post(client, "analyze_new_data", "comparison.csv").json()
    terminal = _wait(client, comparison_job["status_url"])
    assert terminal["status"] == "COMPLETE"
    result = client.get(f"/api/data/intake/{comparison_job['job_id']}/result").json()["result"]

    assert result["baseline_id"] == baseline["baselineId"]
    assert result["baseline_dataset_id"] == baseline["datasetId"]
    assert result["comparison_dataset_id"] == comparison_job["dataset_id"]
    assert result["comparison_dataset_id"] != result["baseline_dataset_id"]
    assert result["comparison_analysis_id"] == comparison_job["job_id"]
    assert result["analysis_run_id"] == comparison_job["job_id"]

    exact = client.get(f"/api/data/analyses/{result['comparison_analysis_id']}")
    findings = client.get(f"/api/data/analyses/{result['comparison_analysis_id']}/findings")
    assert exact.status_code == 200
    assert findings.status_code == 200
    assert findings.json()["comparisonAnalysisId"] == result["comparison_analysis_id"]
    for finding in findings.json()["findings"]:
        assert finding["comparison_analysis_id"] == result["comparison_analysis_id"]
        assert finding["baseline_id"] == result["baseline_id"]
        assert finding["comparison_dataset_id"] == result["comparison_dataset_id"]


def test_comparison_persistence_rejects_the_baseline_dataset_as_evaluation_data() -> None:
    client = TestClient(create_app())
    baseline_job = _post(client, "create_baseline", "baseline.csv", approval_required=False).json()
    _wait(client, baseline_job["status_url"])
    baseline = client.get(baseline_job["baseline_result_url"]).json()
    source_dataset_id = baseline["candidate_model"]["source"]["dataset_id"]
    invalid = _completed_comparison(
        baseline,
        "same-dataset-run",
        dataset_id=source_dataset_id,
        comparison_dataset_id=source_dataset_id,
    )

    with pytest.raises(ValueError, match="comparison_dataset_matches_baseline_dataset"):
        persist_completed_analysis(invalid)


def test_new_baseline_hides_stale_findings_until_its_own_comparison_exists() -> None:
    client = TestClient(create_app())
    first_job = _post(client, "create_baseline", "first.csv", approval_required=False).json()
    _wait(client, first_job["status_url"])
    first = client.get(first_job["baseline_result_url"]).json()
    _persist_comparison(first, "old-pumping-analysis")

    second_job = _post(client, "create_baseline", "second.csv", approval_required=False).json()
    _wait(client, second_job["status_url"])
    second = client.get(second_job["baseline_result_url"]).json()
    latest = client.get("/api/data/latest-upload?include_persisted=1").json()

    assert second["baselineId"] != first["baselineId"]
    assert latest["status"] == "baseline_ready"
    assert latest["processing_state"] == "waiting_for_comparison"
    assert latest["baseline_ready"]["baseline_id"] == second["baselineId"]
    assert latest["latest_result"] is None
    assert latest["current_upload"] is None
    assert latest["history"] == []


def test_active_comparison_identity_is_not_replaced_by_baseline_ready_fallback() -> None:
    client = TestClient(create_app())
    baseline_job = _post(client, "create_baseline", "baseline.csv", approval_required=False).json()
    _wait(client, baseline_job["status_url"])
    baseline = client.get(baseline_job["baseline_result_url"]).json()
    comparison_job_id = "comparison-processing-current"
    write_latest_upload_summary(
        comparison_job_id,
        {
            "dataset_id": "comparison-dataset-current",
            "workflow": "analyze_new_data",
            "active_baseline_model_id": baseline["baselineId"],
            "status": "PROCESSING",
            "processing_state": "processing",
            "message": "Evaluating comparison data.",
        },
    )

    latest = client.get("/api/data/latest-upload?include_persisted=1").json()

    assert latest["job_id"] == comparison_job_id
    assert latest["dataset_id"] == "comparison-dataset-current"
    assert latest["processing_state"] == "processing"
    assert latest["latest_result"] is None
    assert "baseline_ready" not in latest


def test_second_comparison_creates_a_separate_analysis_without_overwriting_baseline() -> None:
    client = TestClient(create_app())
    baseline_job = _post(client, "create_baseline", "baseline.csv", approval_required=False).json()
    _wait(client, baseline_job["status_url"])
    baseline = client.get(baseline_job["baseline_result_url"]).json()
    first = _persist_comparison(baseline, "comparison-one")
    second = _persist_comparison(baseline, "comparison-two")

    detail = client.get(f"/api/data/portfolios/default/baselines/{baseline['baselineId']}").json()
    assert detail["baseline_id"] == baseline["baselineId"]
    assert detail["dataset_id"] == baseline["datasetId"]
    assert detail["analysis_state"]["count"] == 2
    assert {item["analysis_run_id"] for item in detail["analysis_state"]["analyses"]} == {"comparison-one", "comparison-two"}
    assert first["comparison_dataset_id"] != second["comparison_dataset_id"]
    assert client.get("/api/data/analyses/comparison-one").status_code == 200
    assert client.get("/api/data/analyses/comparison-two").status_code == 200

def test_upload_creates_distinct_dataset_and_processing_job_ids() -> None:
    client = TestClient(create_app())

    accepted = _post(client, "create_baseline")

    assert accepted.status_code == 202
    payload = accepted.json()
    assert payload["job_id"]
    assert payload["dataset_id"]
    assert payload["job_id"] != payload["dataset_id"]
    terminal = _wait(client, payload["status_url"])
    result = client.get(payload["baseline_result_url"]).json()
    assert terminal["job_id"] == payload["job_id"]
    assert terminal["dataset_id"] == payload["dataset_id"]
    assert result["job_id"] == payload["job_id"]
    assert result["dataset_id"] == payload["dataset_id"]


def test_validation_exception_returns_structured_failure_with_original_exception(monkeypatch, caplog) -> None:
    def fail_quality(*args, **kwargs):
        raise RuntimeError("quality profiler exploded")

    monkeypatch.setattr(behavioral_baseline, "build_data_quality", fail_quality)
    client = TestClient(create_app())
    accepted = _post(client, "create_baseline").json()

    with caplog.at_level("ERROR"):
        terminal = _wait(client, accepted["status_url"])

    assert terminal["status"] == "FAILED"
    assert terminal["stage"] == "validation"
    assert terminal["errorCode"] == "validation_failed"
    assert terminal["userMessage"] == "The dataset did not pass validation. Check the file and try again."
    assert terminal["technicalMessage"] == "RuntimeError: quality profiler exploded"
    assert terminal["retryable"] is False
    assert terminal["datasetId"] == accepted["dataset_id"]
    assert terminal["jobId"] == accepted["job_id"]
    assert terminal["requestId"]
    record = next(record for record in caplog.records if "upload_queue_job_failed" in record.getMessage())
    assert record.exc_info is not None
    assert f"dataset_id={accepted['dataset_id']}" in record.getMessage()
    assert f"job_id={accepted['job_id']}" in record.getMessage()
    assert "stage=validation" in record.getMessage()
    assert "exception_type=RuntimeError" in record.getMessage()


def test_relationship_learning_exception_reports_actual_stage_and_is_retryable(monkeypatch) -> None:
    def fail_relationships(*args, **kwargs):
        raise ArithmeticError("singular relationship matrix")

    monkeypatch.setattr(behavioral_baseline, "_learn_relationship_graph", fail_relationships)
    client = TestClient(create_app())
    accepted = _post(client, "create_baseline").json()

    terminal = _wait(client, accepted["status_url"])

    assert terminal["status"] == "FAILED"
    assert terminal["stage"] == "relationship_learning"
    assert terminal["errorCode"] == "relationship_learning_failed"
    assert terminal["technicalMessage"] == "ArithmeticError: singular relationship matrix"
    assert terminal["retryable"] is True
    assert terminal["file_stored"] is True
    assert terminal["transfer_succeeded"] is True


def test_worker_waits_for_a_delayed_baseline_result_record(monkeypatch) -> None:
    original_read = upload_jobs.read_baseline_result
    reads = {"count": 0}

    def delayed_read(job_id: str):
        reads["count"] += 1
        if reads["count"] <= 2:
            return None
        return original_read(job_id)

    monkeypatch.setattr(upload_jobs, "read_baseline_result", delayed_read)
    client = TestClient(create_app())
    accepted = _post(client, "create_baseline").json()

    terminal = _wait(client, accepted["status_url"])

    assert terminal["status"] == "COMPLETE"
    assert terminal["result_available"] is True
    assert reads["count"] >= 3
    assert client.get(accepted["baseline_result_url"]).status_code == 200


def test_terminal_success_is_rejected_when_result_cannot_be_retrieved(monkeypatch) -> None:
    monkeypatch.setattr(upload_jobs, "read_baseline_result", lambda _job_id: None)
    client = TestClient(create_app())
    accepted = _post(client, "create_baseline").json()

    terminal = _wait(client, accepted["status_url"])

    assert terminal["status"] == "FAILED"
    assert terminal["job_state"] == "failed"
    assert terminal["stage"] == "baseline_creation"
    assert terminal["errorCode"] == "result_persistence_failed"
    assert terminal["result_available"] is False
    assert terminal["technicalMessage"].startswith("ResultPersistenceError:")


def test_retry_processing_reuses_the_uploaded_dataset(monkeypatch) -> None:
    original_learn = behavioral_baseline._learn_relationship_graph
    attempts = {"count": 0}

    def fail_once(*args, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("temporary relationship learner outage")
        return original_learn(*args, **kwargs)

    monkeypatch.setattr(behavioral_baseline, "_learn_relationship_graph", fail_once)
    client = TestClient(create_app())
    accepted = _post(client, "create_baseline").json()
    failed = _wait(client, accepted["status_url"])
    assert failed["status"] == "FAILED"

    retried_response = client.post(f"/api/data/upload/{accepted['job_id']}/retry")

    assert retried_response.status_code == 202
    retried = retried_response.json()
    assert retried["job_id"] == accepted["job_id"]
    assert retried["dataset_id"] == accepted["dataset_id"]
    assert retried["file_stored"] is True
    terminal = _wait(client, retried["status_url"])
    assert terminal["status"] == "COMPLETE"
    assert terminal["dataset_id"] == accepted["dataset_id"]
    assert attempts["count"] == 2
