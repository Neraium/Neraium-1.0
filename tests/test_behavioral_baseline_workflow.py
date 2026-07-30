from __future__ import annotations

import time

import pytest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import create_app
from app.services import behavioral_model_repository, upload_pipeline
from app.services.baseline_analysis_repository import persist_completed_analysis
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
from app.services.upload_state_repository import write_upload_result


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
    payload = {
        "job_id": run_id,
        "run_id": run_id,
        "upload_id": run_id,
        "dataset_id": run_id,
        "organization_id": scope.tenant_id,
        "portfolio_id": source["portfolio_id"],
        "system_id": source["system_id"],
        "baseline_id": baseline["model_id"],
        "comparison_dataset_id": run_id,
        "analysis_run_id": run_id,
        "workflow": "analyze_new_data",
        "status": "COMPLETE",
        "processing_state": "complete",
        "sii_completed": True,
        "filename": f"{run_id}.csv",
        "completed_at": "2026-07-30T00:00:00+00:00",
        "active_baseline_reference": {"model_id": baseline["model_id"], "version": baseline["version"]},
        "conditions": [{"id": f"condition-{run_id}", "headline": "Real comparison condition"}],
    }
    payload.update(overrides)
    return attach_dataset_scope(payload, scope=scope, dataset_id=payload.get("dataset_id"))


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
    assert analysis_response.json()["comparison_dataset_id"] == run_id


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
