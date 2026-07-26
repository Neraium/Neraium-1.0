from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.change_trajectory import classify_trajectory
from app.services.analysis_result_contract import build_analysis_result, is_canonical_analysis_result
from app.services.condition_corroboration import (
    ConditionCorroborationService,
    evaluate_condition_escalation,
    localize_condition,
)
from app.services.historical_comparables import ComparableHistoricalEpisodeService
from app.services.upload_evidence import build_evidence_record_from_result


WINDOW = "2026-07-01T00:00:00Z to 2026-07-02T00:00:00Z"


def relationship(
    identifier: str,
    left: str,
    right: str,
    *,
    change_type: str = "weakened",
    system: str = "Pumping System",
    confidence: float = 0.9,
) -> dict:
    return {
        "id": identifier,
        "columns": [left, right],
        "change_type": change_type,
        "system": system,
        "confidence_score": confidence,
        "correlation_delta": 0.68,
        "baseline_strength": 0.88,
        "current_strength": 0.2 if change_type == "weakened" else 0.92,
        "baseline_sample_size": 48,
        "recent_sample_size": 16,
        "time_window": WINDOW,
    }


def test_single_relationship_remains_isolated() -> None:
    result = ConditionCorroborationService().corroborate(
        [relationship("rel-1", "pump_power", "flow")]
    )

    assert len(result) == 1
    assert result[0]["corroboration_strength"] == "isolated"
    assert result[0]["relationship_count"] == 1
    assert result[0]["conflicting_relationships"] == []


def test_multiple_connected_relationships_form_one_corroborated_condition() -> None:
    relationships = [
        relationship("rel-1", "pump_power", "flow"),
        relationship("rel-2", "flow", "discharge_pressure"),
        relationship("rel-3", "discharge_pressure", "pump_speed"),
        relationship("rel-4", "pump_speed", "motor_current"),
    ]

    result = ConditionCorroborationService().corroborate(relationships)

    assert len(result) == 1
    assert result[0]["corroboration_strength"] == "strong"
    assert result[0]["relationship_count"] == 4
    assert result[0]["affected_signals"] == [
        "pump_power",
        "flow",
        "discharge_pressure",
        "pump_speed",
        "motor_current",
    ]
    assert result[0]["supporting_relationships"][1]["role"] == "secondary evidence"


def test_same_system_and_time_without_shared_telemetry_does_not_false_corroborate() -> None:
    relationships = [
        relationship("rel-1", "pump_power", "flow"),
        relationship("rel-2", "suction_pressure", "water_temperature"),
    ]

    result = ConditionCorroborationService().corroborate(relationships)

    assert len(result) == 2
    assert all(item["corroboration_strength"] == "isolated" for item in result)
    assert result[0]["independent_relationships"][0]["role"] == "independent evidence"


def test_shared_signal_outside_the_comparison_window_does_not_false_corroborate() -> None:
    first = relationship("rel-1", "pump_power", "flow")
    later = relationship("rel-2", "flow", "discharge_pressure")
    later["time_window"] = "2026-07-20T00:00:00Z to 2026-07-21T00:00:00Z"

    result = ConditionCorroborationService().corroborate([first, later])

    assert len(result) == 2
    assert all(item["corroboration_strength"] == "isolated" for item in result)


def test_five_connected_relationships_can_reach_systemic_strength() -> None:
    relationships = [
        relationship("rel-1", "pump_power", "flow"),
        relationship("rel-2", "flow", "discharge_pressure"),
        relationship("rel-3", "discharge_pressure", "pump_speed"),
        relationship("rel-4", "pump_speed", "motor_current"),
        relationship("rel-5", "motor_current", "suction_pressure"),
    ]

    result = ConditionCorroborationService().corroborate(relationships)

    assert result[0]["corroboration_strength"] == "systemic"
    assert result[0]["relationship_count"] == 5


def test_opposite_connected_relationship_is_retained_as_conflicting_evidence() -> None:
    relationships = [
        relationship("rel-1", "pump_power", "flow"),
        relationship("rel-2", "flow", "discharge_pressure"),
        relationship(
            "rel-3",
            "flow",
            "motor_current",
            change_type="strengthened",
        ),
    ]

    result = ConditionCorroborationService().corroborate(relationships)
    weakening = next(item for item in result if item["relationship_count"] == 2)

    assert [item["relationship_id"] for item in weakening["conflicting_relationships"]] == ["rel-3"]
    assert weakening["confidence_score"] < 0.8


