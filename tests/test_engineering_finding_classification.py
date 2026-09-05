from app.services.finding_classification import (
    CONTEXT_LIMITED_RELATIONSHIP_CHANGE,
    INSUFFICIENT_EVIDENCE,
    KNOWN_OPERATIONAL_CHANGE,
    POSSIBLE_INSTRUMENTATION_ISSUE,
    UNEXPLAINED_SYSTEMIC_CHANGE,
    classify_finding,
)
from app.services.analysis_explanations import build_analysis_explanation
from app.services.analysis_result_contract import build_analysis_result
from app.services.operating_modes import assess_operating_modes
from app.services.sensor_health import assess_sensor_health, build_data_confidence


def _rows(*, stage_change: bool, include_context: bool = True) -> list[dict[str, str]]:
    rows = []
    for index in range(30):
        row = {
            "timestamp": f"2026-07-06T{8 + (index // 20):02d}:{index % 20:02d}:00Z",
            "flow": str(100 + index),
            "pressure": str(50 + index / 2),
        }
        if include_context:
            row["pump_stage"] = "1" if not stage_change or index < 21 else "2"
            row["occupancy_load_pct"] = "70"
        rows.append(row)
    return rows


def test_operating_mode_detects_equipment_stage_change_deterministically() -> None:
    rows = _rows(stage_change=True)

    first = assess_operating_modes(rows, timestamp_column="timestamp")
    second = assess_operating_modes(rows, timestamp_column="timestamp")

    assert first == second
    assert first["match"] == "weak"
    assert first["known_operational_change"] is True
    assert any(item["feature"] == "equipment_state" for item in first["differences"])


def test_operating_mode_allows_like_for_like_relationship_evaluation() -> None:
    assessment = assess_operating_modes(_rows(stage_change=False), timestamp_column="timestamp")

    assert assessment["match"] == "strong"
    assert assessment["confidence"] == "high"
    assert assessment["known_operational_change"] is False


def test_operating_mode_derives_active_unit_count_from_status_signals() -> None:
    rows = _rows(stage_change=False)
    for index, row in enumerate(rows):
        row.pop("pump_stage")
        row["pump_a_enabled"] = "1"
        row["pump_b_enabled"] = "0" if index < 21 else "1"

    assessment = assess_operating_modes(rows, timestamp_column="timestamp")

    assert assessment["features"]["baseline"]["active_unit_count"] == 1
    assert assessment["features"]["recent"]["active_unit_count"] == 2
    assert assessment["match"] == "weak"


def test_operating_mode_is_honest_when_context_signals_are_missing() -> None:
    assessment = assess_operating_modes(
        _rows(stage_change=False, include_context=False),
        timestamp_column="timestamp",
    )

    assert assessment["match"] == "unavailable"
    assert assessment["confidence"] == "low"
    assert assessment["features"]["baseline"]["time_band"] == "day"


def _quality(*, reliability: str = "strong", baseline_reliable: bool = True) -> dict:
    return {
        "readiness": "ready",
        "reliability_rating": reliability,
        "quality_metrics": {"baseline_reliable": baseline_reliable},
        "normalization_report": {"window_suppressed": False},
    }


def test_sensor_health_marks_a_stuck_signal_without_claiming_physical_change() -> None:
    rows = [
        {"timestamp": f"2026-07-06T08:{index:02d}:00Z", "pressure": "42.0", "flow": str(100 + index)}
        for index in range(20)
    ]
    health = assess_sensor_health(
        rows,
        ["pressure", "flow"],
        timestamp_column="timestamp",
        numeric_profiles=[
            {"column": "pressure", "constant_or_stuck": True},
            {"column": "flow", "constant_or_stuck": False},
        ],
    )

    pressure = next(item for item in health["signals"] if item["signal"] == "pressure")
    confidence = build_data_confidence(_quality(), health, affected_signals=["pressure", "flow"])

    assert pressure["health"] == "suspect"
    assert pressure["conditions"][0]["type"] == "flatline_or_stuck"
    assert confidence["rating"] == "limited"
    assert confidence["affected_signals"] == ["pressure"]


def test_sensor_health_detects_gradual_divergence_from_a_strong_peer() -> None:
    rows = []
    for index in range(40):
        reference = 50 + (index % 5)
        drift = 0 if index < 28 else (index - 27) * 0.8
        rows.append(
            {
                "reference_pressure": str(reference),
                "discharge_pressure": str(reference + drift),
            }
        )
    relationship_model = {
        "baseline_relationships": [
            {
                "relationship": "reference_pressure <-> discharge_pressure",
                "baseline_correlation": 1.0,
            }
        ]
    }

    health = assess_sensor_health(
        rows,
        ["reference_pressure", "discharge_pressure"],
        relationship_model=relationship_model,
    )

    assert any(
        condition["type"] == "possible_drift"
        for signal in health["signals"]
        for condition in signal["conditions"]
    )


