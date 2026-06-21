from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from app.services.upload_jobs import process_csv_content


def _csv_from_rows(rows: list[str]) -> bytes:
    return ("timestamp,temp,humidity,airflow,pressure\n" + "\n".join(rows)).encode()


def _telemetry_rows(count: int, *, noisy: bool = False, drift: bool = False, missing: bool = False) -> list[str]:
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    rows: list[str] = []
    for index in range(count):
        timestamp = (start + timedelta(minutes=5 * index)).isoformat().replace("+00:00", "Z")
        phase = index / 12.0
        noise = math.sin(index * 1.7) * 0.35 if noisy else 0.0
        drift_offset = max(0, index - int(count * 0.65)) / max(1, count * 0.35) if drift else 0.0
        temp = 72.0 + math.sin(phase) * 0.8 + noise + drift_offset * 8.0
        humidity = 50.0 + math.cos(phase) * 1.5 - noise * 0.4 + drift_offset * 12.0
        airflow = 420.0 + math.sin(phase * 0.5) * 5.0 - drift_offset * 95.0
        pressure = 1.7 + math.cos(phase * 0.4) * 0.05 + drift_offset * 0.65
        if missing and index % 11 == 0:
            rows.append(f"{timestamp},,{humidity:.3f},{airflow:.3f},{pressure:.4f}")
        elif missing and index % 17 == 0:
            rows.append(f"{timestamp},{temp:.3f},null,{airflow:.3f},{pressure:.4f}")
        else:
            rows.append(f"{timestamp},{temp:.3f},{humidity:.3f},{airflow:.3f},{pressure:.4f}")
    return rows


def _latest_runner_state(result: dict) -> dict:
    return result["sii_runner_result"]["latest_state"]


def _primary_room(result: dict) -> dict:
    return result["sii_intelligence"]["rooms"][0]


def test_stable_upload_stays_nominal_in_runner_and_ui_summary() -> None:
    result = process_csv_content(filename="stable-regression.csv", content=_csv_from_rows(_telemetry_rows(240)))
    latest = _latest_runner_state(result)

    assert result["drift_status"] == "info"
    assert result["operating_state"] == "Baseline-aligned"
    assert latest["regime"] in {"STABLE", "TRANSITION"}
    assert latest["urgency"] != "CRITICAL"
    assert latest["instability_score"] < 0.24
    assert latest["instability_index"]["score"] < 0.25


def test_noisy_stable_upload_does_not_raise_critical_runner_state() -> None:
    result = process_csv_content(filename="noisy-stable-regression.csv", content=_csv_from_rows(_telemetry_rows(240, noisy=True)))
    latest = _latest_runner_state(result)

    assert result["drift_status"] == "info"
    assert latest["urgency"] != "CRITICAL"
    assert latest["instability_score"] < 0.32


def test_missing_values_lower_confidence_without_forcing_alert() -> None:
    complete = process_csv_content(filename="complete-confidence.csv", content=_csv_from_rows(_telemetry_rows(240)))
    missing = process_csv_content(filename="missing-confidence.csv", content=_csv_from_rows(_telemetry_rows(240, missing=True)))

    complete_latest = _latest_runner_state(complete)
    missing_latest = _latest_runner_state(missing)

    assert missing_latest["confidence"] < complete_latest["confidence"]
    assert missing_latest["urgency"] != "CRITICAL"
    assert missing_latest["instability_components"]["recent_completeness"] < 1.0


def test_short_persistence_does_not_produce_strong_finding() -> None:
    result = process_csv_content(filename="short-drift-regression.csv", content=_csv_from_rows(_telemetry_rows(18, drift=True)))
    latest = _latest_runner_state(result)
    primary_room = _primary_room(result)

    assert primary_room["urgency"] == "review"
    assert primary_room["confidence"] <= 52
    assert "confidence is capped" in primary_room["confidence_basis"].lower()
    assert latest["confidence"] <= 0.58


