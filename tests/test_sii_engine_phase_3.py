from __future__ import annotations

import math
from copy import deepcopy

from app.engine.sii.evidence_fusion import CLASSIFICATIONS, SOURCE_MODULE_ORDER, fuse_evidence
from app.engine.sii.physics_reasoning import evaluate_physics_reasoning
from app.engine.sii_engine import evaluate_sii


def _pump_prior() -> dict:
    return {
        "id": "pump_hydraulic_response",
        "name": "Pump Hydraulic Response",
        "description": "Compare configured pump demand and hydraulic response behavior.",
        "domain": "water",
        "equipment_types": ["centrifugal_pump"],
        "required_signals": ["pump_speed", "flow"],
        "required_relationships": [["pump_speed", "flow"]],
        "required_operating_modes": ["running"],
        "prerequisites": [
            {
                "source": "signal_drift",
                "path": "column_drift",
                "where": {"column": "pump_speed"},
                "field": "direction",
                "operator": "eq",
                "value": "up",
                "description": "Pump speed increased.",
            },
            {
                "source": "adaptive_persistence",
                "path": "persistent_columns",
                "operator": "contains",
                "value": "pump_speed",
                "description": "The speed change had persistence support.",
            },
        ],
        "expected_behavior": {
            "logic": "all",
            "conditions": [
                {
                    "source": "signal_drift",
                    "path": "column_drift",
                    "where": {"column": "flow"},
                    "field": "direction",
                    "operator": "eq",
                    "value": "up",
                    "description": "Flow should increase under the configured expectation.",
                },
                {
                    "source": "relationship_graph",
                    "path": "edges",
                    "where": {
                        "relationship": {
                            "operator": "contains_all",
                            "value": ["pump_speed", "flow"],
                        }
                    },
                    "field": "change_type",
                    "operator": "not_in",
                    "value": ["weakened", "missing"],
                    "description": "The configured relationship should remain available.",
                },
            ],
        },
        "validity_conditions": [
            {
                "source": "data_quality",
                "path": "data_confidence.rating",
                "operator": "in",
                "value": ["high", "moderate"],
                "description": "Data quality must be acceptable.",
            },
            {
                "source": "sensor_health",
                "path": "signals",
                "where": {
                    "signal": {
                        "operator": "in",
                        "value": ["pump_speed", "flow"],
                    }
                },
                "field": "health",
                "operator": "eq",
                "value": "healthy",
                "quantifier": "all",
                "description": "Required signals must be healthy.",
            },
        ],
        "confidence_modifier": {
            "level": "moderate",
            "basis": "externally_configured_engineering_prior",
        },
        "limitations": [
            "The configured expectation applies only to comparable pump operation."
        ],
        "reasoning_template": {
            "supported": "Pump demand matches the configured hydraulic response.",
            "contradicted": "Pump demand no longer matches the configured hydraulic response.",
            "indeterminate": "Pump hydraulic response could not be compared.",
        },
    }


def _canonical_evidence() -> dict:
    return {
        "signal_drift": {
            "status": "complete",
            "column_drift": [
                {"column": "pump_speed", "direction": "up"},
                {"column": "flow", "direction": "stable"},
            ],
        },
        "relationship_analysis": {
            "status": "complete",
            "relationship_graph": {
                "edges": [
                    {
                        "relationship": "pump_speed <-> flow",
                        "source": "metric:pump_speed",
                        "target": "metric:flow",
                    }
                ]
            },
        },
        "operating_modes": {
            "status": "complete",
            "baseline_mode": "running",
            "recent_mode": "running",
            "match": "strong",
        },
        "adaptive_persistence": {
            "status": "complete",
            "persistent_columns": ["pump_speed"],
        },
        "temporal_analysis": {"status": "complete", "marker": "temporal"},
        "multiscale_analysis": {"status": "complete", "marker": "multiscale"},
        "relationship_graph": {
            "status": "complete",
            "edges": [
                {
                    "relationship": "pump_speed <-> flow",
                    "source": "metric:pump_speed",
                    "target": "metric:flow",
                    "change_type": "weakened",
                }
            ],
        },
        "covariance_analysis": {"status": "complete", "marker": "covariance"},
        "data_quality": {
            "status": "complete",
            "data_confidence": {"rating": "high"},
        },
        "sensor_health": {
            "status": "complete",
            "signals": [
                {"signal": "pump_speed", "health": "healthy"},
                {"signal": "flow", "health": "healthy"},
            ],
        },
        "uncertainty": {
            "status": "limited",
            "limitations": ["Moderate sensor uncertainty."],
        },
    }