def test_sensor_health_detects_timestamp_offset_between_related_signals() -> None:
    pattern = [0, 1, 4, 2, 5, 3, 8, 6, 9, 7, 12, 10, 13, 11, 16, 14, 17, 15, 20, 18]
    rows = []
    for index in range(40):
        value = pattern[index % len(pattern)]
        shifted = pattern[(index - 1) % len(pattern)]
        rows.append({"signal_a": str(value), "signal_b": str(value if index < 28 else shifted)})
    model = {
        "baseline_relationships": [
            {
                "relationship": "signal_a <-> signal_b",
                "baseline_correlation": 1.0,
            }
        ]
    }

    health = assess_sensor_health(rows, ["signal_a", "signal_b"], relationship_model=model)

    assert any(
        condition["type"] == "timestamp_misalignment"
        for signal in health["signals"]
        for condition in signal["conditions"]
    )


def _relationship_evidence() -> dict:
    return {
        "baseline_sample_size": 24,
        "recent_sample_size": 12,
        "confidence_score": 0.9,
        "correlation_delta": 0.7,
    }


def _healthy_signals() -> list[dict]:
    return [
        {"signal": "flow", "health": "healthy", "conditions": []},
        {"signal": "pressure", "health": "healthy", "conditions": []},
    ]


def test_normal_stage_change_classifies_as_known_operational_change() -> None:
    mode = assess_operating_modes(_rows(stage_change=True), timestamp_column="timestamp")

    classification = classify_finding(
        data_confidence={"rating": "high", "reasons": []},
        sensor_health=_healthy_signals(),
        operating_mode=mode,
        persistence={"persistent": True},
        relationship_evidence=_relationship_evidence(),
    )

    assert classification["type"] == KNOWN_OPERATIONAL_CHANGE
    assert "causality" in classification["certainty_limit"]


def test_stuck_signal_classifies_as_possible_instrumentation_issue() -> None:
    classification = classify_finding(
        data_confidence={"rating": "limited", "reasons": []},
        sensor_health=[
            {
                "signal": "pressure",
                "health": "suspect",
                "conditions": [
                    {
                        "type": "flatline_or_stuck",
                        "severity": "review",
                        "evidence": "The signal remained at one value.",
                    }
                ],
            }
        ],
        operating_mode={"match": "strong", "confidence": "high", "reasons": []},
        persistence={"persistent": True},
        relationship_evidence=_relationship_evidence(),
    )

    assert classification["type"] == POSSIBLE_INSTRUMENTATION_ISSUE
    assert classification["confidence"] == "limited"


def test_persistent_same_mode_change_classifies_as_unexplained_systemic_change() -> None:
    inputs = {
        "data_confidence": {"rating": "high", "reasons": []},
        "sensor_health": _healthy_signals(),
        "operating_mode": {
            "match": "strong",
            "confidence": "high",
            "reasons": ["Available operating context matched."],
        },
        "persistence": {"persistent": True, "summary": "The change persisted across recent evidence."},
        "relationship_evidence": _relationship_evidence(),
    }

    first = classify_finding(**inputs)
    second = classify_finding(**inputs)

    assert first == second
    assert first["type"] == UNEXPLAINED_SYSTEMIC_CHANGE
    assert first["confidence"] == "high"
    assert "does not diagnose cause" in first["certainty_limit"]


def test_weak_data_or_missing_mode_prevents_systemic_classification() -> None:
    low_data = classify_finding(
        data_confidence={"rating": "low", "reasons": ["Sampling was irregular."]},
        sensor_health=_healthy_signals(),
        operating_mode={"match": "strong", "confidence": "high"},
        persistence={"persistent": True},
        relationship_evidence=_relationship_evidence(),
    )
    missing_mode = classify_finding(
        data_confidence={"rating": "high", "reasons": []},
        sensor_health=_healthy_signals(),
        operating_mode={"match": "unavailable", "confidence": "low"},
        persistence={"persistent": True},
        relationship_evidence=_relationship_evidence(),
    )

    assert low_data["type"] == INSUFFICIENT_EVIDENCE
    assert missing_mode["type"] == CONTEXT_LIMITED_RELATIONSHIP_CHANGE