def test_heavy_missingness_caps_confidence_and_temper_driver_language() -> None:
    rows = _telemetry_rows(240)
    degraded_rows: list[str] = []
    for index, row in enumerate(rows):
        timestamp, temp, humidity, airflow, pressure = row.split(",")
        if index % 2 == 0:
            temp = ""
        if index % 3 == 0:
            humidity = "null"
        degraded_rows.append(",".join([timestamp, temp, humidity, airflow, pressure]))

    result = process_csv_content(filename="heavy-missing-regression.csv", content=_csv_from_rows(degraded_rows))
    primary_room = _primary_room(result)

    assert primary_room["confidence"] <= 50
    assert "evidence remains limited" in primary_room["primary_driver"].lower() or "insufficient" in primary_room["primary_driver"].lower()
    assert "data quality is poor" in primary_room["confidence_basis"].lower()


def test_progressive_degradation_remains_detectable() -> None:
    result = process_csv_content(filename="progressive-drift-regression.csv", content=_csv_from_rows(_telemetry_rows(260, drift=True)))
    latest = _latest_runner_state(result)

    assert result["drift_status"] in {"review", "unstable"} or latest["instability_score"] >= 0.52
    assert latest["regime"] in {"UNSTABLE", "LOCK_IN"} or latest["instability_score"] >= 0.52


CHILLED_WATER_COLUMNS = [
    "timestamp",
    "chw_supply_temp_f",
    "chw_return_temp_f",
    "delta_t_f",
    "flow_gpm",
    "pump_speed_pct",
    "pump_power_kw",
    "differential_pressure_psi",
    "chiller_load_pct",
    "compressor_power_kw",
    "condenser_water_temp_f",
    "evaporator_temp_f",
    "building_cooling_demand_pct",
    "ambient_temp_f",
    "energy_consumption_kwh",
    "alarm_count",
    "maintenance_event",
    "operator_override",
]


def _chilled_water_csv(
    count: int = 240,
    *,
    missing_sparse: bool = False,
    omit_timestamp: bool = False,
    omit_temps: bool = False,
    out_of_order: bool = False,
    duplicate: bool = False,
    extra_column: bool = False,
) -> bytes:
    columns = [column for column in CHILLED_WATER_COLUMNS if not (omit_timestamp and column == "timestamp")]
    if omit_temps:
        columns = [column for column in columns if column not in {"chw_supply_temp_f", "chw_return_temp_f"}]
    if extra_column:
        columns.append("vendor_unused_status")
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows: list[dict[str, str]] = []
    for index in range(count):
        supply = 44.0 + math.sin(index / 24.0) * 0.8
        ret = supply + 10.0 + math.cos(index / 18.0) * 0.6
        flow = 1200.0 + math.sin(index / 16.0) * 35.0
        pump_power = 38.0 + math.cos(index / 20.0) * 2.0
        chiller_load = 55.0 + math.sin(index / 30.0) * 8.0
        compressor = 210.0 + math.sin(index / 22.0) * 12.0
        row = {
            "timestamp": (start + timedelta(minutes=5 * index)).isoformat().replace("+00:00", "Z"),
            "chw_supply_temp_f": f"{supply:.3f}",
            "chw_return_temp_f": f"{ret:.3f}",
            "delta_t_f": f"{ret - supply:.3f}",
            "flow_gpm": f"{flow:.3f}",
            "pump_speed_pct": f"{62.0 + math.sin(index / 13.0) * 3.0:.3f}",
            "pump_power_kw": f"{pump_power:.3f}",
            "differential_pressure_psi": f"{18.0 + math.cos(index / 17.0):.3f}",
            "chiller_load_pct": f"{chiller_load:.3f}",
            "compressor_power_kw": f"{compressor:.3f}",
            "condenser_water_temp_f": f"{74.0 + math.sin(index / 19.0):.3f}",
            "evaporator_temp_f": f"{39.0 + math.cos(index / 21.0):.3f}",
            "building_cooling_demand_pct": f"{58.0 + math.sin(index / 29.0) * 7.0:.3f}",
            "ambient_temp_f": f"{82.0 + math.sin(index / 35.0) * 9.0:.3f}",
            "energy_consumption_kwh": f"{95.0 + compressor * 0.05:.3f}",
            "alarm_count": "0",
            "maintenance_event": "0",
            "operator_override": "0",
            "vendor_unused_status": "ignored",
        }
        if missing_sparse and index in {25, 26, 55, 56}:
            for column in ("chw_supply_temp_f", "flow_gpm", "pump_power_kw", "chiller_load_pct", "compressor_power_kw"):
                row[column] = ""
        rows.append(row)
    if out_of_order and len(rows) > 4:
        rows[2], rows[3] = rows[3], rows[2]
    if duplicate and rows:
        rows.insert(5, dict(rows[4]))
    return (",".join(columns) + "\n" + "\n".join(",".join(row.get(column, "") for column in columns) for row in rows)).encode()


