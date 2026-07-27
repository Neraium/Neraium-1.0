from __future__ import annotations

import copy
import time

import pytest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import create_app
from app.engine.sii_engine import evaluate_sii as real_evaluate_sii
from app.services import upload_jobs, upload_pipeline
from app.services.baseline_contracts import (
    BASELINE_PROGRESS_STAGES,
    JOB_TYPE_BASELINE_CONSTRUCTION,
    JOB_TYPE_MONITORING_ANALYSIS,
    MONITORING_PROGRESS_STATE_MACHINE,
    PROHIBITED_BASELINE_OUTPUT_KEYS,
    assert_baseline_progress_contract,
    baseline_copy_is_safe,
    baseline_progress_payload,
    prohibited_keys_present,
)
from app.services.behavioral_model_repository import (
    activate_candidate,
    persist_candidate,
    read_active_behavioral_model,
    read_baseline_result,
)
from app.services.evidence_store import read_evidence_run


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


def _wait(client: TestClient, status_url: str) -> dict:
    deadline = time.time() + 15
    last = {}
    while time.time() < deadline:
        response = client.get(status_url)
        assert response.status_code == 200
        last = response.json()
        if last.get("status") in {"COMPLETE", "FAILED"}:
            return last
        time.sleep(0.05)
    raise AssertionError(f"baseline job did not complete: {last}")


def _post(client: TestClient, workflow: str, filename: str = "historical.csv"):
    return client.post(
        "/api/data/upload",
        data={"workflow": workflow},
        files={"file": (filename, _baseline_csv(), "text/csv")},
    )