def test_partial_band_match_is_context_limited_without_direct_evidence() -> None:
    classification = classify_finding(
        data_confidence={"rating": "high", "reasons": []},
        sensor_health=_healthy_signals(),
        operating_mode={
            "match": "partial",
            "confidence": "high",
            "known_operational_change": True,
            "differences": [{"feature": "load_band", "reason": "Load band changed."}],
        },
        persistence={"persistent": True},
        relationship_evidence=_relationship_evidence(),
    )

    assert classification["type"] == CONTEXT_LIMITED_RELATIONSHIP_CHANGE
    assert classification["confidence"] == "limited"


def test_limited_data_and_weak_mode_require_separate_direct_context_evidence() -> None:
    inputs = {
        "data_confidence": {"rating": "limited", "reasons": ["Coverage is limited."]},
        "sensor_health": _healthy_signals(),
        "operating_mode": {
            "match": "weak",
            "confidence": "limited",
            "known_operational_change": True,
            "differences": [{"feature": "equipment_state", "reason": "Equipment state differed."}],
        },
        "persistence": {"persistent": False},
        "relationship_evidence": _relationship_evidence(),
    }

    bounded = classify_finding(**inputs)
    direct = classify_finding(
        **inputs,
        known_operational_evidence=["Operator log records a staging change in the evidence window."],
    )

    assert bounded["type"] == CONTEXT_LIMITED_RELATIONSHIP_CHANGE
    assert direct["type"] == KNOWN_OPERATIONAL_CHANGE
    assert direct["confidence"] == "limited"


def test_maintenance_event_is_available_as_known_operational_context() -> None:
    rows = _rows(stage_change=False)
    for index, row in enumerate(rows):
        row["maintenance_event"] = "0" if index < 21 else "1"

    mode = assess_operating_modes(rows, timestamp_column="timestamp")
    classification = classify_finding(
        data_confidence={"rating": "high", "reasons": []},
        sensor_health=_healthy_signals(),
        operating_mode=mode,
        persistence={"persistent": True},
        relationship_evidence=_relationship_evidence(),
    )

    assert any(item["feature"] == "maintenance_state" for item in mode["differences"])
    assert classification["type"] == KNOWN_OPERATIONAL_CHANGE


def _explanation_context(
    *,
    mode: dict,
    data_confidence: dict,
    sensor_health: list[dict],
    persistent: bool = True,
) -> dict:
    relationship = {
        "relationship": "pump_speed <-> discharge_pressure",
        "display_columns": ["Pump speed", "Discharge pressure"],
        "change_type": "weakened",
        "correlation_delta": 0.72,
        "baseline_correlation": 0.9,
        "recent_correlation": 0.18,
        "coupling_strength": 0.9,
        "baseline_strength": 0.9,
        "current_strength": 0.18,
        "baseline_sample_size": 24,
        "recent_sample_size": 12,
        "confidence_score": 0.9,
        "operating_mode": mode,
        "data_confidence": data_confidence,
        "sensor_health": sensor_health,
    }
    result = {
        "job_id": "classification-explanation",
        "run_id": "classification-explanation",
        "upload_id": "classification-explanation",
        "filename": "classification.csv",
        "timestamp_profile": {
            "first_timestamp": "2026-07-01T08:00:00Z",
            "last_timestamp": "2026-07-01T12:00:00Z",
        },
        "baseline_analysis": {
            "overall_assessment": "needs_review",
            "baseline_window_rows": 24,
            "recent_window_rows": 12,
            "columns_analyzed": 2,
            "column_drift": [],
            "warnings": [],
        },
        "relationship_model": {
            "top_relationship_changes": [relationship],
            "baseline_relationships": [relationship],
            "relationship_graph": {},
            "operating_mode": mode,
        },
        "data_quality": {
            "readiness": "ready",
            "reliability_rating": "strong" if data_confidence["rating"] == "high" else "usable",
            "data_confidence": data_confidence,
            "operating_mode": mode,
            "sensor_health": sensor_health,
            "warnings": [],
        },
        "engine_result": {
            "persistence_assessment": {
                "persistent_columns": ["pump_speed", "discharge_pressure"] if persistent else []
            }
        },
        "operator_report": {"recommended_operator_checks": ["Review the source evidence."]},
        "sii_intelligence": {"facility_state": "needs_review"},
    }
    result["analysis_explanation"] = build_analysis_explanation(result)
    return result


