from __future__ import annotations

from datetime import datetime, timezone

from app.engine import run_engine_analysis
from app.services.analysis_result_contract import build_analysis_result
from app.services.baseline_analysis import build_baseline_analysis
from app.services.cultivation_mapping import map_cultivation_columns
from app.services.data_quality import build_data_quality, profile_numeric_columns
from app.services.upload_evidence import build_evidence_record_from_result
from app.water_intelligence import WaterIntelligenceContext, interpret_water_intelligence
from app.water_intelligence.models import apply_confirmation_status


def _catalog(columns, units):
    return {
        column: {
            "source_column": column,
            "original_header": column,
            "display_name": column.replace("_", " ").title(),
            "engineering_units": units.get(column, ""),
        }
        for column in columns
    }


def _normalized(columns, rows, units):
    records = []
    for row_index, row in enumerate(rows):
        for column in columns:
            if column == "timestamp":
                continue
            records.append({"timestamp": row[0], "source_column": column, "value": row[columns.index(column)], "unit": units.get(column), "quality": "ok", "source_row": row_index + 1})
    return {"records": records, "tags": [{"source_column": column, "unit": units.get(column)} for column in columns if column != "timestamp"]}


def _finding(columns, *, trust="proposed", finding_id="rel-1", metadata=True):
    item = {
        "id": finding_id,
        "columns": columns,
        "relationship_type": "linear_correlation",
        "change_type": "weakened",
        "baseline_strength": 0.88,
        "current_strength": 0.22,
        "correlation_delta": 0.66,
        "confidence_score": 0.81,
        "graph_trust": trust,
        "time_window": {"baseline_start": "2026-01-01T00:00:00Z", "baseline_end": "2026-01-01T01:00:00Z", "current_start": "2026-01-01T02:00:00Z", "current_end": "2026-01-01T03:00:00Z"},
        "source_rows": [{"window": "baseline_start", "source_row": 1}, {"window": "current_end", "source_row": 12}],
        "supporting_metric_pairs": [{"left": columns[0], "right": columns[1], "baseline_sample_size": 8, "recent_sample_size": 4}],
    }
    if metadata:
        item["source_column_metadata"] = [{"source_column": column} for column in columns]
    return item


def _context(columns, rows, units, finding, **kwargs):
    return WaterIntelligenceContext(
        columns=columns,
        engine_result={"evidence": [{"type": "relationship_change", "columns": finding["columns"], "change": finding.get("correlation_delta"), "confidence_score": finding.get("confidence_score")}], "signals": [], "system_evidence": {"corroboration_level": "moderate"}},
        relationship_model={"top_relationship_changes": [finding], "relationship_graph": {"changed_edges": [finding]}},
        baseline_analysis={"warnings": kwargs.pop("baseline_warnings", [])},
        normalized_telemetry=_normalized(columns, rows, units),
        telemetry_signal_catalog=_catalog(columns, units),
        timestamp_profile={"first_timestamp": rows[0][0], "last_timestamp": rows[-1][0], "warnings": kwargs.pop("timestamp_warnings", [])},
        data_quality={"readiness": "ready", "warnings": kwargs.pop("data_warnings", [])},
        operating_mode=kwargs.pop("operating_mode", "normal"),
        upload_id="upload-water-1",
        analysis_id="analysis-water-1",
        **kwargs,
    )


def _pump_fixture(trust="proposed", metadata=True, units=None, operating_mode="normal", data_warnings=None):
    columns = ["timestamp", "pump_flow_gpm", "pump_dp_psi", "pump_power_kw", "pump_speed_hz", "valve_position_pct"]
    units = units or {"pump_flow_gpm": "gpm", "pump_dp_psi": "psi", "pump_power_kw": "kW", "pump_speed_hz": "Hz", "valve_position_pct": "%"}
    rows = []
    for i in range(12):
        flow = 500 - max(0, i - 7) * 28
        dp = 46 - max(0, i - 7) * 2
        power = 35 + max(0, i - 7) * 3
        rows.append([f"2026-01-01T00:{i:02d}:00Z", flow, dp, power, 50, 70])
    finding = _finding(["pump_flow_gpm", "pump_dp_psi"], trust=trust, metadata=metadata)
    return _context(columns, rows, units, finding, operating_mode=operating_mode, data_warnings=data_warnings or [])


