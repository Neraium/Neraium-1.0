from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import create_app
from app.services.baseline_analysis_repository import persist_completed_analysis, stamp_comparison_analysis_identity
from app.services.dataset_scope import attach_dataset_scope, current_dataset_scope
from app.services.evidence_package import EvidencePackage, PackageStatus, ReferenceLevel, build_evidence_package
from app.services.upload_state_repository import write_upload_result


def _comparison(run_id: str = "analysis-ep-001") -> dict:
    scope = current_dataset_scope()
    result = {
        "job_id": run_id, "run_id": run_id, "dataset_id": "comparison-dataset-001",
        "organization_id": scope.tenant_id, "portfolio_id": scope.workspace_id, "system_id": scope.workspace_id,
        "baseline_id": "baseline-001", "baseline_dataset_id": "baseline-dataset-001",
        "comparison_dataset_id": "comparison-dataset-001", "comparison_analysis_id": run_id,
        "analysis_run_id": run_id, "workflow": "analyze_new_data", "status": "COMPLETE",
        "processing_state": "complete", "sii_completed": True, "completed_at": "2026-08-03T12:00:00+00:00",
        "active_baseline_reference": {"model_id": "baseline-001", "version": 3, "dataset_id": "baseline-dataset-001"},
        "conditions": [{"id": "condition-001", "headline": "Pump response weakening in Pumping System", "system": "Pumping System"}],
        "baseline_analysis": {"baseline_model_id": "baseline-001", "relationship_drift": [{
            "left": "pump_power_kw", "right": "chw_flow_gpm", "direction": "weakened",
            "baseline_correlation": 0.998290, "recent_correlation": 0.690739,
            "correlation_delta": 0.307551, "baseline_sample_count": 672, "recent_sample_count": 672,
            "persistence_score": 1.0,
        }]},
        "replay_frame_count": 120,
    }
    return stamp_comparison_analysis_identity(attach_dataset_scope(result, scope=scope, dataset_id=result["dataset_id"]))


def test_v1_package_preserves_comparison_and_has_deterministic_evidence() -> None:
    first = build_evidence_package(_comparison())
    second = build_evidence_package(_comparison())

    assert first == second
    assert first["id"] == second["id"]
    assert first["package_number"].startswith("EP-ANALYSIS-")
    assert first["status"] == "active"
    assert first["comparison_reference"]["reference_level"] == "matched_historical_baseline"
    assert first["baseline_id"] == "baseline-001"
    assert first["comparison_dataset_id"] == "comparison-dataset-001"
    assert first["primary_relationship"] == {
        **first["primary_relationship"], "relationship_label": "pump_power_kw / chw_flow_gpm",
        "change_direction": "weakened", "baseline_strength": 0.998290,
        "comparison_strength": 0.690739, "absolute_change": 0.307551,
        "baseline_sample_count": 672, "comparison_sample_count": 672,
    }
    assert [item["id"] for item in first["supporting_evidence"]] == [
        "ev-baseline-strength", "ev-comparison-strength", "ev-absolute-change", "ev-baseline-samples",
        "ev-comparison-samples", "ev-persistence", "ev-baseline-identity", "ev-replay",
    ]
    assert all(value["level"] == "unknown" for value in first["confidence"].values())
    assert first["limitations"] == []
    assert first["hypotheses"] == []


def test_package_endpoints_are_idempotent_and_tenant_scoped() -> None:
    client = TestClient(create_app())
    result = _comparison()
    write_upload_result(result["job_id"], result)
    persist_completed_analysis(result)

    analysis_response = client.get(f"/api/data/analyses/{result['job_id']}")
    assert analysis_response.status_code == 200
    package = analysis_response.json()["evidence_package"]
    before_revision = package["revision"]
    direct = client.get(f"/api/data/analyses/{result['job_id']}/evidence-package")
    exact = client.get(f"/api/data/evidence-packages/{package['id']}")
    repeated = client.get(f"/api/data/analyses/{result['job_id']}/evidence-package")
    assert direct.status_code == exact.status_code == repeated.status_code == 200
    assert direct.json() == exact.json() == repeated.json() == package
    assert repeated.json()["revision"] == before_revision == 1
    assert client.get(
        f"/api/data/evidence-packages/{package['id']}", headers={"X-Neraium-Workspace-Id": "foreign-portfolio"}
    ).status_code == 404


def test_invalid_package_enums_are_rejected() -> None:
    package = build_evidence_package(_comparison())
    package["status"] = "invented_status"
    with pytest.raises(ValidationError):
        EvidencePackage.model_validate(package)
    with pytest.raises(ValueError):
        PackageStatus("invented_status")
    with pytest.raises(ValueError):
        ReferenceLevel("invented_reference")


def test_internal_window_legacy_change_does_not_claim_exact_baseline() -> None:
    result = _comparison("legacy-internal-window")
    result["baseline_analysis"].pop("baseline_model_id")

    assert build_evidence_package(result) is None


def test_mismatched_persisted_baseline_model_does_not_create_package() -> None:
    result = _comparison("mismatched-baseline")
    result["baseline_analysis"]["baseline_model_id"] = "baseline-other"

    assert build_evidence_package(result) is None


def test_missing_persisted_timestamp_is_deterministically_unsupported() -> None:
    result = _comparison("legacy-without-timestamp")
    result.pop("completed_at")
    result.pop("last_processed_at", None)

    assert build_evidence_package(result) is None
    assert build_evidence_package(result) is None


def test_package_organization_comes_from_dataset_scope() -> None:
    result = _comparison("scoped-package")
    result["dataset_scope"]["tenant_id"] = "tenant-from-scope"
    result["dataset_scope"]["user_id"] = "tenant-from-scope"
    result["organization_id"] = "tenant-from-scope"

    package = build_evidence_package(result)

    assert package is not None
    assert package["organization_id"] == "tenant-from-scope"
    assert package["id"] == build_evidence_package(result)["id"]