def test_explanation_layer_uses_classification_specific_cautious_wording() -> None:
    cases = [
        (
            {
                "baseline_mode": "one_unit",
                "baseline_mode_label": "One-unit operation",
                "recent_mode": "two_units",
                "recent_mode_label": "Two-unit operation",
                "match": "weak",
                "confidence": "high",
                "known_operational_change": True,
                "differences": [{"feature": "equipment_state", "reason": "Equipment stage changed."}],
                "reasons": ["Equipment stage changed."],
            },
            {"rating": "high", "reasons": [], "affected_signals": []},
            _healthy_signals(),
            KNOWN_OPERATIONAL_CHANGE,
            "recorded context change occurred in the same evidence window",
        ),
        (
            {"match": "strong", "confidence": "high", "reasons": ["Operating context matched."]},
            {"rating": "limited", "reasons": ["Signal validation is needed."], "affected_signals": ["discharge_pressure"]},
            [
                {
                    "signal": "discharge_pressure",
                    "health": "suspect",
                    "conditions": [
                        {
                            "type": "possible_drift",
                            "severity": "review",
                            "evidence": "The signal gradually diverged from a redundant pressure measurement.",
                        }
                    ],
                }
            ],
            POSSIBLE_INSTRUMENTATION_ISSUE,
            "possible instrumentation issue",
        ),
        (
            {"match": "strong", "confidence": "high", "reasons": ["Operating context matched."]},
            {"rating": "high", "reasons": [], "affected_signals": []},
            _healthy_signals(),
            UNEXPLAINED_SYSTEMIC_CHANGE,
            "no recorded operating change explains the shift",
        ),
        (
            {"match": "strong", "confidence": "high", "reasons": ["Operating context matched."]},
            {"rating": "low", "reasons": ["Sampling was irregular."], "affected_signals": []},
            _healthy_signals(),
            INSUFFICIENT_EVIDENCE,
            "prevents a reliable interpretation",
        ),
    ]

    for mode, confidence, health, expected_type, wording in cases:
        result = _explanation_context(mode=mode, data_confidence=confidence, sensor_health=health)
        insight = result["analysis_explanation"]["insights"][0]

        assert insight["classification"]["type"] == expected_type
        assert wording in insight["what_changed"]
        assert insight["operating_mode"]["match"]
        assert insight["data_confidence"]["rating"]
        assert insight["persistence"]["status"]
        assert insight["relationship_evidence"]["baseline_sample_size"] == 24
        assert insight["activity_timeline"]
        assert insight["certainty_limit"]
        assert not any(
            phrase in f"{insight['what_changed']} {insight['behavior_interpretation']}".lower()
            for phrase in ("the pump is failing", "definitely a", "will fail on", "exact failure date")
        )


def test_canonical_result_preserves_new_finding_fields_and_legacy_fields() -> None:
    result = _explanation_context(
        mode={"match": "strong", "confidence": "high", "reasons": ["Operating context matched."]},
        data_confidence={"rating": "high", "reasons": [], "affected_signals": []},
        sensor_health=_healthy_signals(),
    )
    analysis = build_analysis_result(result)
    insight = analysis["insights"][0]
    relationship = analysis["relationships"][0]

    assert set(insight) >= {
        "classification",
        "finding_confidence_v1",
        "relationship_comparison",
        "operating_mode",
        "data_confidence",
        "sensor_health",
        "certainty_limit",
        "persistence",
        "relationship_evidence",
        "activity_timeline",
        "investigation_guidance",
        "what_changed",
        "why_it_matters",
        "evidence_refs",
    }
    assert "likely_cause" not in insight
    assert not insight.get("recommended_check")
    assert insight["investigation_guidance"]
    assert insight["finding_confidence_v1"]["schema_version"] == "finding-confidence-v1"
    assert insight["relationship_comparison"] == insight["finding_confidence_v1"]["relationship_comparison"]
    assert insight["relationship_comparison"]["baseline_value"] == 0.9
    assert insight["relationship_comparison"]["current_value"] == 0.18
    assert round(insight["relationship_comparison"]["signed_change"], 6) == -0.72
    assert round(insight["relationship_comparison"]["absolute_change"], 6) == 0.72
    assert relationship["relationship_comparison"] == insight["relationship_comparison"]
    assert round(relationship["signed_change"], 6) == -0.72
    assert round(relationship["absolute_change"], 6) == 0.72
    assert relationship["relationship_direction"] == "decreased"
    assert insight["recommended_first_action"] == insight["investigation_guidance"][0]["check"]
    assert all(item["reason"] and item["category"] and item["editable"] is True for item in insight["investigation_guidance"])
