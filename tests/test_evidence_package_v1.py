from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import create_app
from app.services.baseline_analysis_repository import persist_completed_analysis, stamp_comparison_analysis_identity
from app.services.dataset_scope import attach_dataset_scope, current_dataset_scope
from app.services.evidence_package import (
    ComparabilityLevel,
    ConfidenceLevel,
    EvidencePackage,
    LimitationCategory,
    LimitationSeverity,
    LimitationStatus,
    LifecycleActor,
    LifecycleEventType,
    LifecycleStatus,
    OperatingStateType,
    PackageStatus,
    ReferenceLevel,
    TimelineEventType,
    TransitionDirection,
    build_evidence_package,
)
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


def _with_operating_context(result: dict) -> dict:
    result["operating_context_inputs"] = {
        "schema_version": "operating-context-input-v1",
        "source": "analysis_metadata",
        "baseline": {
            "process_demand": {"canonical_role": "process_demand", "source_variable": "cooling_demand_tons", "unit": "tons", "count": 672, "mean": 311.2, "min": 164.1, "max": 507.8, "source": "baseline_model"},
            "control_command": {"canonical_role": "control_command", "source_variable": "valve_position_pct", "unit": "%", "count": 672, "mean": 67.01, "min": 45.1, "max": 93.0, "source": "baseline_model"},
        },
        "comparison": {
            "process_demand": {"canonical_role": "process_demand", "source_variable": "cooling_demand_tons", "unit": "tons", "count": 672, "mean": 311.2, "min": 164.1, "max": 507.8, "early_median": 205.0, "late_median": 207.0, "source": "telemetry"},
            "control_command": {"canonical_role": "control_command", "source_variable": "valve_position_pct", "unit": "%", "count": 672, "mean": 67.01, "min": 45.1, "max": 93.0, "early_median": 52.0, "late_median": 52.5, "source": "telemetry"},
        },
        "windows": {
            "baseline": {"start": "2026-06-01T00:00:00Z", "end": "2026-06-07T23:45:00Z"},
            "comparison": {"start": "2026-06-15T00:00:00Z", "end": "2026-06-21T23:45:00Z"},
        },
    }
    return result


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
    with pytest.raises(ValueError):
        OperatingStateType("invented_state")
    with pytest.raises(ValueError):
        TransitionDirection("invented_direction")
    with pytest.raises(ValueError):
        ComparabilityLevel("invented_level")
    with pytest.raises(ValueError):
        ConfidenceLevel("invented_confidence")
    package = build_evidence_package(_comparison())
    package["timeline"][0]["event_type"] = "causal_precursor"
    with pytest.raises(ValidationError):
        EvidencePackage.model_validate(package)
    with pytest.raises(ValueError):
        TimelineEventType("causal_precursor")
    with pytest.raises(ValueError):
        LifecycleStatus("CLOSED")
    with pytest.raises(ValueError):
        LifecycleEventType("investigation_started")
    with pytest.raises(ValueError):
        LifecycleActor("technician")


def test_lifecycle_defaults_open_and_is_deterministic() -> None:
    first = build_evidence_package(_comparison("lifecycle-open"))
    second = build_evidence_package(_comparison("lifecycle-open"))

    assert first == second
    assert first["revision"] == 1
    assert first["lifecycle"] == {
        "status": "OPEN",
        "events": [{
            "event_id": first["lifecycle"]["events"][0]["event_id"],
            "timestamp": "2026-08-03T12:00:00Z",
            "actor": "system",
            "event_type": "package_created",
            "reason": "Evidence Package created from the completed baseline comparison.",
            "metadata": {},
        }],
        "provenance": {
            "schema_version": "evidence-package-lifecycle-v1",
            "source": "lifecycle_event_store",
        },
    }


