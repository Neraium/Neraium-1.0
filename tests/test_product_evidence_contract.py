from __future__ import annotations

import json
from copy import deepcopy

import pytest

from app.services.analysis_explanations import build_analysis_explanation
from app.services.analysis_result_contract import build_analysis_result, ensure_analysis_result
from app.services.product_evidence_contract import product_evidence
from app.services.measurable_consequence import build_measurable_consequence
from app.engine.sii.expected_behavior import evaluate_expected_behavior
from app.services import evidence_store, runtime_db
from app.services.finding_workflow import evidence_finding_id

FORBIDDEN = {"cause", "causes", "likely_cause", "likely_causes", "root_cause", "probable_cause", "suspected_cause", "diagnosis", "diagnostic_conclusion", "automated_corrective_action", "potential_operational_causes", "possible_operational_causes", "possible_operational_causes_summary", "likely_driver", "primary_driver"}


def assert_no_conclusion(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in FORBIDDEN:
                assert item in (None, [], {}), (key, item)
            if key not in {"provenance", "measurable_consequence"}:
                assert_no_conclusion(item)
    elif isinstance(value, list):
        for item in value:
            assert_no_conclusion(item)


def relationship_source():
    changes = []
    for index, target in enumerate(("flow", "pressure")):
        changes.append({
            "relationship_id": f"rel-{index}", "columns": ["power", target],
            "baseline_correlation": 0.9, "recent_correlation": 0.2,
            "correlation_delta": 0.7, "baseline_sample_size": 80,
            "recent_sample_size": 40, "confidence_score": 0.9,
            "operating_mode": {"match": "strong"},
            "data_confidence": {"rating": "high", "reasons": []},
            "persistence": {"status": "persistent", "persistent": True},
            "source_time_ranges": [{"current_start": 0, "current_end": 360}],
        })
    return {
        "run_id": "cause-contract-run", "analysis_id": "cause-contract-run",
        "relationship_model": {"top_relationship_changes": changes},
        "engine_result": {"persistence_assessment": {"persistent_columns": ["power", "flow", "pressure"]}},
        "data_quality": {"data_confidence": {"rating": "high"}, "sensor_health": [{"signal": tag, "health": "healthy"} for tag in ("power", "flow", "pressure")]},
    }


def test_original_fresh_reproduction_no_longer_generates_cause():
    result = build_analysis_explanation({"run_id": "repro", "baseline_analysis": {"overall_assessment": "normal", "columns_analyzed": 2, "baseline_window_rows": 80, "recent_window_rows": 80}})
    assert result["insights"][0]["id"] == "baseline-stable"
    assert result["insights"][0]["what_changed"]
    assert_no_conclusion(result)


def test_persistent_multisignal_evidence_survives_without_physical_attribution():
    source = relationship_source()
    original = deepcopy(source)
    first = build_analysis_explanation(source)
    assert first == build_analysis_explanation(source)
    assert source == original
    assert first["relationships"]
    assert len(first["relationships"]) == 2
    assert {tag for rel in first["relationships"] for tag in rel["columns"]} == {"power", "flow", "pressure"}
    assert all(rel["correlation_delta"] == 0.7 for rel in first["relationships"])
    assert all(insight["persistence"]["persistent"] for insight in first["insights"])
    assert_no_conclusion(first)
    canonical = build_analysis_result({**source, "analysis_explanation": first})
    assert canonical["relationships"]
    assert_no_conclusion(canonical)


def test_historical_fields_are_inert_without_mutating_saved_data():
    canonical = build_analysis_result(relationship_source())
    canonical["insights"][0].update(likely_cause="LEGACY_CAUSE_CANARY", diagnosis="LEGACY_DIAGNOSIS_CANARY", possible_operational_causes=["LEGACY_MECHANISM_CANARY"])
    original = deepcopy(canonical)
    projected = ensure_analysis_result({"analysis_result": canonical})
    assert "LEGACY_" not in json.dumps(projected)
    assert canonical == original
    assert projected["relationships"] == canonical["relationships"]


@pytest.mark.parametrize("quantifiable", [True, False])
def test_expected_rate_consequence_and_provenance_unchanged(quantifiable):
    rows = [{"t": index * 60, "load": 10 + index, "flow": 45 + 2 * index} for index in range(7)]
    expected = evaluate_expected_behavior(
        active_model={"expected_behavior_models": {"model": {"model_id": "model", "target_signal": "flow", "predictor_signals": ["load"], "operating_mode": "running", "validation": {"passed": True}, "sample_support": 80, "model_parameters": {"intercept": 5, "slope": 2, "lag_samples": 0}, "source_relationships": ["rel"]}}},
        rows=rows, operating_mode="running", data_quality={"readiness": "ready"},
        sensor_health={"signals": [{"signal": tag, "health": "healthy"} for tag in ("flow", "load")]},
        source_model_version="3", evaluation_time="2026-09-05T00:00:00Z", timestamp_column="t",
    )
    finding = {"id": "consequence-finding", "evidence_id": "evidence", "support_level": "high", "source_relationship_ids": ["rel"], "persistence": {"status": "persistent"}, "operating_mode": {"match": "strong"}, "source_time_ranges": [{"current_start": 0, "current_end": 360}]}
    kwargs = {"expected_behavior": expected, "signal_catalog": {"flow": {"canonical_unit": "gpm", **({"resource_type": "water"} if quantifiable else {})}}, "analysis_run_id": "run"}
    recorded = build_measurable_consequence(finding, **kwargs)
    legacy = {**finding, "likely_cause": "LEGACY_CAUSE_CANARY", "measurable_consequence": recorded}
    projected = product_evidence(legacy)
    assert projected["measurable_consequence"] == recorded
    assert build_measurable_consequence(projected, **kwargs) == recorded
    assert recorded == build_measurable_consequence(finding, **kwargs)
    if quantifiable:
        assert recorded["cumulative_amount"] == 120
        assert recorded["duration_seconds"] == 360
        assert recorded["provenance"]["expected_behavior"] == expected["expected_values"][0]
    else:
        assert recorded["status"] == "not_quantifiable"
        assert recorded["statement"] == "Consequence not quantifiable from available evidence."
        assert "cumulative_amount" not in recorded
        assert "duration_seconds" not in recorded


def test_legacy_storage_findings_api_and_exports_do_not_surface_conclusions(client):
    record = {
        "run_id": "legacy-cause-api", "source_type": "csv_upload", "source_name": "plant.csv",
        "status": "completed", "created_at": "2026-09-05T00:00:00Z", "completed_at": "2026-09-05T00:01:00Z",
        "observation_status": "open", "operator_feedback_history": [], "finding_status_history": [],
        "primary_drivers": ["LEGACY_DRIVER_CANARY"],
        "finding_identity_snapshot": [{"source_finding_id": "finding", "finding": {"condition_id": "finding", "headline": "Measured flow relationship changed", "likely_cause": "LEGACY_CAUSE_CANARY", "diagnosis": "LEGACY_DIAGNOSIS_CANARY", "source_relationship_ids": ["rel"], "source_tags": ["flow", "pressure"]}}],
    }
    evidence_store.upsert_evidence_run(record)
    stored_before = runtime_db.read_evidence_run_db(record["run_id"])
    response = client.get(f"/api/findings/{evidence_finding_id(record['run_id'], 'finding')}")
    assert response.status_code == 200
    assert "LEGACY_" not in response.text
    assert response.json()["evidence"]["finding"]["source_relationship_ids"] == ["rel"]
    evidence_response = client.get("/api/evidence/latest")
    assert evidence_response.status_code == 200
    assert "LEGACY_" not in evidence_response.text
    for formatter in (evidence_store.build_evidence_export_payload, evidence_store.build_evidence_export, evidence_store.build_evidence_export_csv):
        assert "LEGACY_" not in str(formatter(record))
    stored_after = runtime_db.read_evidence_run_db(record["run_id"])
    assert stored_after == stored_before
    assert stored_after["finding_identity_snapshot"][0]["finding"]["likely_cause"] == "LEGACY_CAUSE_CANARY"


def test_source_ids_and_canonical_provenance_are_not_text_sanitized():
    value = {"likely_cause": "retired", "source_tag_ids": ["diagnosis/pump/cause"], "provenance": {"original_header": "likely_cause"}}
    projected = product_evidence(value)
    assert projected == {"source_tag_ids": value["source_tag_ids"], "provenance": value["provenance"]}


def test_signal_names_matching_retired_terms_are_preserved_as_telemetry():
    telemetry = {"rows": [{"cause": 1, "diagnosis": 2}], "telemetry_signal_catalog": {"cause": {"canonical_unit": "kW"}}}
    assert product_evidence(telemetry) == telemetry


def test_legacy_driver_does_not_become_a_finding_title(client):
    record = {"run_id": "legacy-driver-title", "status": "completed", "source_type": "csv_upload", "primary_drivers": ["LEGACY_DRIVER_CANARY"], "created_at": "2026-09-05T00:00:00Z"}
    evidence_store.upsert_evidence_run(record)
    response = client.get(f"/api/findings/{evidence_finding_id(record['run_id'], 'run-observation')}")
    assert response.status_code == 200
    assert "LEGACY_DRIVER_CANARY" not in response.text


def test_runner_evidence_does_not_promote_internal_attribution_category():
    from app.services.sii_runner import build_runner_evidence

    evidence = build_runner_evidence({"regime": "changed", "urgency": "review", "instability_score": 0.2, "structural_drift": 0.3}, ["flow", "pressure"], {"driver_category": "LEGACY_CATEGORY_CANARY"}, {})
    assert "LEGACY_CATEGORY_CANARY" not in str(evidence)
    assert "Driver attribution" not in str(evidence)
    assert "2 numeric telemetry channels" in evidence[0]
    assert "0.2" in evidence[2] and "0.3" in evidence[2]
