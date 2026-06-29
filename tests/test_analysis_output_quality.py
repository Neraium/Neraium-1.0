from __future__ import annotations

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


def test_analysis_output_promotes_operational_findings_and_keeps_valid_relationship() -> None:
    result = process_csv_content(
        filename="analysis-quality.csv",
        content=_analysis_quality_csv(),
        job_id="analysisoutputquality002",
    )
    analysis = result["analysis_result"]
    insight_titles = [insight["title"] for insight in analysis["insights"]]

    assert "Pump vibration increased sharply" in insight_titles
    assert "Fouling-related thermal behavior changed" in insight_titles
    assert any(
        {"ct_outlet_temp_f", "gt_ct_fouling_severity"}.issubset(set(relationship.get("source_tags", [])))
        for relationship in analysis["relationships"]
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

