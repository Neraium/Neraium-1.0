import pytest

from app.services.pilot_benchmark import assert_no_future_leakage, match_findings_to_events
from app.services.pilot_metrics import build_pilot_metrics


def test_pilot_metrics_separate_candidates_suppressions_and_operator_outcomes() -> None:
    runs = [
        {
            "run_id": "one",
            "site_id": "site-a",
            "created_at": "2026-07-01T00:00:00Z",
            "completed_at": "2026-07-01T01:00:00Z",
            "rows_received": 100,
            "rows_accepted": 95,
            "condition_id": "condition-one",
            "observation_status": "investigating",
            "latest_feedback_category": "confirmed_issue",
            "phase_2_supporting_evidence": {
                "processing_trace": {
                    "mode_aware_authority": {"applied": False, "gates": {"candidate_present": True}}
                }
            },
        },
        {
            "run_id": "two",
            "site_id": "site-a",
            "created_at": "2026-07-08T00:00:00Z",
            "completed_at": "2026-07-08T01:00:00Z",
            "rows_received": 100,
            "rows_accepted": 100,
            "observation_status": "suppressed",
            "latest_feedback_category": "false_positive",
            "phase_2_supporting_evidence": {
                "processing_trace": {
                    "mode_aware_authority": {"applied": True, "gates": {"candidate_present": True}}
                }
            },
        },
    ]

    metrics = build_pilot_metrics(runs)

    assert metrics["candidate_findings"] == 2
    assert metrics["suppressed_candidates"] == 1
    assert metrics["surfaced_findings"] == 1
    assert metrics["useful_findings"] == 1
    assert metrics["irrelevant_findings"] == 1
    assert metrics["irrelevant_finding_rate"] == 0.5
    assert metrics["data_coverage_rate"] == 0.975


def test_chronological_event_matching_reports_lead_time_and_context() -> None:
    findings = [
        {
            "finding_id": "flow-change",
            "detected_at": "2026-07-01T06:00:00Z",
            "source_window_end": "2026-07-01T06:00:00Z",
            "system_id": "chw-loop",
            "signals": ["flow", "pump_speed"],
        },
        {
            "finding_id": "other-system",
            "detected_at": "2026-07-01T05:00:00Z",
            "source_window_end": "2026-07-01T05:00:00Z",
            "system_id": "condenser-loop",
            "signals": ["flow"],
        },
    ]
    events = [
        {
            "event_id": "alarm-1",
            "event_at": "2026-07-01T18:00:00Z",
            "system_id": "chw-loop",
            "related_signals": "flow|differential_pressure",
        }
    ]

    result = match_findings_to_events(findings, events, max_lead_hours=48)

    assert result["events_matched"] == 1
    assert result["events_detected_earlier"] == 1
    assert result["median_lead_time_hours"] == 12
    assert result["matches"][0]["finding_id"] == "flow-change"
    assert result["unmatched_finding_ids"] == ["other-system"]


def test_future_rows_are_rejected_from_benchmark() -> None:
    with pytest.raises(ValueError, match="future_data_leakage"):
        assert_no_future_leakage(
            [{
                "finding_id": "leaky",
                "detected_at": "2026-07-01T06:00:00Z",
                "source_window_end": "2026-07-01T07:00:00Z",
            }]
        )