def test_configured_prior_evaluates_expected_behavior_without_overriding_statistics() -> None:
    result = evaluate_physics_reasoning(
        priors=[_pump_prior()],
        analytical_evidence=_canonical_evidence(),
        equipment_context={"equipment_type": "centrifugal_pump"},
    )

    assert result["status"] == "complete"
    assert result["applicable_priors"] == ["pump_hydraulic_response"]
    assert result["supporting_priors"] == []
    assert result["contradictory_priors"] == ["pump_hydraulic_response"]
    evaluated = result["evaluated_priors"][0]
    assert evaluated["status"] == "contradicted"
    assert evaluated["applicable"] is True
    assert {
        item["evidence_id"] for item in evaluated["supporting_evidence"]
    } >= {
        "physics:pump_hydraulic_response:prerequisites:1",
        "physics:pump_hydraulic_response:prerequisites:2",
        "physics:pump_hydraulic_response:validity_conditions:1",
        "physics:pump_hydraulic_response:validity_conditions:2",
    }
    assert len(evaluated["contradictory_evidence"]) == 2
    assert {
        item["originating_module"] for item in evaluated["contradictory_evidence"]
    } == {"signal_drift", "relationship_graph"}
    assert evaluated["confidence_modifier"] == _pump_prior()["confidence_modifier"]
    assert evaluated["confidence_modifier_applied"] is False
    assert evaluated["statistical_evidence_overridden"] is False
    assert result["principles"]["diagnosis_performed"] is False
    assert result["principles"]["recommendations_generated"] is False


def test_prior_is_not_applicable_when_validity_condition_is_not_satisfied() -> None:
    evidence = _canonical_evidence()
    evidence["sensor_health"]["signals"][1]["health"] = "suspect"
    result = evaluate_physics_reasoning(
        priors=[_pump_prior()],
        analytical_evidence=evidence,
        equipment_context={"equipment_type": "centrifugal_pump"},
    )

    assert result["status"] == "limited"
    assert result["applicable_priors"] == []
    evaluated = result["evaluated_priors"][0]
    assert evaluated["status"] == "not_applicable"
    assert evaluated["applicable"] is False
    assert evaluated["supporting_evidence"] == []
    assert evaluated["contradictory_evidence"] == []
    assert evaluated["reasoning_trace"]["expected_behavior_evaluated"] is False
    assert "validity_conditions_not_satisfied" in evaluated["reasoning_trace"]["applicability_reasons"]
    assert result["ignored_priors"][0]["id"] == "pump_hydraulic_response"


def test_no_configured_priors_forces_no_engineering_assumptions() -> None:
    result = evaluate_physics_reasoning(
        priors=[],
        analytical_evidence=_canonical_evidence(),
        equipment_context={},
    )

    assert result["status"] == "limited"
    assert result["reason"] == "no_configured_engineering_priors"
    assert result["evaluated_priors"] == []
    assert result["supporting_priors"] == []
    assert result["contradictory_priors"] == []
    assert "no engineering assumptions were forced" in result["limitations"][0].lower()