def test_connected_low_confidence_relationship_is_retained_as_uncertain_evidence() -> None:
    relationships = [
        relationship("rel-1", "pump_power", "flow"),
        relationship("rel-2", "flow", "discharge_pressure"),
        relationship(
            "rel-3",
            "discharge_pressure",
            "pump_speed",
            confidence=0.3,
        ),
    ]

    result = ConditionCorroborationService().corroborate(relationships)
    supported = next(item for item in result if item["relationship_count"] == 2)

    assert supported["uncertain_relationships"][0]["relationship_id"] == "rel-3"
    assert supported["uncertain_relationships"][0]["role"] == "uncertain evidence"
    assert supported["independent_relationships"] == []


def test_zero_current_strength_is_preserved_in_relationship_evidence() -> None:
    changed = relationship("rel-1", "pump_power", "flow")
    changed["current_strength"] = 0.0
    changed["strength"] = 0.7

    result = ConditionCorroborationService().corroborate([changed])

    assert result[0]["supporting_relationships"][0]["current_strength"] == 0.0


@pytest.mark.parametrize(
    ("expected", "inputs"),
    [
        (
            "Strengthening",
            {
                "persistence": 0.8,
                "corroboration_history": [1, 2, 4],
                "confidence_trend": [0.55, 0.68, 0.85],
                "evidence_spread": [0.2, 0.38, 0.62],
            },
        ),
        (
            "Recovering",
            {
                "persistence": 0.7,
                "corroboration_history": [2, 4, 2],
                "confidence_trend": [0.65, 0.82, 0.6],
                "evidence_spread": [0.3, 0.8, 0.4],
            },
        ),
        (
            "Recurring",
            {
                "persistence": 0.4,
                "corroboration_history": [2, 0, 2],
                "confidence_trend": [0.7, 0.0, 0.72],
                "evidence_spread": [0.5, 0.0, 0.52],
            },
        ),
        (
            "Stable shift",
            {
                "persistence": 0.9,
                "corroboration_history": [3, 3, 3],
                "confidence_trend": [0.8, 0.81, 0.8],
                "evidence_spread": [0.55, 0.56, 0.55],
            },
        ),
        (
            "Sudden",
            {
                "persistence": 0.3,
                "corroboration_history": [0, 0, 3],
                "confidence_trend": [0.0, 0.0, 0.8],
                "evidence_spread": [0.03, 0.05, 0.7],
            },
        ),
        (
            "Gradual",
            {
                "persistence": 0.55,
                "corroboration_history": [2, 2, 3],
                "confidence_trend": [0.6, 0.67, 0.72],
                "evidence_spread": [0.25, 0.34, 0.43],
            },
        ),
        (
            "Weakening",
            {
                "persistence": 0.65,
                "corroboration_history": [4, 3, 2],
                "confidence_trend": [0.84, 0.72, 0.6],
                "evidence_spread": [0.7, 0.55, 0.4],
            },
        ),
        (
            "Intermittent",
            {
                "persistence": 0.4,
                "corroboration_history": [0, 2, 0, 2],
                "confidence_trend": [0.0, 0.68, 0.0, 0.7],
                "evidence_spread": [0.0, 0.5, 0.0, 0.52],
            },
        ),
    ],
)
def test_trajectory_classification(expected: str, inputs: dict) -> None:
    assert classify_trajectory(**inputs) == expected


