from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.analysis_explanations import build_analysis_explanation, relationship_subsystem_name
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


def _relationship(left, right, *, score=80.0, delta=0.62, change_type="weakened", confidence_score=0.91, summary=None):
    return {
        "relationship": f"{left} <-> {right}",
        "columns": [left, right],
        "correlation_delta": delta,
        "change_type": change_type,
        "confidence_score": confidence_score,
        "baseline_sample_size": 40,
        "recent_sample_size": 40,
        "baseline_strength": 0.9,
        "current_strength": 0.28,
        "relationship_importance_score": score,
        "relationship_importance_rationale": "Important because equipment/process behavior changed with corroborating signals.",
        "ranking_factors": {"magnitude": delta, "equipment_process_involvement": 1.0},
        "evidence_refs": [{"column": left}, {"column": right}],
        "summary": summary or f"{left} and {right} relationship weakened against the historical operating pattern.",
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
        _relationship("supply_temp_f", "return_temp_f", score=84.0),
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
    merged = next(insight for insight in explanation["insights"] if insight["title"] == "Thermal Transfer Subsystem behavior changed")
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


def test_relationship_stats_stay_out_of_main_insight_contract_and_remain_in_evidence() -> None:
    raw_summary = "pump_power_kw vs flow_rate_gpm relationship weakened: baseline strength=0.900, current strength=0.200, correlation delta=0.700."
    result = build_analysis_result(
        {
            "job_id": "operator-language-contract",
            "timestamp_profile": {"first_timestamp": "2026-01-01T00:00:00Z", "last_timestamp": "2026-01-05T00:00:00Z"},
            "baseline_analysis": {"baseline_window_rows": 40, "recent_window_rows": 40, "columns_analyzed": 2, "column_drift": []},
            "relationship_model": {"top_relationship_changes": [_relationship("pump_power_kw", "flow_rate_gpm", summary=raw_summary)]},
        }
    )

    main_insights = str(result["insights"]).lower()
    assert "correlation delta" not in main_insights
    assert "confidence score" not in main_insights
    assert "operational support from confidence" not in main_insights
    assert "correlation delta" in str(result["evidence_index"]).lower()
    assert "correlation_delta" in str(result["evidence_index"]).lower()


def test_subsystem_names_match_dominant_telemetry_groups() -> None:
    assert relationship_subsystem_name(["pump_power_kw", "main_pressure_psi", "flow_rate_gpm"]) == "Flow / Pressure Subsystem"
    assert relationship_subsystem_name(["chlorine_dose_ppm", "turbidity_ntu", "orp_mv"]) == "Chemical Feed / Water Quality Subsystem"
    assert relationship_subsystem_name(["wet_well_level_ft", "pump_status", "flow_rate_gpm"]) == "Lift Station Operations"
    assert relationship_subsystem_name(["supply_temp_f", "return_temp_f", "condenser_lwt_f"]) == "Thermal Transfer Subsystem"


def test_low_confidence_or_ambiguous_subsystem_naming_falls_back_to_observed_behavior() -> None:
    assert relationship_subsystem_name(["source_temperature_f", "main_pressure_psi"]) == "Observed subsystem behavior changed"

    explanation = build_analysis_explanation(
        {
            "job_id": "low-confidence-subsystem",
            "timestamp_profile": {"first_timestamp": "2026-01-01T00:00:00Z", "last_timestamp": "2026-01-05T00:00:00Z"},
            "baseline_analysis": {"baseline_window_rows": 5, "recent_window_rows": 5, "columns_analyzed": 2, "column_drift": []},
            "relationship_model": {"top_relationship_changes": [_relationship("source_temperature_f", "main_pressure_psi", confidence_score=0.2)]},
        }
    )

    assert explanation["insights"][0]["title"] == "Observed subsystem behavior changed"
    assert explanation["insights"][0]["affected_systems"] == ["Observed subsystem behavior changed"]


def test_relationship_clusters_use_dominant_group_and_merge_related_findings() -> None:
    relationships = [
        _relationship("pump_power_kw", "chlorine_dose_ppm", score=92.0),
        _relationship("main_pressure_psi", "chlorine_dose_ppm", score=88.0),
        _relationship("pump_speed_hz", "chlorine_dose_ppm", score=86.0),
    ]
    explanation = build_analysis_explanation(
        {
            "job_id": "flow-chemical-cluster",
            "timestamp_profile": {"first_timestamp": "2026-01-01T00:00:00Z", "last_timestamp": "2026-01-05T00:00:00Z"},
            "baseline_analysis": {"baseline_window_rows": 40, "recent_window_rows": 40, "columns_analyzed": 4, "column_drift": []},
            "relationship_model": {"top_relationship_changes": relationships},
        }
    )

    assert explanation["insights"][0]["title"] == "Flow / Pressure Subsystem behavior changed"
    assert explanation["insights"][0]["affected_systems"] == ["Flow / Pressure Subsystem"]
    assert len(explanation["insights"][0]["contributing_relationships"]) == 3


def test_individual_variable_changes_are_down_ranked_when_relationship_changes_exist() -> None:
    explanation = build_analysis_explanation(
        {
            "job_id": "relationship-before-metric",
            "timestamp_profile": {"first_timestamp": "2026-01-01T00:00:00Z", "last_timestamp": "2026-01-05T00:00:00Z"},
            "baseline_analysis": {
                "baseline_window_rows": 40,
                "recent_window_rows": 40,
                "columns_analyzed": 3,
                "column_drift": [
                    {"column": "turbidity_ntu", "direction": "up", "drift_flag": "review", "percent_change": 194},
                    {"column": "chlorine_dose_ppm", "direction": "up", "drift_flag": "review", "percent_change": 42},
                ],
            },
            "relationship_model": {"top_relationship_changes": [_relationship("chlorine_dose_ppm", "turbidity_ntu", score=91.0)]},
        }
    )

    assert explanation["insights"][0]["title"] == "Chemical Feed / Water Quality Subsystem behavior changed"
    assert not any(insight["title"].lower().startswith("turbidity") for insight in explanation["insights"])


def test_raw_csv_tags_remain_available_in_evidence() -> None:
    result = build_analysis_result(
        {
            "job_id": "raw-tag-evidence",
            "timestamp_profile": {"first_timestamp": "2026-01-01T00:00:00Z", "last_timestamp": "2026-01-05T00:00:00Z"},
            "baseline_analysis": {"baseline_window_rows": 40, "recent_window_rows": 40, "columns_analyzed": 2, "column_drift": []},
            "relationship_model": {"top_relationship_changes": [_relationship("chlorine_dose_ppm", "turbidity_ntu", score=91.0)]},
        }
    )

    refs = result["insights"][0]["evidence_refs"]
    evidence_tags = {tag for ref in refs for tag in result["evidence_index"][ref]["source_tags"]}
    assert {"chlorine_dose_ppm", "turbidity_ntu"}.issubset(evidence_tags)
