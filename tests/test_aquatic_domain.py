from app.engine import run_engine_analysis
from app.services.aquatic_domain import (
    AQUATIC_TELEMETRY_SIGNALS,
    analyze_aquatic_instability,
    build_aquatic_replay_dataset,
    generate_aquatic_simulated_telemetry,
    map_aquatic_schema,
)
from app.services.baseline_analysis import build_baseline_analysis
from app.services.cultivation_mapping import map_cultivation_columns
from app.services.data_quality import build_data_quality, profile_numeric_columns


def _engine_result_for(rows: list[list[str]], columns: list[str]) -> tuple[dict, dict]:
    numeric_profiles = profile_numeric_columns(columns, rows)
    data_quality = build_data_quality(
        row_count=len(rows),
        column_count=len(columns),
        numeric_column_count=len(numeric_profiles),
        timestamp_detected=True,
        warnings=[],
    )
    baseline = build_baseline_analysis(columns, rows, numeric_profiles)
    engine = run_engine_analysis(
        columns=columns,
        rows=rows,
        data_quality=data_quality,
        baseline_analysis=baseline,
        cultivation_mapping=map_cultivation_columns(columns),
        numeric_profiles=numeric_profiles,
    )
    return baseline, engine


def test_aquatic_schema_maps_required_signals() -> None:
    columns = ["timestamp", *AQUATIC_TELEMETRY_SIGNALS]
    mapped = map_aquatic_schema(columns)
    assert mapped["schema_type"] == "commercial_aquatic_v1"
    assert mapped["mapped_column_count"] >= len(AQUATIC_TELEMETRY_SIGNALS)
    assert mapped["coverage_ratio"] > 0.9


def test_aquatic_schema_maps_commercial_water_aliases() -> None:
    mapped = map_aquatic_schema([
        "chlorine_ppm",
        "turbidity",
        "conductivity",
        "makeup_water_flow",
        "chilled_water_supply_temp",
        "chilled_water_return_temp",
        "chw_delta_t",
        "chiller_load_pct",
        "tower_fan_speed",
        "basin_temperature",
        "blowdown_rate",
    ])

    assert mapped["mapped_signals"]["free_chlorine"] == ["chlorine_ppm"]
    assert mapped["mapped_signals"]["supply_temperature"] == ["chilled_water_supply_temp"]
    assert mapped["mapped_signals"]["return_temperature"] == ["chilled_water_return_temp"]
    assert mapped["mapped_signals"]["loop_delta_t"] == ["chw_delta_t"]
    assert mapped["mapped_signals"]["tower_fan_speed"] == ["tower_fan_speed"]
    assert mapped["mapped_column_count"] == 11


def test_aquatic_generator_has_daily_and_noise_variation() -> None:
    rows = generate_aquatic_simulated_telemetry(intervals=96, seed=5)
    assert len(rows) == 96
    occupancy_values = [row["occupancy_estimate"] for row in rows]
    ambient_values = [row["ambient_temperature"] for row in rows]
    assert max(occupancy_values) - min(occupancy_values) > 40
    assert max(ambient_values) - min(ambient_values) > 8


def test_aquatic_replay_dataset_contains_relationship_map() -> None:
    payload = build_aquatic_replay_dataset(intervals=40)
    assert payload["meta"]["domain"] == "commercial_aquatic_hospitality"
    assert len(payload["rows"]) == 40
    assert len(payload["relationship_map"]) >= 5


def test_aquatic_admission_candidates_require_multi_signal_support() -> None:
    columns = [
        "timestamp",
        "flow_rate",
        "filter_pressure",
        "pump_amperage",
        "orp",
        "ph",
        "sanitizer_feed_rate",
    ]
    rows = []
    for i in range(48):
        rows.append(
            [
                str(i),
                str(560 - i * 2.2),
                str(15.5 + i * 0.12),
                str(22 + i * 0.05),
                str(735 - i * 0.85),
                str(7.32 + i * 0.004),
                str(1.3 + i * 0.008),
            ]
        )
    baseline, engine = _engine_result_for(rows, columns)
    outcome = analyze_aquatic_instability(columns=columns, baseline_analysis=baseline, engine_result=engine)
    assert outcome["domain"] == "commercial_aquatic_hospitality"
    assert outcome["admitted_candidates"]
    for event in outcome["admitted_candidates"]:
        assert len(event["contributing_signals"]) >= 2
        assert event["confidence_persistence_score"] >= 0.62