def test_lifecycle_transitions_are_append_only_and_do_not_rewrite_evidence() -> None:
    client = TestClient(create_app())
    result = _comparison("lifecycle-transitions")
    write_upload_result(result["job_id"], result)
    persist_completed_analysis(result)
    package = client.get(f"/api/data/analyses/{result['job_id']}/evidence-package").json()
    analytical = {key: value for key, value in package.items() if key != "lifecycle"}

    acknowledged = client.post(
        f"/api/data/evidence-packages/{package['id']}/lifecycle-events",
        json={
            "timestamp": "2026-08-03T13:00:00+00:00",
            "actor": "user",
            "event_type": "package_acknowledged",
            "reason": "Accepted for investigation.",
            "metadata": {"source": "evidence_package"},
        },
    )
    assert acknowledged.status_code == 200
    assert acknowledged.json()["lifecycle"]["status"] == "ACKNOWLEDGED"
    assert [event["event_type"] for event in acknowledged.json()["lifecycle"]["events"]] == [
        "package_created", "package_acknowledged",
    ]
    persist_completed_analysis(result)
    assert client.get(f"/api/data/evidence-packages/{package['id']}").json()["lifecycle"] == acknowledged.json()["lifecycle"]

    resolved = client.post(
        f"/api/data/evidence-packages/{package['id']}/lifecycle-events",
        json={
            "timestamp": "2026-08-03T14:00:00Z",
            "actor": "unknown",
            "event_type": "package_resolved",
            "reason": "Operational resolution recorded.",
            "metadata": {},
        },
    )
    assert resolved.status_code == 200
    payload = resolved.json()
    assert payload["lifecycle"]["status"] == "RESOLVED"
    assert len(payload["lifecycle"]["events"]) == 3
    assert {key: value for key, value in payload.items() if key != "lifecycle"} == analytical
    assert payload["id"] == package["id"]
    assert payload["revision"] == package["revision"] == 1

    repeated = client.get(f"/api/data/evidence-packages/{package['id']}")
    analysis = client.get(f"/api/data/analyses/{result['job_id']}")
    assert repeated.json() == payload
    assert analysis.json()["evidence_package"] == payload


def test_lifecycle_rejects_invalid_transitions_and_is_tenant_scoped() -> None:
    client = TestClient(create_app())
    result = _comparison("lifecycle-invalid")
    write_upload_result(result["job_id"], result)
    persist_completed_analysis(result)
    package = client.get(f"/api/data/analyses/{result['job_id']}/evidence-package").json()
    endpoint = f"/api/data/evidence-packages/{package['id']}/lifecycle-events"
    request = {
        "timestamp": "2026-08-03T13:00:00Z", "actor": "user",
        "event_type": "package_resolved", "reason": "Out of order.", "metadata": {},
    }
    assert client.post(endpoint, json=request).status_code == 409
    request["event_type"] = "closed"
    assert client.post(endpoint, json=request).status_code == 422
    request["event_type"] = "package_acknowledged"
    assert client.post(endpoint, json=request, headers={"X-Neraium-Workspace-Id": "foreign"}).status_code == 404
    assert client.get(endpoint.removesuffix("/lifecycle-events")).json()["lifecycle"]["status"] == "OPEN"


def test_legacy_package_without_lifecycle_remains_valid() -> None:
    package = build_evidence_package(_comparison("lifecycle-legacy"))
    package.pop("lifecycle")
    validated = EvidencePackage.model_validate(package).model_dump(mode="json")
    assert validated["id"] == package["id"]
    assert validated["lifecycle"] is None


def test_timeline_uses_deterministic_persisted_temporal_evidence() -> None:
    result = _with_operating_context(_comparison("timeline-supported"))
    result["conditions"][0]["first_supported_at"] = "2026-06-18T04:30:00-04:00"
    edge = result["baseline_analysis"]["relationship_drift"][0]
    edge.update({"confidence_level": "high", "confidence_score": 0.91})

    first = build_evidence_package(result)
    second = build_evidence_package(result)

    assert first == second
    assert first["schema_version"] == "evidence-package-v1"
    assert first["id"] == second["id"]
    assert first["first_supported_at"] == "2026-06-18T08:30:00Z"
    assert [event["event_type"] for event in first["timeline"]] == [
        "comparison_started", "earliest_supported_deviation", "behavior_persisted", "comparison_completed",
    ]
    assert [event["sequence"] for event in first["timeline"]] == [1, 2, 3, 4]
    assert [event["occurred_at"] for event in first["timeline"]] == sorted(
        event["occurred_at"] for event in first["timeline"]
    )
    earliest = first["timeline"][1]
    assert earliest["is_earliest_supported"] is True
    assert earliest["confidence_level"] == "high"
    assert earliest["evidence_refs"] == [
        "ev-absolute-change", "ev-comparison-samples", "ev-persistence", "ev-context-comparison-window",
    ]
    evidence_ids = {item["id"] for item in first["supporting_evidence"]}
    assert all(set(event["evidence_refs"]) <= evidence_ids for event in first["timeline"])