def test_fusion_preserves_every_source_and_generates_only_behavioral_observations() -> None:
    evidence = _canonical_evidence()
    ignored = _pump_prior()
    ignored["id"] = "other_equipment_response"
    ignored["name"] = "Other Equipment Response"
    ignored["equipment_types"] = ["positive_displacement_pump"]
    physics = evaluate_physics_reasoning(
        priors=[_pump_prior(), ignored],
        analytical_evidence=evidence,
        equipment_context={"equipment_type": "centrifugal_pump"},
    )
    trace = {
        "module_statuses": {
            module: {"status": "complete"} for module in SOURCE_MODULE_ORDER
        },
        "modules_attempted": list(SOURCE_MODULE_ORDER),
    }

    result = fuse_evidence(
        analytical_evidence=evidence,
        physics_reasoning=physics,
        processing_trace=trace,
    )

    assert result["status"] == "complete"
    module_items = {
        item["originating_module"]: item
        for item in result["evidence_inventory"]
        if item["evidence_id"].startswith("module:")
    }
    assert list(module_items) == list(SOURCE_MODULE_ORDER)
    for module in SOURCE_MODULE_ORDER:
        expected = physics if module == "physics_reasoning" else evidence[module]
        assert module_items[module]["evidence"] == expected
    assert {
        item["classification"] for item in result["evidence_inventory"]
    } <= set(CLASSIFICATIONS)
    assert result["contradictory_evidence"]
    assert result["limiting_evidence"]

    observation = result["observations"][0]
    assert observation["observation"] == (
        "Pump demand no longer matches the configured hydraulic response."
    )
    assert observation["behavioral_status"] == (
        "not_consistent_with_configured_expectation"
    )
    assert {
        item["evidence_id"] for item in observation["supporting_evidence"]
    } >= {
        "physics:pump_hydraulic_response:prerequisites:1",
        "physics:pump_hydraulic_response:prerequisites:2",
        "physics:pump_hydraulic_response:expectation:1",
        "physics:pump_hydraulic_response:expectation:2",
    }
    assert observation["contradictory_evidence"] == []
    assert observation["engineering_interpretation"] is None
    assert observation["human_review_required"] is True
    assert observation["causal_interpretation_provided"] is False
    assert observation["maintenance_recommendation_provided"] is False
    assert observation["evaluated_engineering_priors"] == [
        "pump_hydraulic_response",
        "other_equipment_response",
    ]
    assert observation["ignored_engineering_priors"][0]["id"] == (
        "other_equipment_response"
    )
    assert observation["analytical_uncertainty"] == evidence["uncertainty"]
    assert observation["processing_trace"]["weighted_scoring_performed"] is False
    assert result["processing_trace"]["voting_performed"] is False
    assert result["processing_trace"]["probability_estimated"] is False


def test_phase_3_runs_once_after_phase_2_and_extends_canonical_output() -> None:
    columns = ["timestamp", "flow_rate", "supply_pressure"]
    rows = []
    for index in range(120):
        wave = math.sin(index / 8.0)
        rows.append(
            {
                "timestamp": f"2026-01-01T{index // 60:02d}:{index % 60:02d}:00Z",
                "flow_rate": f"{100.0 + wave:.6f}",
                "supply_pressure": f"{40.0 + wave * 0.5:.6f}",
            }
        )
    profiles = [
        {
            "column": column,
            "constant_or_stuck": False,
            "missing_count": 0,
            "non_numeric_count": 0,
        }
        for column in columns[1:]
    ]
    prior = {
        "id": "configured_signal_evidence_available",
        "name": "Configured Signal Evidence Availability",
        "description": "Confirm the configured evidence source completed.",
        "domain": "generic",
        "equipment_types": [],
        "required_signals": ["flow_rate"],
        "required_relationships": [],
        "required_operating_modes": [],
        "prerequisites": [],
        "expected_behavior": {
            "conditions": [
                {
                    "source": "signal_drift",
                    "path": "status",
                    "operator": "eq",
                    "value": "complete",
                    "description": "Signal drift evidence completed.",
                }
            ]
        },
        "validity_conditions": [],
        "confidence_modifier": "unchanged",
        "limitations": ["This prior describes evidence availability only."],
        "reasoning_template": {
            "supported": "Configured signal evidence is available for human review.",
            "contradicted": "Configured signal evidence is not available.",
            "indeterminate": "Configured signal evidence availability is indeterminate.",
        },
    }

    result = evaluate_sii(
        columns=columns,
        rows=rows,
        numeric_profiles=profiles,
        timestamp_column="timestamp",
        config={
            "numeric_columns": columns[1:],
            "physics_reasoning_config": {"priors": [deepcopy(prior)]},
        },
    )

    trace = result["processing_trace"]
    assert trace["modules_attempted"].count("physics_reasoning") == 1
    assert trace["modules_attempted"].count("evidence_fusion") == 1
    assert trace["modules_attempted"].index("covariance_analysis") < (
        trace["modules_attempted"].index("physics_reasoning")
    )
    assert trace["modules_attempted"].index("physics_reasoning") < (
        trace["modules_attempted"].index("evidence_fusion")
    )
    assert trace["phase_3_active"] is True
    assert trace["phase_3_effect"] == "transparent_evidence_enrichment_only"
    assert trace["engineering_priors_evaluated"] == 1
    assert trace["engineering_observations_generated"] == 1
    assert result["physics_reasoning"]["supporting_priors"] == [
        "configured_signal_evidence_available"
    ]
    assert result["physics_evidence"] == result["physics_reasoning"]
    assert result["evidence_fusion"]["observations"][0]["human_review_required"] is True
    assert result["findings"] == []