def test_create_baseline_never_invokes_sii_or_persists_detection_evidence(monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("the full SII runner must not be invoked for a baseline upload")

    monkeypatch.setattr(upload_pipeline, "evaluate_sii", fail_if_called)
    monkeypatch.setattr(upload_jobs, "run_structural_analysis_pipeline", fail_if_called)
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
    assert result["result_type"] == "baseline_suitability_report"
    assert result["report_title"] == "Baseline Suitability Report"
    assert result["candidate_behavioral_digital_model"] == result["candidate_model"]
    assert result["baseline_suitability_report"] == result["baseline_suitability"]
    assert "analysis_result" not in result
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


def test_baseline_jobs_emit_only_the_baseline_progress_contract(monkeypatch) -> None:
    observed: list[dict] = []
    real_write_job = upload_jobs.write_job

    def capture_write(*args):
        real_write_job(*args)
        job_id = str(args[0] if len(args) == 2 else (args[0] or {}).get("job_id") or "")
        snapshot = upload_jobs.read_job(job_id)
        if snapshot and snapshot.get("workflow") == "create_baseline":
            observed.append(copy.deepcopy(snapshot))

    monkeypatch.setattr(upload_jobs, "write_job", capture_write)
    client = TestClient(create_app())
    queued = _post(client, "create_baseline").json()
    terminal = _wait(client, queued["status_url"])

    assert observed
    assert terminal["baseline_stage"] == "ready"
    assert terminal["baseline_stage_order"] == list(BASELINE_PROGRESS_STAGES)
    observed_learn_steps: list[str] = []
    for payload in observed:
        step = payload.get("baseline_step")
        if payload.get("baseline_stage") == "learn" and step != (observed_learn_steps[-1] if observed_learn_steps else None):
            observed_learn_steps.append(step)
    assert observed_learn_steps == [
        "validating_historical_coverage",
        "assessing_data_quality",
        "checking_sensor_suitability",
        "identifying_operating_modes",
        "learning_signal_behavior",
        "learning_relationships",
        "building_behavioral_graph",
        "estimating_empirical_thresholds",
        "fitting_expected_behavior_models",
        "creating_candidate_baseline",
    ]
    for payload in [queued, *observed, terminal]:
        assert_baseline_progress_contract(payload)
        assert payload["job_type"] == JOB_TYPE_BASELINE_CONSTRUCTION
        assert payload["baseline_stage"] in {*BASELINE_PROGRESS_STAGES, "failed", "cancelled"}
        assert not ({
            "analysis_state", "contract_stage", "contract_progress", "contract_label",
            "monitoring_stage", "monitoring_step", "propagation_stage",
            "propagation_progress", "propagation_label",
        } & set(payload))
        for key in ("baseline_stage_label", "baseline_step_label", "progress_label", "message"):
            assert baseline_copy_is_safe(payload.get(key)), (key, payload.get(key))


def test_baseline_progress_normalization_is_idempotent() -> None:
    first = baseline_progress_payload("baseline_data_quality", progress=60)
    normalized = baseline_progress_payload(first["processing_state"], progress=first["progress"])

    assert normalized["baseline_stage"] == "learn"
    assert normalized["baseline_step"] == "assessing_data_quality"
    assert normalized["baseline_step_label"] == "Assessing data quality"


def test_monitoring_job_keeps_full_sii_workflow_and_loads_active_baseline(monkeypatch) -> None:
    client = TestClient(create_app())
    baseline_job = _post(client, "create_baseline").json()
    _wait(client, baseline_job["status_url"])
    baseline_result = client.get(baseline_job["baseline_result_url"]).json()
    candidate = baseline_result["candidate_model"]
    approved = client.post(
        f"/api/data/baselines/candidates/{candidate['model_id']}/approve",
        json={},
    )
    assert approved.status_code == 200

    calls: list[dict] = []

    def counted_evaluate_sii(**kwargs):
        calls.append(dict(kwargs))
        return real_evaluate_sii(**kwargs)

    monkeypatch.setattr(upload_pipeline, "evaluate_sii", counted_evaluate_sii)
    accepted = _post(client, "analyze_new_data", "current.csv")
    assert accepted.status_code == 202
    queued = accepted.json()
    assert queued["job_type"] == JOB_TYPE_MONITORING_ANALYSIS
    assert queued["progress_state_machine"] == MONITORING_PROGRESS_STATE_MACHINE
    assert not ({"baseline_stage", "baseline_step", "baseline_learn_steps"} & set(queued))

    terminal = _wait(client, queued["status_url"])
    assert len(calls) == 1
    assert calls[0]["config"]["active_baseline_loaded"] is True
    assert calls[0]["config"]["active_behavioral_baseline"]["model_id"] == candidate["model_id"]
    assert terminal["status"] == "COMPLETE"
    assert terminal["sii_completed"] is True
    assert terminal["analysis_state"] == "completed"
    assert terminal["job_type"] == JOB_TYPE_MONITORING_ANALYSIS
    assert terminal["progress_state_machine"] == MONITORING_PROGRESS_STATE_MACHINE
    assert terminal["evidence_persisted"] is True
    assert not ({"baseline_stage", "baseline_step", "baseline_learn_steps"} & set(terminal))


def test_candidate_cannot_activate_before_completion_or_required_approval() -> None:
    incomplete_model = {
        "model_id": "incomplete-candidate",
        "version": 1,
        "status": "awaiting_approval",
        "workflow": "create_baseline",
        "construction": {"state": "processing"},
        "source": {"job_id": "incomplete-job"},
        "activation": {"eligible": True, "approval_required": True},
    }
    incomplete_result = {
        "job_id": "incomplete-job",
        "status": "PROCESSING",
        "candidate_model": incomplete_model,
    }
    with pytest.raises(ValueError, match="candidate_not_completed"):
        persist_candidate(incomplete_model, incomplete_result, activate=False)
    assert read_active_behavioral_model() is None

    client = TestClient(create_app())
    queued = _post(client, "create_baseline").json()
    _wait(client, queued["status_url"])
    candidate = client.get(queued["baseline_result_url"]).json()["candidate_model"]
    with pytest.raises(ValueError, match="candidate_approval_required"):
        activate_candidate(candidate["model_id"], approved_by="automatic_policy")
    with pytest.raises(ValueError, match="candidate_approval_required"):
        activate_candidate(candidate["model_id"], approved_by="")
    assert read_active_behavioral_model() is None

    approved = client.post(
        f"/api/data/baselines/candidates/{candidate['model_id']}/approve",
        json={},
    )
    assert approved.status_code == 200
    assert approved.json()["active_model"]["status"] == "active"
