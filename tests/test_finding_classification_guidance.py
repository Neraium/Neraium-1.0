import json
import re
from pathlib import Path

import pytest

from app.services.analysis_explanations import ensure_finding_context
from app.services.finding_classification import (
    CONTEXT_LIMITED_RELATIONSHIP_CHANGE,
    INSUFFICIENT_EVIDENCE,
    classify_finding,
)
from app.services.investigation_guidance import (
    SUPPORTED_GUIDANCE_CATEGORIES,
    build_investigation_guidance,
)


ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = json.loads((ROOT / "tests/fixtures/finding_classification_scenarios.json").read_text())
EXAMPLES = json.loads((ROOT / "docs/validation/finding-classification-examples.json").read_text())


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda item: item["id"])
def test_representative_classifications_and_guidance_are_valid(scenario: dict) -> None:
    classification = classify_finding(
        data_confidence=scenario["data_confidence"],
        sensor_health=scenario["sensor_health"],
        operating_mode=scenario["operating_mode"],
        persistence=scenario["persistence"],
        relationship_evidence=scenario["relationship_evidence"],
    )
    guidance = build_investigation_guidance(
        classification=classification,
        existing_guidance=[
            "Inspect the relevant monitored boundary.",
            "Review the contributing signal trends.",
        ],
        source_signals=["pump_speed", "discharge_pressure"],
        operating_mode=scenario["operating_mode"],
        data_confidence=scenario["data_confidence"],
        sensor_health=scenario["sensor_health"],
        relationship_evidence=scenario["relationship_evidence"],
        persistence=scenario["persistence"],
    )

    assert classification["type"] == scenario["expected_classification"]
    assert classification["label"]
    assert classification["confidence"] in {"low", "limited", "high"}
    assert classification["reasons"]
    assert classification["alternative_explanations"]
    assert classification["certainty_limit"]
    assert len(guidance) <= 3
    assert [item["rank"] for item in guidance] == list(range(1, len(guidance) + 1))
    assert all(item["check"] and item["reason"] for item in guidance)
    assert all(item["editable"] is True for item in guidance)
    assert all(item["category"] in SUPPORTED_GUIDANCE_CATEGORIES for item in guidance)


@pytest.mark.parametrize(
    ("classification_type", "expected_categories"),
    [
        ("known_operational_change", ["operating_context", "controls", "operating_context"]),
        ("possible_instrumentation_issue", ["instrumentation", "instrumentation", "data_quality"]),
        ("unexplained_systemic_change", ["data_quality", "operating_context", "physical_system"]),
        ("insufficient_evidence", ["data_quality", "data_quality", "operating_context"]),
    ],
)
def test_representative_guidance_order_matches_classification(
    classification_type: str,
    expected_categories: list[str],
) -> None:
    example = EXAMPLES[classification_type]

    assert [item["category"] for item in example["investigation_guidance"]] == expected_categories
    assert example["recommended_first_check"] == example["investigation_guidance"][0]["check"]


def test_low_data_and_weak_mode_each_block_systemic_classification() -> None:
    base = {
        "sensor_health": [{"signal": "a", "health": "healthy", "conditions": []}],
        "persistence": {"persistent": True},
        "relationship_evidence": {
            "baseline_sample_size": 20,
            "recent_sample_size": 10,
            "confidence_score": 0.9,
            "correlation_delta": 0.6,
        },
    }
    low_data = classify_finding(
        **base,
        data_confidence={"rating": "low", "reasons": ["Sampling was irregular."]},
        operating_mode={"match": "strong", "confidence": "high"},
    )
    weak_mode = classify_finding(
        **base,
        data_confidence={"rating": "high", "reasons": []},
        operating_mode={"match": "weak", "confidence": "high", "known_operational_change": False},
    )

    assert low_data["type"] == INSUFFICIENT_EVIDENCE
    assert weak_mode["type"] == CONTEXT_LIMITED_RELATIONSHIP_CHANGE