def _chilled_fixture():
    columns = ["timestamp", "chw_supply_temp_f", "chw_return_temp_f", "chw_flow_gpm", "chw_delta_t_f", "chiller_power_kw", "valve_position_pct"]
    units = {"chw_supply_temp_f": "F", "chw_return_temp_f": "F", "chw_flow_gpm": "gpm", "chw_delta_t_f": "delta_f", "chiller_power_kw": "kW", "valve_position_pct": "%"}
    rows = []
    for i in range(14):
        recent = max(0, i - 9)
        rows.append([f"2026-01-02T00:{i:02d}:00Z", 44, 56 - recent * 1.0, 800 + recent * 80, 12 - recent * 1.0, 220 + recent * 8, 80])
    finding = _finding(["chw_flow_gpm", "chw_delta_t_f"], trust="proposed")
    return _context(columns, rows, units, finding, operating_mode="cooling")


def _filter_fixture():
    columns = ["timestamp", "filter_dp_psi", "filter_flow_gpm", "filter_mode"]
    units = {"filter_dp_psi": "psi", "filter_flow_gpm": "gpm", "filter_mode": ""}
    rows = []
    for i in range(14):
        rows.append([f"2026-01-03T00:{i:02d}:00Z", 8 + max(0, i - 9) * 1.5, 450 + (i % 2), 1])
    finding = _finding(["filter_dp_psi", "filter_flow_gpm"], trust="proposed")
    return _context(columns, rows, units, finding, operating_mode="filtering")


def _tower_fixture():
    columns = ["timestamp", "tower_makeup_flow_gpm", "tower_basin_level_ft", "tower_makeup_conductivity_us_cm", "tower_circulating_conductivity_us_cm"]
    units = {"tower_makeup_flow_gpm": "gpm", "tower_basin_level_ft": "ft", "tower_makeup_conductivity_us_cm": "uS/cm", "tower_circulating_conductivity_us_cm": "uS/cm"}
    rows = []
    for i in range(10):
        rows.append([f"2026-01-04T00:{i:02d}:00Z", 40 + i, 5.0, 450, 1800])
    finding = _finding(["tower_makeup_flow_gpm", "tower_basin_level_ft"], trust="proposed")
    return _context(columns, rows, units, finding, operating_mode="heat_rejection")


def test_water_layer_consumes_existing_sii_finding_for_pump_fixture():
    result = interpret_water_intelligence(_pump_fixture())
    insight = result["insights"][0]
    assert insight["relationship_prior_id"] == "water.pump_hydraulic_behavior"
    assert insight["sii_finding_id"] == "rel-1"
    assert insight["observed_evidence"]
    assert any(metric["name"] == "hydraulic_output_proxy" for metric in insight["derived_metrics"])
    assert insight["confidence_and_uncertainty"]["preserved_sii_confidence"] == 0.81


def test_sii_engine_behavior_remains_unchanged_and_generic():
    columns = ["timestamp", "temperature", "humidity"]
    rows = [[str(i), str(70 + i), str(50 - i)] for i in range(10)]
    profiles = profile_numeric_columns(columns, rows)
    data_quality = build_data_quality(len(rows), len(columns), len(profiles), True, [])
    baseline = build_baseline_analysis(columns, rows, profiles)
    result = run_engine_analysis(columns=columns, rows=rows, data_quality=data_quality, baseline_analysis=baseline, cultivation_mapping=map_cultivation_columns(columns), numeric_profiles=profiles)
    assert "water_intelligence" not in result
    assert result["engine_version"] == "neraium-cultivation-v1"


