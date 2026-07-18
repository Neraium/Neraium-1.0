from __future__ import annotations

from app.services.analysis_explanations import build_analysis_explanation
from app.services.upload_jobs import process_csv_content


def _analysis_quality_csv() -> bytes:
    rows = []
    for index in range(240):
        timestamp = f"2026-06-01T{index // 60:02d}:{index % 60:02d}:00Z"
        meter = 10000 + (index * 11)
        vibration = 0.10 if index < 120 else 0.54
        supply_pressure = 78.0 + ((index % 5) * 0.1)
        fouling = 0.2 + (index * 0.004)
        if index < 168:
            ct_outlet = 70 + (fouling * 18)
        else:
            ct_outlet = 93 - (fouling * 12)
        if index == 50:
            vibration_value = ""
            pressure_value = ""
        else:
            vibration_value = f"{vibration:.3f}"
            pressure_value = f"{supply_pressure:.2f}"
        rows.append(
            ",".join(
                [
                    timestamp,
                    str(meter),
                    vibration_value,
                    f"{ct_outlet:.3f}",
                    f"{fouling:.3f}",
                    pressure_value,
                ]
            )
        )
    header = "timestamp,meter_cumulative_gal,pump_vibration_ips,ct_outlet_temp_f,gt_ct_fouling_severity,supply_pressure_psi"
    return (header + "\n" + "\n".join(rows)).encode("utf-8")


def test_analysis_explanation_builds_operator_interpretation_report() -> None:
    analysis = build_analysis_explanation(
        {
            "job_id": "operatorinterpretation001",
            "timestamp_profile": {
                "first_timestamp": "2026-06-01T00:00:00Z",
                "last_timestamp": "2026-06-01T04:00:00Z",
            },
            "baseline_analysis": {
                "overall_assessment": "needs_review",
                "baseline_window_rows": 48,
                "recent_window_rows": 24,
                "columns_analyzed": 6,
                "warnings": [],
                "column_drift": [],
                "top_relationship_changes": [
                    {
                        "relationship": "pump_power_kw<->filter_dp_psi",
                        "display_columns": ["Pump Power", "Filter Differential Pressure"],
                        "change_type": "weakened",
                        "correlation_delta": 0.72,
                        "baseline_correlation": 0.88,
                        "recent_correlation": 0.16,
                        "coupling_strength": 0.88,
                        "baseline_sample_size": 48,
                        "recent_sample_size": 24,
                        "confidence_score": 0.91,
                    },
                    {
                        "relationship": "pump_speed_hz<->filter_dp_psi",
                        "display_columns": ["Pump Speed", "Filter Differential Pressure"],
                        "change_type": "changed",
                        "correlation_delta": 0.51,
                        "baseline_correlation": 0.82,
                        "recent_correlation": 0.31,
                        "coupling_strength": 0.82,
                        "baseline_sample_size": 48,
                        "recent_sample_size": 24,
                        "confidence_score": 0.86,
                    },
                ],
            },
            "operator_report": {"recommended_operator_checks": ["Compare the baseline and recent windows against facility logs."]},
            "sii_intelligence": {"facility_state": "needs_review"},
        }
    )

    report = analysis["operator_interpretation"]

    assert report["title"] == "Operational Assessment"
    assert report["overall_condition"] == "Attention Needed"
    assert report["confidence"] == "High"
    assert report["subsystem"] == "Flow & Pressure"
    assert "2 operational relationships changed" in report["what_changed"]
    assert {"label": "Pump Power <-> Filter Differential Pressure"} in report["relationship_changes"]
    assert analysis["insights"][0]["why_it_matters"].startswith("Operational impact: ")
    assert "process resistance" in analysis["insights"][0]["why_it_matters"]
    assert "Operating setpoint modification" in report["potential_operational_causes"]
    assert "Operator logs" in report["recommended_review"]
    assert any("Pump Power <-> Filter Differential Pressure shifted" in item for item in report["advanced_details"]["raw_relationship_identifiers"])


def test_analysis_output_suppresses_cumulative_counter_artifacts() -> None:
    result = process_csv_content(
        filename="analysis-quality.csv",
        content=_analysis_quality_csv(),
        job_id="analysisoutputquality001",
    )

    baseline = result["baseline_analysis"]
    relationship_model = result["relationship_model"]
    analysis = result["analysis_result"]

    assert [item["column"] for item in baseline["cumulative_counters"]] == ["meter_cumulative_gal"]
    raw_meter = next(item for item in baseline["column_drift"] if item["column"] == "meter_cumulative_gal")
    assert raw_meter["analysis_role"] == "supporting_context"
    assert raw_meter["drift_flag"] == "context"
    assert relationship_model["excluded_cumulative_counters"][0]["column"] == "meter_cumulative_gal"

    serialized_relationships = str(relationship_model["top_relationship_changes"])
    serialized_insights = str(analysis["insights"])
    assert "meter_cumulative_gal" not in serialized_relationships
    assert "meter_cumulative_gal" not in analysis["executive_summary"]["highest_priority_finding"]
    assert "meter_cumulative_gal moved" not in serialized_insights