def test_chilled_water_sparse_nulls_do_not_block_analysis() -> None:
    result = process_csv_content(filename="chilled_water_system_data.csv", content=_chilled_water_csv(missing_sparse=True, extra_column=True))

    quality = result["data_quality"]
    messages = quality["messages"]
    assert quality["schema_detection"]["detected"] is True
    assert quality["analysis_gate_state"] == "DEGRADED_READY"
    assert quality["readiness"] == "ready"
    assert "Detected chilled-water telemetry." in messages
    assert "240 rows loaded." in messages
    assert "5-minute interval detected." in messages
    assert any("Sparse missing values detected in supply temp, flow, pump power, chiller load, compressor power" in message for message in messages)
    assert "Analysis can proceed with confidence warnings." in messages
    assert result["sii_runner_result"]["latest_state"]["urgency"] != "CRITICAL"


def test_chilled_water_missing_timestamp_uses_row_index_when_signal_exists() -> None:
    result = process_csv_content(filename="missing-timestamp.csv", content=_chilled_water_csv(omit_timestamp=True))

    assert result["data_quality"]["analysis_gate_state"] == "DEGRADED_READY"
    assert result["data_quality"]["readiness"] == "ready"
    assert "No timestamp column detected; using row-index analysis." in result["data_quality"]["messages"]


def test_chilled_water_missing_supply_and_return_temperature_degrades_confidence() -> None:
    result = process_csv_content(filename="missing-temps.csv", content=_chilled_water_csv(omit_temps=True))

    assert result["data_quality"]["analysis_gate_state"] in {"READY", "DEGRADED_READY"}
    assert result["data_quality"]["readiness"] == "ready"


def test_chilled_water_out_of_order_timestamps_are_sorted() -> None:
    result = process_csv_content(filename="unsorted-chilled.csv", content=_chilled_water_csv(out_of_order=True))

    preview_timestamps = [row["timestamp"] for row in result["preview_rows"][:4]]
    assert preview_timestamps == sorted(preview_timestamps)
    assert result["data_quality"]["analysis_gate_state"] == "DEGRADED_READY"


def test_chilled_water_duplicate_rows_are_dropped() -> None:
    result = process_csv_content(filename="duplicate-chilled.csv", content=_chilled_water_csv(duplicate=True))

    assert result["row_count"] == 240
    assert result["ingestion_report"]["drop_reasons"]["exact_duplicate_row"] == 1
    assert result["data_quality"]["analysis_gate_state"] == "DEGRADED_READY"


def test_chilled_water_unknown_extra_columns_are_ignored() -> None:
    result = process_csv_content(filename="extra-column-chilled.csv", content=_chilled_water_csv(extra_column=True))

    assert "vendor_unused_status" in result["columns"]
    assert result["data_quality"]["analysis_gate_state"] == "READY"
