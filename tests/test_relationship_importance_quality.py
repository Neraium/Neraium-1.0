from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.analysis_explanations import build_analysis_explanation
from app.services.analysis_result_contract import build_analysis_result
from app.services.relationship_baselines import score_relationship_importance
from app.services.upload_jobs import process_csv_content


def _edge(**overrides):
    payload = {
        "correlation_delta": 0.62,
        "change_type": "weakened",
        "confidence_score": 0.9,
        "baseline_sample_size": 48,
        "recent_sample_size": 36,
        "baseline_strength": 0.92,
        "current_strength": 0.3,
    }
    payload.update(overrides)
    return payload


def _relationship(left, right, *, score=80.0, delta=0.62, change_type="weakened"):
    return {
        "relationship": f"{left} <-> {right}",
        "columns": [left, right],
        "correlation_delta": delta,
        "change_type": change_type,
        "confidence_score": 0.91,
        "baseline_sample_size": 40,
        "recent_sample_size": 40,
        "baseline_strength": 0.9,
        "current_strength": 0.28,
        "relationship_importance_score": score,
        "relationship_importance_rationale": "Important because equipment/process behavior changed with corroborating signals.",
        "ranking_factors": {"magnitude": delta, "equipment_process_involvement": 1.0},
        "evidence_refs": [{"column": left}, {"column": right}],
        "summary": f"{left} vs {right} relationship weakened.",
    }


def _occupancy_csv() -> bytes:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(240):
        ts = (start + timedelta(hours=index)).isoformat().replace("+00:00", "Z")
        if index < 120:
            occupancy = 12 + (index % 4)
            pump_power = 18 + ((index % 6) * 0.05)
            vibration = 0.10 + ((index % 5) * 0.002)
        else:
            occupancy = 86 + (index % 8)
            pump_power = 41 + ((index % 6) * 0.12)
            vibration = 0.54 + ((index % 5) * 0.006)
        rows.append(f"{ts},{occupancy:.3f},{pump_power:.3f},{vibration:.3f}")
    return ("timestamp,occupancy_load_pct,pump_power_kw,pump_vibration_ips\n" + "\n".join(rows)).encode("utf-8")


def test_occupancy_load_pct_is_context_and_supporting_evidence_not_top_anomaly() -> None:
    result = process_csv_content(
        filename="occupancy-context.csv",
        content=_occupancy_csv(),
        job_id="occupancycontext001",
    )

    occupancy = next(item for item in result["baseline_analysis"]["column_drift"] if item["column"] == "occupancy_load_pct")
    assert occupancy["telemetry_category"] == "scheduled_load_context"
    assert occupancy["analysis_role"] == "supporting_context"
    assert occupancy["drift_flag"] == "context"

    analysis = result["analysis_result"]
    titles = [insight["title"] for insight in analysis["insights"]]
    assert not any("occupancy" in title.lower() for title in titles)
    assert "occupancy_load_pct" in str(analysis["insights"])


def test_high_delta_context_only_relationship_is_down_ranked_below_equipment_relationship() -> None:
    context = score_relationship_importance(
        ["occupancy_load_pct", "production_rate"],
        _edge(correlation_delta=0.98, change_type="disrupted"),
        {},
    )
    equipment = score_relationship_importance(
        ["pump_power_kw", "pump_vibration_ips"],
        _edge(correlation_delta=0.48, change_type="weakened"),
        {
            "pump_power_kw": {"drift_flag": "review"},
            "pump_vibration_ips": {"drift_flag": "review"},
        },
    )

    assert context["relationship_importance_score"] < equipment["relationship_importance_score"]
    assert context["relationship_context"]["context_only"] is True
    assert equipment["ranking_factors"]["equipment_process_involvement"] == 1.0
    assert equipment["relationship_importance_rationale"]


def test_top_finding_is_selected_by_relationship_importance_not_raw_delta() -> None:
    context_only = _relationship("occupancy_load_pct", "production_rate", score=20.0, delta=0.99, change_type="disrupted")
    context_only["relationship_context"] = {"context_only": True, "equipment_process_involved": False, "context_driver_involved": True}
    context_only["column_classifications"] = [
        {"column": "occupancy_load_pct", "is_primary_anomaly_candidate": False},
        {"column": "production_rate", "is_primary_anomaly_candidate": False},
    ]
    equipment = _relationship("pump_power_kw", "pump_vibration_ips", score=86.0, delta=0.55)
    explanation = build_analysis_explanation(
        {
            "job_id": "importance-ranking",
            "timestamp_profile": {"first_timestamp": "2026-01-01T00:00:00Z", "last_timestamp": "2026-01-05T00:00:00Z"},
            "baseline_analysis": {"baseline_window_rows": 40, "recent_window_rows": 40, "columns_analyzed": 4, "column_drift": []},
            "relationship_model": {"top_relationship_changes": [context_only, equipment]},
        }
    )

    assert explanation["insights"][0]["relationship_importance_score"] == 86.0
    assert "occupancy" not in explanation["executive_summary"]["highest_priority_finding"].lower()


def test_duplicate_relationship_insights_are_merged_and_preserve_relationships() -> None:
    relationships = [
        _relationship("chw_supply_temp_f", "condenser_lwt_f", score=90.0),
        _relationship("ct_outlet_temp_f", "gt_ct_fouling_severity", score=84.0),
        _relationship("evap_entering_temp_f", "condenser_lwt_f", score=78.0),
    ]
    explanation = build_analysis_explanation(
        {
            "job_id": "relationship-dedupe",
            "timestamp_profile": {"first_timestamp": "2026-01-01T00:00:00Z", "last_timestamp": "2026-01-05T00:00:00Z"},
            "baseline_analysis": {"baseline_window_rows": 40, "recent_window_rows": 40, "columns_analyzed": 6, "column_drift": []},
            "relationship_model": {"top_relationship_changes": relationships},
        }
    )

    titles = [insight["title"] for insight in explanation["insights"]]
    assert titles.count("Thermal relationship changed") == 0
    merged = next(insight for insight in explanation["insights"] if insight["title"] == "Thermal response behavior changed")
    assert len(merged["contributing_relationships"]) == 3
    assert all(item["label"] for item in merged["contributing_relationships"])


def test_analysis_result_preserves_relationship_importance_fields() -> None:
    result = build_analysis_result(
        {
            "job_id": "importance-contract",
            "timestamp_profile": {"first_timestamp": "2026-01-01T00:00:00Z", "last_timestamp": "2026-01-05T00:00:00Z"},
            "baseline_analysis": {"baseline_window_rows": 40, "recent_window_rows": 40, "columns_analyzed": 2, "column_drift": []},
            "relationship_model": {"top_relationship_changes": [_relationship("pump_power_kw", "pump_vibration_ips", score=82.0)]},
        }
    )

    assert result["relationships"][0]["relationship_importance_score"] == 82.0
    assert result["relationships"][0]["relationship_importance_rationale"]
    assert result["relationships"][0]["ranking_factors"]
    assert result["insights"][0]["relationship_importance_score"] == 82.0