def test_analysis_output_promotes_operational_findings_and_suppresses_ground_truth_relationships() -> None:
    result = process_csv_content(
        filename="analysis-quality.csv",
        content=_analysis_quality_csv(),
        job_id="analysisoutputquality002",
    )
    analysis = result["analysis_result"]
    insight_titles = [insight["title"] for insight in analysis["insights"]]

    assert "Pump vibration increased sharply" in insight_titles
    assert not any("fouling" in title.lower() for title in insight_titles)
    assert not any(
        "gt_ct_fouling_severity" in relationship.get("source_tags", [])
        for relationship in analysis["relationships"]
    )
    assert any(
        item["column"] == "gt_ct_fouling_severity"
        and item["telemetry_category"] == "ground_truth_label"
        and item["analysis_role"] == "validation_label"
        and item["drift_flag"] == "validation"
        for item in result["baseline_analysis"]["column_drift"]
    )
    assert not any(title.startswith("Relationship shift:") for title in insight_titles)


def test_analysis_output_narratives_and_contributors_are_distinct_and_deduped() -> None:
    result = process_csv_content(
        filename="analysis-quality.csv",
        content=_analysis_quality_csv(),
        job_id="analysisoutputquality003",
    )
    analysis = result["analysis_result"]

    for insight in analysis["insights"]:
        fields = [
            insight.get("what_happened") or insight.get("what_changed"),
            insight.get("why_neraium_thinks_it_happened") or insight.get("why_it_matters"),
            insight.get("possible_operational_consequence") or insight.get("possible_consequence"),
        ]
        assert len({field for field in fields if field}) == len([field for field in fields if field])
        factors = insight.get("likely_contributors", [])
        assert factors == list(dict.fromkeys(factors))
        assert insight.get("recommended_action") != insight.get("operator_check")


def test_analysis_output_missing_telemetry_warning_has_affected_columns_and_percentage() -> None:
    result = process_csv_content(
        filename="analysis-quality.csv",
        content=_analysis_quality_csv(),
        job_id="analysisoutputquality004",
    )
    data_quality = result["analysis_result"]["data_quality"]
    affected = {
        profile["signal_id"]
        for profile in data_quality["signal_integrity"]
        if profile.get("gap_type")
    }

    assert {"supply_pressure_psi", "pump_vibration_ips"}.issubset(affected)
    missing_values = " ".join(data_quality["missing_values"])
    assert "0.4% missing" in missing_values



def _semantic_mapping_csv() -> bytes:
    rows = []
    for index in range(80):
        timestamp = f"2026-06-01T{index // 60:02d}:{index % 60:02d}:00Z"
        pressure = 50.0 if index < 40 else 75.0
        status = 0 if index < 40 else 1
        occupancy = 18 if index < 40 else 92
        rows.append(f"{timestamp},{pressure:.2f},{status},{occupancy}")
    header = "Timestamp,Supply Pressure (psi),Pump Status,Occupancy Load %"
    return (header + "\n" + "\n".join(rows)).encode("utf-8")


def test_semantic_header_mapping_survives_pipeline_and_titles_avoid_column_fallbacks() -> None:
    result = process_csv_content(
        filename="semantic-mapping.csv",
        content=_semantic_mapping_csv(),
        job_id="semanticmapping001",
    )

    catalog = result["telemetry_signal_catalog"]
    pressure = catalog["Supply Pressure (psi)"]
    assert pressure["original_header"] == "Supply Pressure (psi)"
    assert pressure["normalized_name"] == "supply_pressure_psi"
    assert pressure["display_name"] == "Supply pressure"
    assert pressure["engineering_units"] == "psi"
    assert pressure["source_column_index"] == 1
    assert pressure["inferred_telemetry_type"] == "Equipment Process Variable"

    tags = {tag["source_column"]: tag for tag in result["analysis_result"]["normalized_telemetry"]["tags"]}
    assert tags["Supply Pressure (psi)"]["original_header"] == "Supply Pressure (psi)"
    assert tags["Supply Pressure (psi)"]["display_name"] == "Supply pressure"

    serialized_insights = str(result["analysis_result"]["insights"])
    assert "Supply pressure moved up" in serialized_insights
    assert "Column " not in serialized_insights


def test_binary_status_columns_use_state_analysis_not_operator_findings() -> None:
    rows = []
    for index in range(120):
        timestamp = f"2026-06-01T{index // 60:02d}:{index % 60:02d}:00Z"
        status = 0 if index < 60 else 1
        vibration = 0.1 if index < 60 else 0.5
        rows.append(f"{timestamp},{status},{70.0:.1f},{vibration:.3f}")
    content = ("timestamp,pump_status,water_temp_f,pump_vibration_ips\n" + "\n".join(rows)).encode("utf-8")

    result = process_csv_content(filename="binary-status.csv", content=content, job_id="binarystate001")
    status_drift = next(item for item in result["baseline_analysis"]["column_drift"] if item["column"] == "pump_status")

    assert status_drift["telemetry_category"] == "binary_status"
    assert status_drift["analysis_role"] == "state_signal"
    assert status_drift["drift_flag"] == "state_analysis"
    assert status_drift["state_analysis"]["transition_count"] == 1
    assert "pump_status" not in str(result["analysis_result"]["insights"])
    assert "pump_status" not in result["sii_runner_result"]["columns_used"]