def test_timeline_explicitly_records_unknown_earliest_support() -> None:
    package = build_evidence_package(_with_operating_context(_comparison("timeline-unknown")))

    assert package["first_supported_at"] is None
    unknown = next(event for event in package["timeline"] if event["event_type"] == "unknown")
    assert unknown["occurred_at"] == "2026-08-03T12:00:00Z"
    assert unknown["is_earliest_supported"] is False
    assert unknown["evidence_refs"] == []
    assert "No persisted comparison evidence" in unknown["summary"]
    assert not any(event["event_type"] == "earliest_supported_deviation" for event in package["timeline"])


@pytest.mark.parametrize("onset", ["2026-06-14T23:59:59Z", "2026-06-22T00:00:00Z", "not-a-timestamp"])
def test_timeline_does_not_substitute_onset_outside_comparison_window(onset: str) -> None:
    result = _with_operating_context(_comparison(f"timeline-window-{onset}"))
    result["conditions"][0]["first_detected_at"] = onset

    package = build_evidence_package(result)

    assert package["first_supported_at"] is None
    assert any(event["event_type"] == "unknown" for event in package["timeline"])
    assert not any(event["event_type"] == "earliest_supported_deviation" for event in package["timeline"])


def test_legacy_package_without_temporal_onset_remains_valid() -> None:
    package = build_evidence_package(_comparison("timeline-legacy"))
    package["timeline"] = []

    validated = EvidencePackage.model_validate(package).model_dump(mode="json")

    assert validated["timeline"] == []
    assert validated["id"] == package["id"]


def test_multidimensional_confidence_preserves_supported_existing_assessments() -> None:
    result = _comparison("multidimensional-supported")
    edge = result["baseline_analysis"]["relationship_drift"][0]
    edge.update({"confidence_level": "high", "confidence_score": 0.91})
    result["data_quality"] = {
        "readiness": "ready", "reliability_rating": "strong", "reliability_score": 96,
        "data_confidence": {"rating": "high", "summary": "Telemetry passed existing quality checks.", "reasons": []},
    }
    result["telemetry_signal_catalog"] = {
        "pump_power_kw": {"source_column": "pump_power_kw", "canonical_role": "electrical_power"},
        "chw_flow_gpm": {"source_column": "chw_flow_gpm", "canonical_role": "process_rate"},
    }

    confidence = build_evidence_package(result)["confidence"]

    assert confidence["finding_confidence"] == {
        **confidence["finding_confidence"], "level": "high", "score": 0.91,
        "method": "preserved_relationship_confidence_v1",
    }
    assert confidence["data_quality_confidence"] == {
        **confidence["data_quality_confidence"], "level": "high", "score": 96.0,
        "method": "preserved_data_quality_assessment_v1",
    }
    assert confidence["mapping_confidence"]["level"] == "medium"
    assert confidence["mapping_confidence"]["score"] is None
    assert "physical correctness has not been independently validated" in confidence["mapping_confidence"]["reason"]
    assert confidence["physical_consistency_confidence"]["level"] == "unknown"
    assert confidence["physical_consistency_confidence"]["reason"] == "Physics consistency engine not implemented."


def test_mapping_ambiguity_decreases_only_mapping_confidence() -> None:
    result = _comparison("mapping-ambiguous")
    result["telemetry_signal_catalog"] = {
        "pump_power_kw": {"source_column": "pump_power_kw", "canonical_role": "electrical_power"},
        "backup_power_kw": {"source_column": "backup_power_kw", "canonical_role": "electrical_power"},
        "chw_flow_gpm": {"source_column": "chw_flow_gpm", "canonical_role": "process_rate"},
    }

    confidence = build_evidence_package(result)["confidence"]

    assert confidence["mapping_confidence"]["level"] == "low"
    assert "electrical_power" in confidence["mapping_confidence"]["reason"]
    assert confidence["finding_confidence"]["level"] == "unknown"


def test_missing_quality_evidence_remains_unknown() -> None:
    confidence = build_evidence_package(_comparison("missing-quality"))["confidence"]

    assert confidence["data_quality_confidence"]["level"] == "unknown"
    assert confidence["data_quality_confidence"]["score"] is None


def test_operating_comparability_does_not_become_state_confidence() -> None:
    confidence = build_evidence_package(_with_operating_context(_comparison("state-unknown")))["confidence"]

    assert confidence["operating_state_confidence"]["level"] == "unknown"
    assert confidence["operating_state_confidence"]["score"] is None
    assert "comparability is available" in confidence["operating_state_confidence"]["reason"]