def test_missing_required_signals_skip_prior_gracefully():
    columns = ["timestamp", "pump_flow_gpm"]
    units = {"pump_flow_gpm": "gpm"}
    rows = [["2026-01-01T00:00:00Z", 100], ["2026-01-01T00:01:00Z", 90]]
    finding = _finding(["pump_flow_gpm", "unknown_signal"], trust="trusted")
    result = interpret_water_intelligence(_context(columns, rows, units, finding))
    assert not result["insights"]
    assert any("differential_pressure" in item["missing_required_signals"] for item in result["skipped_priors"])


def test_incompatible_units_invalidate_required_signal():
    ctx = _pump_fixture(units={"pump_flow_gpm": "psi", "pump_dp_psi": "psi", "pump_power_kw": "kW", "pump_speed_hz": "Hz", "valve_position_pct": "%"})
    result = interpret_water_intelligence(ctx)
    assert not result["insights"]
    assert any("incompatible_unit:flow:pump_flow_gpm" in item["invalid_conditions"] for item in result["skipped_priors"])


def test_timestamp_misalignment_reduces_confidence_and_adds_confounder():
    result = interpret_water_intelligence(_pump_fixture(data_warnings=["Timestamp misalignment detected between pump flow and pressure."]))
    insight = result["insights"][0]
    assert any(item["condition"] == "timestamp misalignment" and item["state"] == "active" for item in insight["confounding_conditions"])
    assert "timestamp" in insight["confidence_and_uncertainty"]["explanation"].lower() or insight["confidence_and_uncertainty"]["reduced_confidence"]


def test_invalid_operating_mode_blocks_prior():
    result = interpret_water_intelligence(_pump_fixture(operating_mode="fire_mode"))
    assert not result["insights"]
    assert any("invalid_operating_mode:fire_mode" in item["invalid_conditions"] for item in result["skipped_priors"])


def test_active_confounders_include_valve_context():
    insight = interpret_water_intelligence(_pump_fixture())["insights"][0]
    assert any("Valve" in item["condition"] or "valve" in item["condition"] for item in insight["confounding_conditions"] if item["state"] == "active")


def test_graph_trust_tiers_control_operator_insight_eligibility():
    trusted = interpret_water_intelligence(_pump_fixture(trust="trusted"))["insights"][0]
    proposed = interpret_water_intelligence(_pump_fixture(trust="proposed"))["insights"][0]
    speculative = interpret_water_intelligence(_pump_fixture(trust="speculative"))
    assert trusted["graph_trust"]["tier"] == "trusted"
    assert proposed["graph_trust"]["tier"] == "proposed"
    assert not speculative["insights"]
    assert any(item.get("graph_trust", {}).get("tier") == "speculative" for item in speculative["skipped_priors"])


def test_correlation_only_edge_is_not_used_for_automated_insight():
    ctx = _pump_fixture(trust="correlation_only", metadata=False)
    ctx.relationship_model["top_relationship_changes"][0].pop("source_rows", None)
    ctx.relationship_model["top_relationship_changes"][0].pop("time_window", None)
    result = interpret_water_intelligence(ctx)
    assert not result["insights"]
    assert any("correlation-only" in item["reason"] for item in result["skipped_priors"])


def test_chilled_water_flow_rises_while_delta_t_falls_is_hypothesis_not_confirmation():
    insight = interpret_water_intelligence(_chilled_fixture())["insights"][0]
    assert insight["relationship_prior_id"] == "water.chilled_water_thermal_behavior"
    assert any(metric["name"] in {"derived_delta_t", "reported_delta_t", "thermal_load_proxy"} for metric in insight["derived_metrics"])
    assert insight["status"] != "operator_confirmed"
    assert any("Bypass flow" == item["explanation"] for item in insight["possible_explanations"])