def historical_rows(count: int = 240) -> list[dict[str, str]]:
    start = datetime(2026, 6, 1, tzinfo=UTC)
    rows: list[dict[str, str]] = []
    period_size = max(6, min(24, count // 20))
    for index in range(count):
        flow = 90 + (index % period_size)
        pressure = 30 + (flow * 0.4)
        if index >= count - period_size:
            pressure = 38 + ((index * 7) % 5)
        rows.append(
            {
                "timestamp": (start + timedelta(hours=index)).isoformat(),
                "flow": str(flow),
                "discharge_pressure": str(pressure),
                "pump_power": str(20 + (flow * 0.2) if index < count - period_size else 21 + ((index * 3) % 4)),
                "pump_speed": "50",
                "pump_stage": "1",
                "occupancy_load_pct": "70",
            }
        )
    return rows


def test_comparable_historical_episode_retrieval_is_like_for_like_and_additive() -> None:
    result = ComparableHistoricalEpisodeService().retrieve(
        rows=historical_rows(),
        relationship=relationship("rel-1", "flow", "discharge_pressure"),
        timestamp_column="timestamp",
    )

    assert result["status"] == "supported"
    assert result["comparable_period_count"] >= 4
    assert result["supports_existing_baseline"] is True
    assert "normally moved together" in result["normal_behavior"]
    assert "Current behavior" in result["current_behavior"]
    dimensions = {item["dimension"] for item in result["matching_dimensions"]}
    assert {"time_band", "equipment_state", "load_band"} <= dimensions


def test_condition_creation_includes_localization_timeline_and_next_checks() -> None:
    relationships = [
        relationship("rel-1", "pump_power", "flow"),
        relationship("rel-2", "flow", "discharge_pressure"),
        relationship("rel-3", "discharge_pressure", "pump_speed"),
    ]
    conditions = ConditionCorroborationService().build_conditions(
        relationships=relationships,
        findings=[
            {
                "id": "finding-1",
                "source_tags": ["pump_power", "flow", "discharge_pressure"],
                "classification": {
                    "type": "unexplained_systemic_change",
                    "label": "Unexplained systemic change",
                    "confidence": "high",
                    "reasons": ["The relationship changes persisted during comparable operation."],
                    "certainty_limit": "The evidence does not establish a cause.",
                },
            }
        ],
        rows=historical_rows(),
        timestamp_column="timestamp",
        data_quality={"data_confidence": {"rating": "high"}},
        operating_mode={"match": "strong", "confidence": "high"},
        site_name="Rush Tower",
        generated_at="2026-07-26T00:00:00Z",
    )

    assert len(conditions) == 1
    condition = conditions[0]
    assert condition["object_type"] == "condition"
    assert condition["headline"] == "Pump response weakening in Rush Tower Pumping System"
    assert condition["localization"]["site"] == "Rush Tower"
    assert condition["localization"]["monitored_boundary"] == "Discharge boundary"
    assert condition["affected_boundaries"] == ["Discharge boundary"]
    assert len(condition["timeline"]) == 3
    assert condition["timeline"][1]["event_type"] == "trajectory_classified"
    assert condition["next_checks"][0].startswith("Verify source data")
    assert condition["comparable_operation"]["status"] == "supported"


def test_localization_stops_at_telemetry_supported_boundary() -> None:
    result = localize_condition(
        [
            relationship("rel-1", "pump_7_power", "flow"),
            relationship("rel-2", "flow", "pump_7_discharge_pressure"),
        ],
        site_name="Rush Tower",
    )

    assert result["precision"] == "monitored_boundary"
    assert result["likely_investigation_area"] == "Discharge boundary"
    assert result["system"] == "Pumping System"
    assert "pipe" not in result["likely_investigation_area"].lower()
    assert "valve" not in result["likely_investigation_area"].lower()
    assert "pump 7" not in result["likely_investigation_area"].lower()


def test_condition_escalation_never_uses_one_weak_relationship() -> None:
    result = evaluate_condition_escalation(
        classification={"type": "unexplained_systemic_change"},
        confidence="high",
        trajectory={"state": "Strengthening"},
        corroboration={"relationship_count": 1, "corroboration_strength": "isolated"},
        operating_mode={"match": "strong"},
        data_quality={"data_confidence": {"rating": "high"}},
        criticality="critical",
    )

    assert result["eligible"] is False
    assert result["level"] == "hold"
    assert any("Fewer than two" in reason for reason in result["blocked_by"])


def test_condition_escalation_uses_all_governed_inputs() -> None:
    result = evaluate_condition_escalation(
        classification={"type": "unexplained_systemic_change"},
        confidence="high",
        trajectory={"state": "Strengthening"},
        corroboration={"relationship_count": 5, "corroboration_strength": "systemic"},
        operating_mode={"match": "strong"},
        data_quality={"data_confidence": {"rating": "high"}},
        criticality="critical",
    )

    assert result["prompt_engineering_review"] is True
    assert result["level"] == "prompt_engineering_review"
    assert set(result["inputs"]) == {
        "classification",
        "confidence",
        "trajectory",
        "corroboration",
        "relationship_count",
        "operating_mode_match",
        "data_quality",
        "criticality",
    }


def test_analysis_contract_adds_conditions_without_removing_legacy_objects() -> None:
    relationships = [
        relationship("rel-1", "pump_power", "flow"),
        relationship("rel-2", "flow", "discharge_pressure"),
        relationship("rel-3", "discharge_pressure", "pump_speed"),
    ]
    result = build_analysis_result(
        {
            "job_id": "condition-run",
            "filename": "condition.csv",
            "completed_at": "2026-07-26T00:00:00Z",
            "data_quality": {
                "reliability_rating": "strong",
                "data_confidence": {"rating": "high"},
                "operating_mode": {"match": "strong", "confidence": "high"},
            },
            "baseline_analysis": {
                "baseline_window_rows": 48,
                "recent_window_rows": 16,
                "columns_analyzed": 4,
                "overall_assessment": "needs_review",
            },
            "analysis_explanation": {
                "systems": [{"name": "Pumping System"}],
                "relationships": relationships,
                "insights": [
                    {
                        "id": "legacy-finding",
                        "title": "Pump response changed",
                        "source_tags": ["pump_power", "flow"],
                        "supporting_evidence": ["Pump power and flow changed together."],
                    }
                ],
                "recommendations": [],
                "fingerprint": {},
            },
        }
    )

    assert result["schema_version"] == "analysis-result-v1"
    assert result["primary_object"] == "condition"
    assert result["conditions"][0]["schema_version"] == "condition-v1"
    assert result["relationships"]
    assert result["insights"]
    assert result["conditions"][0]["evidence_refs"]
    assert result["analysis_metadata"]["condition_count"] == 1
    assert is_canonical_analysis_result(result) is True

    legacy_without_conditions = dict(result)
    legacy_without_conditions.pop("conditions")
    legacy_without_conditions.pop("primary_object")
    assert is_canonical_analysis_result(legacy_without_conditions) is True


def test_persisted_evidence_record_keeps_condition_as_primary_object() -> None:
    condition = {
        "object_type": "condition",
        "condition_id": "condition-pump",
        "headline": "Pump response weakening in Rush Tower Pumping System",
        "confidence": "high",
        "confidence_score": 0.84,
        "affected_signals": ["pump_power", "flow", "discharge_pressure"],
        "affected_systems": ["Pumping System"],
        "affected_boundaries": ["Discharge boundary"],
        "localization": {
            "system": "Pumping System",
            "monitored_boundary": "Discharge boundary",
        },
        "trajectory": {"state": "Strengthening"},
        "corroboration": {
            "relationship_count": 3,
            "corroboration_strength": "moderate",
        },
        "supporting_evidence": [
            "3 connected relationships changed in the same comparison window."
        ],
        "why_it_matters": "The evidence pattern is strengthening.",
    }
    record = build_evidence_record_from_result(
        run_id="condition-run",
        filename="condition.csv",
        source_type="csv_upload",
        result={
            "row_count": 100,
            "column_count": 4,
            "analysis_result": {"conditions": [condition]},
            "sii_intelligence": {},
            "baseline_analysis": {},
            "data_quality": {},
        },
        created_at="2026-07-26T00:00:00Z",
        completed_at="2026-07-26T00:01:00Z",
        status="completed",
        initiated_by="engineer@neraium.test",
    )

    assert record["observation_type"] == "corroborated_condition"
    assert record["condition_id"] == "condition-pump"
    assert record["finding_title"] == condition["headline"]
    assert record["evidence_summary"] == condition["supporting_evidence"]
    assert record["variables"] == condition["affected_signals"]
    assert record["condition"]["trajectory"]["state"] == "Strengthening"