def test_operating_context_is_deterministic_and_preserves_only_mapped_facts() -> None:
    result = _with_operating_context(_comparison("analysis-context-001"))
    original_id = build_evidence_package(_comparison("analysis-context-001"))["id"]

    first = build_evidence_package(result)
    second = build_evidence_package(result)

    assert first == second
    assert first["id"] == original_id
    context = first["operating_context"]
    assert context["schema_version"] == "operating-context-v1"
    assert context["load_context"] == {
        **context["load_context"], "canonical_role": "process_demand", "baseline_mean": 311.2,
        "comparison_mean": 311.2, "baseline_range": {"min": 164.1, "max": 507.8},
        "comparison_range": {"min": 164.1, "max": 507.8},
    }
    assert context["control_context"][0]["baseline_mean"] == 67.01
    assert context["control_context"][0]["comparison_mean"] == 67.01
    assert context["equipment_configuration"] == []
    assert context["environmental_context"] == []
    assert context["comparison_state"]["state_confidence"] == {
        **context["comparison_state"]["state_confidence"], "level": "unknown", "score": None,
    }
    assert context["transition_context"]["direction"] == "stable"
    assert context["comparability"]["level"] == "high"
    assert context["comparability"]["score"] == 1.0
    assert [item["id"] for item in first["supporting_evidence"][-6:]] == [
        "ev-context-baseline-demand-range", "ev-context-comparison-demand-range", "ev-context-control-01",
        "ev-context-baseline-window", "ev-context-comparison-window", "ev-context-comparability",
    ]


def test_operating_context_comparability_is_unknown_without_canonical_demand() -> None:
    result = _with_operating_context(_comparison("analysis-context-missing"))
    result["operating_context_inputs"]["baseline"].pop("process_demand")

    context = build_evidence_package(result)["operating_context"]

    assert context["load_context"] is None
    assert context["comparability"]["level"] == "unknown"
    assert context["comparability"]["score"] is None


@pytest.mark.parametrize(
    ("baseline_unit", "comparison_unit"),
    [("tons", "kW"), ("tons", None)],
)
def test_process_demand_comparability_is_unknown_for_incompatible_units(
    baseline_unit: str | None, comparison_unit: str | None,
) -> None:
    result = _with_operating_context(_comparison(f"analysis-unit-{comparison_unit}"))
    result["operating_context_inputs"]["baseline"]["process_demand"]["unit"] = baseline_unit
    result["operating_context_inputs"]["comparison"]["process_demand"]["unit"] = comparison_unit

    context = build_evidence_package(result)["operating_context"]

    assert context["load_context"]["unit"] is None
    assert context["load_context"]["baseline_unit"] == baseline_unit
    assert context["load_context"]["comparison_unit"] == comparison_unit
    assert context["comparability"]["level"] == "unknown"
    assert context["comparability"]["score"] is None


def test_incompatible_control_units_are_excluded_from_comparability() -> None:
    result = _with_operating_context(_comparison("analysis-control-units"))
    result["operating_context_inputs"]["comparison"]["control_command"]["unit"] = "V"

    first = build_evidence_package(result)
    second = build_evidence_package(result)

    assert first == second
    assert first["operating_context"]["control_context"][0]["unit"] is None
    assert first["operating_context"]["comparability"]["level"] == "high"
    assert first["operating_context"]["comparability"]["score"] == 1.0
    assert "control_command" in first["operating_context"]["comparability"]["unavailable_dimensions"]


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


def test_unknown_limitation_evidence_does_not_create_a_limitation() -> None:
    package = build_evidence_package(_comparison("limitations-unknown"))

    assert package["limitations"] == []


def test_explicit_missing_operating_context_creates_supported_limitation() -> None:
    result = _comparison("limitations-context")
    result["operating_context_inputs"] = None

    package = build_evidence_package(result)

    limitation = package["limitations"][0]
    assert limitation["category"] == "missing_operating_state_evidence"
    assert limitation["severity"] == "unknown"
    assert limitation["supporting_evidence_refs"] == ["ev-operating-context-availability"]
    assert any(item["id"] == "ev-operating-context-availability" for item in package["supporting_evidence"])


def test_missing_mapping_creates_only_evidence_bounded_limitation() -> None:
    result = _comparison("limitations-mapping")
    result["telemetry_signal_catalog"] = {
        "pump_power_kw": {"source_column": "pump_power_kw", "canonical_role": "electrical_power"},
    }

    package = build_evidence_package(result)
    limitation = package["limitations"][0]

    assert limitation["category"] == "missing_semantic_mapping"
    assert limitation["severity"] == "unknown"
    assert "chw_flow_gpm" in limitation["reason"]
    assert limitation["supporting_evidence_refs"] == ["ev-semantic-mapping-availability"]