def test_filter_dp_rise_at_similar_flow_supports_only_hypothesis():
    insight = interpret_water_intelligence(_filter_fixture())["insights"][0]
    metric = next(item for item in insight["derived_metrics"] if item["name"] == "filter_dp_at_comparable_flow_context")
    assert metric["value"]["similar_flow"] is True
    assert "does not confirm filter loading" in metric["explanation"]


def test_non_identifiable_tower_mass_balance_returns_residual_with_uncertainty():
    insight = interpret_water_intelligence(_tower_fixture())["insights"][0]
    metric = next(item for item in insight["derived_metrics"] if item["name"] == "unmeasured_outflow")
    assert metric["identifiability"] == "not_separable"
    assert "blowdown_flow" in metric["missing_inputs"]
    assert metric["uncertainty_range"]
    assert "cannot be separated" in metric["explanation"]


def test_hypothesis_never_becomes_confirmed_from_telemetry_alone_and_operator_confirmation_is_explicit():
    insight = interpret_water_intelligence(_pump_fixture())["insights"][0]
    assert insight["status"] == "observed"
    rejected = apply_confirmation_status(insight, {"source": "telemetry", "note": "stats only"})
    assert rejected["status"] == "observed"
    confirmed = apply_confirmation_status(insight, {"source": "operator_confirmation", "confirmed_by": "operator@example.com"})
    assert confirmed["status"] == "operator_confirmed"


def test_prior_version_persists_into_evidence_record():
    result = interpret_water_intelligence(_pump_fixture())
    payload = {"job_id": "water-run", "upload_id": "water-run", "filename": "water.csv", "row_count": 12, "column_count": 3, "columns": ["pump_flow_gpm", "pump_dp_psi"], "water_intelligence": result, "sii_intelligence": {"supporting_evidence": []}, "baseline_analysis": {"top_relationship_changes": []}, "data_quality": {}, "timestamp_profile": {}}
    record = build_evidence_record_from_result(run_id="water-run", filename="water.csv", source_type="csv", result=payload, created_at="2026-01-01T00:00:00Z", completed_at="2026-01-01T00:01:00Z", status="completed", initiated_by="operator")
    assert record["water_prior_versions"][0]["relationship_prior_id"] == "water.pump_hydraulic_behavior"
    assert record["water_prior_versions"][0]["relationship_prior_version"] == "1.0.0"


def test_analysis_result_serializes_all_six_water_insight_fields():
    water = interpret_water_intelligence(_pump_fixture())
    result = {"job_id": "water-analysis", "run_id": "water-analysis", "upload_id": "water-analysis", "filename": "water.csv", "data_quality": {"readiness": "ready"}, "timestamp_profile": {}, "baseline_analysis": {}, "relationship_model": {}, "operator_report": {}, "water_intelligence": water, "analysis_explanation": {"insights": water["insights"], "relationships": [], "systems": [], "recommendations": [], "fingerprint": {}, "executive_summary": {}}}
    analysis = build_analysis_result(result)
    insight = analysis["insights"][0]
    for field in ["observed_evidence", "derived_metrics", "possible_explanations", "confounding_conditions", "recommended_checks", "confidence_and_uncertainty"]:
        assert field in insight
    assert insight["relationship_prior_id"] == "water.pump_hydraulic_behavior"
    assert analysis["water_intelligence"]["insights"]


def test_no_water_prior_applies_gracefully():
    columns = ["timestamp", "air_temp_f", "humidity_pct"]
    units = {"air_temp_f": "F", "humidity_pct": "%"}
    rows = [["2026-01-01T00:00:00Z", 70, 50], ["2026-01-01T00:01:00Z", 71, 49]]
    finding = _finding(["air_temp_f", "humidity_pct"], trust="trusted")
    result = interpret_water_intelligence(_context(columns, rows, units, finding))
    assert result["no_applicable_prior"] is True
    assert result["insights"] == []