def test_instrumentation_wording_is_cautious_and_checks_are_capped() -> None:
    example = EXAMPLES["possible_instrumentation_issue"]
    wording = json.dumps(example).lower()

    assert "possible instrumentation issue" in wording
    assert "does not confirm that a sensor or transmitter is faulty" in wording
    assert len(example["investigation_guidance"]) == 3
    assert example["investigation_guidance"][0]["category"] == "instrumentation"


def test_legacy_findings_default_to_insufficient_evidence_with_structured_guidance() -> None:
    legacy = ensure_finding_context(
        [
            {
                "id": "legacy-finding",
                "title": "Historical relationship observation",
                "what_changed": "A relationship changed in the historical analysis.",
                "recommended_check": "Review the original operator notes.",
                "activity_timeline": [
                    {
                        "event_type": "operating_mode_event",
                        "title": "Recorded schedule note",
                        "period_label": "Historical comparison window",
                        "precision": "period",
                    }
                ],
            }
        ],
        {},
    )[0]

    assert legacy["classification"]["type"] == INSUFFICIENT_EVIDENCE
    assert legacy["data_confidence"]["rating"] == "low"
    assert legacy["operating_mode"]["match"] == "unavailable"
    assert legacy["investigation_guidance"][0]["category"] == "data_quality"
    assert legacy["recommended_first_action"] == legacy["investigation_guidance"][0]["check"]
    assert legacy["activity_timeline"][0]["title"] == "Recorded schedule note"
    assert legacy["activity_timeline"][0]["period_label"] == "Historical comparison window"


def test_stale_known_operational_classification_is_revalidated() -> None:
    finding = ensure_finding_context(
        [
            {
                "id": "stale-known",
                "classification": {
                    "type": "known_operational_change",
                    "label": "Known operational change",
                    "rule_version": "deterministic_finding_classification_v1",
                },
                "data_confidence": {"rating": "limited", "reasons": ["Coverage is limited."]},
                "operating_mode": {
                    "match": "weak",
                    "confidence": "limited",
                    "known_operational_change": True,
                    "differences": [{"feature": "load_band", "reason": "Load band differed."}],
                },
                "persistence": {"persistent": False, "status": "not_established"},
                "relationship_evidence": {
                    "baseline_sample_size": 12,
                    "recent_sample_size": 12,
                    "confidence_score": 0.55,
                    "correlation_delta": 0.6,
                },
            }
        ],
        {},
    )[0]

    assert finding["classification"]["type"] == CONTEXT_LIMITED_RELATIONSHIP_CHANGE
    assert finding["classification"]["rule_version"] == "deterministic_finding_classification_v3"


def test_examples_have_no_unsupported_failure_or_cause_claims() -> None:
    text = json.dumps(EXAMPLES).lower()
    unsupported = (
        r"\bthe cause is\b",
        r"\bcaused by\b",
        r"\bis failing\b",
        r"\bwill fail\b",
        r"\bexact failure date\b",
        r"\breplace the\b",
        r"\brepair the\b",
    )

    assert not any(re.search(pattern, text) for pattern in unsupported)
    assert EXAMPLES["insufficient_evidence"]["classification"]["confidence"] == "low"
    assert "recorded context change" in EXAMPLES["known_operational_change"]["engineer_wording"]["what_changed"]
    assert "possible instrumentation issue" in EXAMPLES["possible_instrumentation_issue"]["engineer_wording"]["what_changed"]


def test_example_timelines_use_only_source_ranges_or_labeled_periods() -> None:
    allowed_periods = {"Recent comparison window"}
    for example in EXAMPLES.values():
        for event in example["relationship_timeline"]:
            has_source_time = bool(event.get("time") or event.get("start") or event.get("end"))
            has_supported_period = event.get("period_label") in allowed_periods
            assert has_source_time or has_supported_period
            assert event.get("event_type")
            assert "day" not in str(event.get("time", "")).lower()