def test_dictionary_key_signal_identity_prevents_false_missing_mapping() -> None:
    result = _comparison("limitations-key-identity")
    result["telemetry_signal_catalog"] = {
        "pump_power_kw": {"canonical_role": "electrical_power"},
        "chw_flow_gpm": {"canonical_role": "process_rate"},
    }
    original_id = build_evidence_package(_comparison("limitations-key-identity"))["id"]

    first = build_evidence_package(result)
    second = build_evidence_package(result)

    assert first == second
    assert first["id"] == original_id
    assert first["limitations"] == []
    assert first["confidence"]["mapping_confidence"]["level"] == "medium"


def test_source_column_signal_identity_remains_supported() -> None:
    result = _comparison("limitations-source-column-identity")
    result["telemetry_signal_catalog"] = [
        {"source_column": "pump_power_kw", "canonical_role": "electrical_power"},
        {"source_column": "chw_flow_gpm", "canonical_role": "process_rate"},
    ]

    package = build_evidence_package(result)

    assert package["limitations"] == []
    assert package["confidence"]["mapping_confidence"]["level"] == "medium"


def test_mapping_confidence_and_limitation_share_catalog_identity() -> None:
    result = _comparison("limitations-shared-identity")
    result["telemetry_signal_catalog"] = {
        "pump_power_kw": {"canonical_role": "electrical_power"},
        "unrelated_signal": {"canonical_role": "process_rate"},
    }

    package = build_evidence_package(result)

    assert package["confidence"]["mapping_confidence"]["level"] == "unknown"
    assert package["limitations"][0]["category"] == "missing_semantic_mapping"
    evidence = next(item for item in package["supporting_evidence"] if item["id"] == "ev-semantic-mapping-availability")
    assert evidence["value"]["unmapped_variables"] == ["chw_flow_gpm"]


def test_persisted_telemetry_ambiguity_creates_supported_limitation() -> None:
    result = _comparison("limitations-telemetry")
    result["telemetry_ambiguity"] = {
        "status": "supported", "alternatives": ["restriction", "equipment degradation"],
    }

    limitation = build_evidence_package(result)["limitations"][0]

    assert limitation["category"] == "telemetry_ambiguity"
    assert "cannot" in limitation["description"]
    assert limitation["supporting_evidence_refs"] == ["ev-telemetry-ambiguity"]


def test_multiple_persisted_explanations_do_not_become_hypotheses() -> None:
    result = _comparison("limitations-alternatives")
    result["conditions"][0]["alternative_explanations"] = [
        "Operating-mode difference", "Instrumentation condition",
    ]

    package = build_evidence_package(result)

    assert [item["category"] for item in package["limitations"]] == ["multiple_plausible_explanations"]
    assert package["hypotheses"] == []
    assert package["limitations"][0]["supporting_evidence_refs"] == ["ev-supported-alternatives"]


def test_unknown_comparability_and_physics_unavailability_are_supported() -> None:
    result = _with_operating_context(_comparison("limitations-availability"))
    result["operating_context_inputs"]["baseline"].pop("process_demand")
    result["physics_reasoning"] = {"status": "unavailable", "reason": "No applicable persisted physics result."}

    first = build_evidence_package(result)
    second = build_evidence_package(result)

    assert first == second
    assert first["id"] == second["id"]
    assert [item["category"] for item in first["limitations"]] == [
        "comparable_operating_conditions_unavailable", "physics_validation_unavailable",
    ]
    assert {item["severity"] for item in first["limitations"]} == {"unknown"}
    evidence_ids = {item["id"] for item in first["supporting_evidence"]}
    assert all(set(item["supporting_evidence_refs"]) <= evidence_ids for item in first["limitations"])


def test_invalid_limitation_enums_are_rejected() -> None:
    result = _comparison("limitations-invalid-enum")
    result["operating_context_inputs"] = None
    package = build_evidence_package(result)
    package["limitations"][0]["category"] = "diagnosis"

    with pytest.raises(ValidationError):
        EvidencePackage.model_validate(package)
    with pytest.raises(ValueError):
        LimitationCategory("diagnosis")
    with pytest.raises(ValueError):
        LimitationSeverity("critical")
    with pytest.raises(ValueError):
        LimitationStatus("suspected")
