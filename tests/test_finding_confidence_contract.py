from app.services.finding_classification import (
    CONTEXT_LIMITED_RELATIONSHIP_CHANGE,
    OBSERVED_CHANGE_UNDER_REVIEW,
    POSSIBLE_INSTRUMENTATION_ISSUE,
    UNEXPLAINED_SYSTEMIC_CHANGE,
    classify_finding,
)


def _relationship_evidence(**overrides: object) -> dict:
    return {
        "evidence_type": "linear_correlation",
        "baseline_correlation": 0.7,
        "recent_correlation": -0.1,
        "correlation_delta": 0.8,
        "baseline_sample_size": 24,
        "recent_sample_size": 12,
        "confidence_score": 0.9,
        "evidence_refs": ["relationship-window-1"],
        **overrides,
    }


def _healthy_signals() -> list[dict]:
    return [
        {"signal": "flow", "health": "healthy", "conditions": []},
        {"signal": "pressure", "health": "healthy", "conditions": []},
    ]


def _strong_mode() -> dict:
    return {
        "match": "strong",
        "confidence": "high",
        "reasons": ["Recorded load and equipment state matched."],
    }


def test_supported_sensor_hypothesis_is_not_buried_by_low_change_support() -> None:
    result = classify_finding(
        data_confidence={"rating": "low", "reasons": ["Relationship samples were sparse."]},
        sensor_health=[
            {
                "signal": "pressure",
                "health": "suspect",
                "conditions": [
                    {
                        "type": "flatline_or_stuck",
                        "severity": "review",
                        "evidence": "The pressure signal remained at one value.",
                    }
                ],
            }
        ],
        operating_mode=_strong_mode(),
        persistence={"status": "not_established", "persistent": False},
        relationship_evidence=_relationship_evidence(
            baseline_sample_size=2,
            recent_sample_size=2,
            confidence_score=0.2,
        ),
    )

    contract = result["finding_confidence_v1"]
    assert result["type"] == POSSIBLE_INSTRUMENTATION_ISSUE
    assert contract["change_detection"]["level"] == "low"
    assert contract["evidence_quality"]["level"] == "low"
    assert contract["interpretation"] == {
        "level": "medium",
        "reason": "pressure: The pressure signal remained at one value.",
        "method": "deterministic_finding_classification",
        "evidence_refs": ["relationship-window-1"],
        "attribution_status": "hypothesis",
    }


def test_measured_change_still_observing_has_maintenance_class_and_legacy_mapping() -> None:
    result = classify_finding(
        data_confidence={"rating": "high", "summary": "Recorded quality checks passed.", "reasons": []},
        sensor_health=_healthy_signals(),
        operating_mode=_strong_mode(),
        persistence={
            "status": "not_established",
            "persistent": False,
            "summary": "A follow-up comparison window is still required.",
        },
        relationship_evidence=_relationship_evidence(),
    )

    contract = result["finding_confidence_v1"]
    assert result["type"] == OBSERVED_CHANGE_UNDER_REVIEW
    assert result["label"] == "Observed change under review"
    assert result["legacy_classification"]["type"] == "insufficient_evidence"
    assert result["rule_version"] == "deterministic_finding_classification_v3"
    assert contract["persistence"]["status"] == "observing"
    assert contract["change_detection"]["level"] == "high"
    assert contract["interpretation"]["attribution_status"] == "unattributed"
    assert contract["interpretation"]["level"] == "unknown"


def test_confidence_dimensions_and_named_relationship_values_are_independent() -> None:
    result = classify_finding(
        data_confidence={"rating": "high", "summary": "Recorded quality checks passed.", "reasons": []},
        sensor_health=_healthy_signals(),
        operating_mode=_strong_mode(),
        persistence={"status": "persistent", "persistent": True, "summary": "Three windows support persistence."},
        relationship_evidence=_relationship_evidence(
            trajectory={"scope": "evidence_support", "state": "Strengthening"},
        ),
    )

    contract = result["finding_confidence_v1"]
    comparison = contract["relationship_comparison"]
    assert result["type"] == UNEXPLAINED_SYSTEMIC_CHANGE
    assert contract["schema_version"] == "finding-confidence-v1"
    assert contract["change_detection"]["level"] == "high"
    assert contract["interpretation"]["level"] == "unknown"
    assert contract["interpretation"]["attribution_status"] == "unattributed"
    assert contract["operating_context"]["status"] == "comparable"
    assert contract["evidence_quality"]["level"] == "high"
    assert contract["persistence"]["status"] == "persistent"
    assert comparison["metric"] == "pearson_correlation"
    assert comparison["baseline_value"] == 0.7
    assert comparison["current_value"] == -0.1
    assert round(comparison["signed_change"], 6) == -0.8
    assert round(comparison["absolute_change"], 6) == 0.8
    assert comparison["formula"] == (
        "signed_change = current_value - baseline_value; absolute_change = abs(signed_change)"
    )

    # Relationship direction describes the coefficient; support trend describes
    # how the body of evidence is changing. They may move in opposite directions.
    assert comparison["direction"] == "decreased"
    assert contract["support_trend"] == "increasing"


def test_high_confidence_change_with_different_context_keeps_change_and_cause_separate() -> None:
    result = classify_finding(
        data_confidence={"rating": "high", "summary": "Recorded quality checks passed."},
        sensor_health=_healthy_signals(),
        operating_mode={
            "match": "weak",
            "confidence": "high",
            "reasons": ["Recent demand differed from the baseline period."],
        },
        persistence={"status": "persistent", "persistent": True},
        relationship_evidence=_relationship_evidence(),
    )

    contract = result["finding_confidence_v1"]
    assert result["type"] == CONTEXT_LIMITED_RELATIONSHIP_CHANGE
    assert contract["change_detection"]["level"] == "high"
    assert contract["operating_context"]["status"] == "different_from_baseline"
    assert "level" not in contract["operating_context"]
    assert contract["interpretation"]["level"] == "unknown"
    assert contract["interpretation"]["attribution_status"] == "unattributed"


def test_alternative_reconciliation_distinguishes_unavailable_and_clear_sensor_checks() -> None:
    common = {
        "data_confidence": {"rating": "high", "reasons": []},
        "operating_mode": _strong_mode(),
        "persistence": {"status": "persistent", "persistent": True},
        "relationship_evidence": _relationship_evidence(),
    }
    unavailable = classify_finding(sensor_health=[], **common)
    checked = classify_finding(sensor_health=_healthy_signals(), **common)

    assert unavailable["alternative_explanations"][0] == (
        "Signal-health checks were unavailable for the affected signals."
    )
    assert checked["alternative_explanations"][0].startswith(
        "Recorded signal-health checks did not identify a supported instrumentation issue"
    )
    assert not any("establish" in item.lower() and "persistence" in item.lower() for item in checked["alternative_explanations"])
    assert not any("more persistence" in item.lower() for item in checked["alternative_explanations"])
