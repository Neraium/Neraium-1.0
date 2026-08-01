#!/usr/bin/env python3
"""Generate deterministic resort-tower hydronic telemetry fixtures.

This file creates telemetry only. It does not call, reproduce, or influence
Neraium's assessment logic.
"""

from __future__ import annotations

import csv
import json
import math
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path


SEED = 731_2026
INTERVAL = timedelta(minutes=5)
BASELINE_START = datetime(2026, 6, 1, tzinfo=UTC)
BASELINE_DAYS = 30
COMPARISON_START = datetime(2026, 7, 1, tzinfo=UTC)
COMPARISON_DAYS = 14
CHANGE_START = datetime(2026, 7, 3, 0, 0, tzinfo=UTC)
CHANGE_FULL = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)
RECOVERY_START = datetime(2026, 7, 12, 6, 0, tzinfo=UTC)
RECOVERY_COMPLETE = datetime(2026, 7, 13, 6, 0, tzinfo=UTC)

FIELDNAMES = [
    "timestamp",
    "outdoor_air_temp_f",
    "system_load_tons",
    "pump_speed_pct",
    "pump_power_kw",
    "loop_flow_gpm",
    "differential_pressure_psi",
    "critical_valve_position_pct",
    "supply_water_temp_f",
    "return_water_temp_f",
    "tower_enable_status",
    "operator_note",
]

BASELINE_MISSING_INDEXES = {
    *range(518, 522),
    *range(3_177, 3_181),
    *range(6_904, 6_907),
}
COMPARISON_MISSING_INDEXES = {
    *range(204, 208),
    *range(520, 524),
    *range(3_780, 3_783),
}
BASELINE_DUPLICATE_INDEXES = {711, 1_844, 2_777, 4_302, 5_119, 6_211, 7_503}
COMPARISON_DUPLICATE_INDEXES = {339, 1_107, 2_208, 3_417}
BASELINE_VALUE_GAPS = {
    "loop_flow_gpm": set(range(2_030, 2_034)),
    "differential_pressure_psi": set(range(4_411, 4_416)),
    "return_water_temp_f": set(range(7_012, 7_016)),
}
COMPARISON_VALUE_GAPS = {
    "loop_flow_gpm": set(range(690, 694)),
    "differential_pressure_psi": set(range(2_714, 2_719)),
    "return_water_temp_f": set(range(3_890, 3_894)),
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _smooth_step(value: float) -> float:
    bounded = _clamp(value, 0.0, 1.0)
    return bounded * bounded * (3.0 - 2.0 * bounded)


def _change_severity(timestamp: datetime) -> float:
    if timestamp < CHANGE_START:
        return 0.0
    if timestamp < CHANGE_FULL:
        return _smooth_step((timestamp - CHANGE_START) / (CHANGE_FULL - CHANGE_START))
    if timestamp < RECOVERY_START:
        return 1.0
    if timestamp < RECOVERY_COMPLETE:
        return 1.0 - _smooth_step((timestamp - RECOVERY_START) / (RECOVERY_COMPLETE - RECOVERY_START))
    return 0.0


def _active_fraction(timestamp: datetime) -> float:
    hour = timestamp.hour + timestamp.minute / 60
    weekend = timestamp.weekday() >= 5
    start_hour = 6.5 if weekend else 5.5
    stop_hour = 23.5
    if hour < start_hour or hour >= stop_hour:
        return 0.0
    ramp_up = _smooth_step((hour - start_hour) / 1.0)
    ramp_down = _smooth_step((stop_hour - hour) / 1.0)
    return min(ramp_up, ramp_down)


def _normal_signals(timestamp: datetime, rng: random.Random) -> dict[str, float]:
    day_index = (timestamp.date() - BASELINE_START.date()).days
    hour = timestamp.hour + timestamp.minute / 60
    daily_wave = math.sin(2 * math.pi * (hour - 14.5) / 24)
    synoptic_wave = math.sin(2 * math.pi * day_index / 8.5)
    outdoor = 72.0 + 13.5 * daily_wave + 3.2 * synoptic_wave + rng.gauss(0, 0.32)
    active = _active_fraction(timestamp)
    weekend = timestamp.weekday() >= 5
    occupancy = 0.84 if weekend else 1.0
    if weekend:
        occupancy += 0.10 * math.exp(-((hour - 16.0) / 3.2) ** 2)
    else:
        occupancy += 0.08 * math.exp(-((hour - 13.5) / 2.7) ** 2)
        occupancy += 0.035 * math.sin(2 * math.pi * day_index / 5)

    if active:
        load = active * (
            125
            + 8.7 * max(outdoor - 55, 0)
            + 235 * occupancy
            + 38 * math.sin(2 * math.pi * (hour - 10) / 24)
        ) + rng.gauss(0, 4.5)
        load = _clamp(load, 28, 735)
        valve = _clamp(
            17.0 + 0.091 * load + 4.2 * math.sin(2 * math.pi * hour / 6.5) + rng.gauss(0, 0.75),
            18,
            91,
        )
        speed = _clamp(25.5 + 0.061 * load + 0.175 * valve + rng.gauss(0, 0.38), 30, 91)
        flow = max(120, 17.5 * speed + 4.2 * valve - 350 + rng.gauss(0, 10.5))
        differential_pressure = max(4, 0.0045 * speed**2 + 0.035 * valve + rng.gauss(0, 0.24))
        pump_power = max(
            1.5,
            flow * differential_pressure * 0.000604 + 0.000004 * speed**3 + rng.gauss(0, 0.22),
        )
        supply_temp = 43.7 + 0.0022 * load + 0.12 * math.sin(2 * math.pi * hour / 8) + rng.gauss(0, 0.07)
        delta_temp = _clamp(24.0 * load / max(flow, 1), 3.2, 14.8)
        return_temp = supply_temp + delta_temp + rng.gauss(0, 0.09)
    else:
        load = max(0, rng.gauss(1.2, 0.55))
        valve = _clamp(8.0 + rng.gauss(0, 0.35), 5, 12)
        speed = max(0, rng.gauss(0.25, 0.12))
        flow = max(0, rng.gauss(2.5, 1.1))
        differential_pressure = max(0, 0.38 + rng.gauss(0, 0.05))
        pump_power = max(0, 0.32 + rng.gauss(0, 0.04))
        supply_temp = 52.0 + 0.06 * (outdoor - 70) + rng.gauss(0, 0.10)
        return_temp = supply_temp + 0.7 + rng.gauss(0, 0.10)

    return {
        "outdoor_air_temp_f": outdoor,
        "system_load_tons": load,
        "pump_speed_pct": speed,
        "pump_power_kw": pump_power,
        "loop_flow_gpm": flow,
        "differential_pressure_psi": differential_pressure,
        "critical_valve_position_pct": valve,
        "supply_water_temp_f": supply_temp,
        "return_water_temp_f": return_temp,
        "tower_enable_status": 1.0 if active else 0.0,
    }


def _comparison_signals(timestamp: datetime, rng: random.Random) -> dict[str, float]:
    signals = _normal_signals(timestamp, rng)
    if signals["tower_enable_status"] < 0.5:
        return signals

    severity = _change_severity(timestamp)
    if severity <= 0:
        return signals

    valve = _clamp(signals["critical_valve_position_pct"] + 3.8 * severity, 18, 94)
    speed = _clamp(signals["pump_speed_pct"] + 5.2 * severity, 30, 94)
    weakened_valve_coefficient = 4.2 * (1.0 - 0.72 * severity)
    flow = max(
        120,
        17.5 * speed
        + weakened_valve_coefficient * valve
        - 350
        - 0.035 * severity * signals["loop_flow_gpm"]
        + rng.gauss(0, 11.0),
    )
    hydraulic_pressure = 0.0045 * speed**2 + 0.035 * valve
    pressure_sensor_bias = 1.65 * severity
    differential_pressure = max(
        4,
        hydraulic_pressure * (1.0 - 0.10 * severity) + pressure_sensor_bias + rng.gauss(0, 0.25),
    )
    pump_power = max(
        1.5,
        (
            flow * differential_pressure * 0.000604
            + 0.000004 * speed**3
        )
        * (1.0 + 0.34 * severity)
        + rng.gauss(0, 0.24),
    )
    supply_temp = signals["supply_water_temp_f"] + 0.18 * severity
    delta_temp = _clamp(24.0 * signals["system_load_tons"] / max(flow, 1), 3.2, 15.8)
    return_temp = supply_temp + delta_temp + rng.gauss(0, 0.10)
    return {
        **signals,
        "pump_speed_pct": speed,
        "pump_power_kw": pump_power,
        "loop_flow_gpm": flow,
        "differential_pressure_psi": differential_pressure,
        "critical_valve_position_pct": valve,
        "supply_water_temp_f": supply_temp,
        "return_water_temp_f": return_temp,
    }


def _record(timestamp: datetime, values: dict[str, float], note: str) -> dict[str, str]:
    record = {"timestamp": timestamp.isoformat().replace("+00:00", "Z")}
    for field in FIELDNAMES[1:-1]:
        value = values[field]
        record[field] = str(int(value)) if field == "tower_enable_status" else f"{value:.3f}"
    record["operator_note"] = note
    return record


def _write_period(
    path: Path,
    *,
    start: datetime,
    days: int,
    seed_offset: int,
    comparison: bool,
) -> dict[str, object]:
    rng = random.Random(SEED + seed_offset)
    missing_indexes = COMPARISON_MISSING_INDEXES if comparison else BASELINE_MISSING_INDEXES
    duplicate_indexes = COMPARISON_DUPLICATE_INDEXES if comparison else BASELINE_DUPLICATE_INDEXES
    value_gaps = COMPARISON_VALUE_GAPS if comparison else BASELINE_VALUE_GAPS
    rows: list[dict[str, str]] = []
    missing_periods: list[dict[str, str]] = []
    expected_count = days * 24 * 12

    gap_start: int | None = None
    for index in range(expected_count):
        timestamp = start + index * INTERVAL
        if index in missing_indexes:
            if gap_start is None:
                gap_start = index
            continue
        if gap_start is not None:
            missing_periods.append(
                {
                    "start": (start + gap_start * INTERVAL).isoformat().replace("+00:00", "Z"),
                    "end": timestamp.isoformat().replace("+00:00", "Z"),
                }
            )
            gap_start = None
        values = _comparison_signals(timestamp, rng) if comparison else _normal_signals(timestamp, rng)
        note = "routine operator round" if index % (24 * 12 * 5) == 143 else ""
        row = _record(timestamp, values, note)
        for field, indexes in value_gaps.items():
            if index in indexes:
                row[field] = ""
        rows.append(row)
        if index in duplicate_indexes:
            duplicate = dict(row)
            if duplicate["operator_note"]:
                duplicate["operator_note"] += "; duplicate historian delivery"
            else:
                duplicate["operator_note"] = "duplicate historian delivery"
            rows.append(duplicate)
    if gap_start is not None:
        missing_periods.append(
            {
                "start": (start + gap_start * INTERVAL).isoformat().replace("+00:00", "Z"),
                "end": (start + expected_count * INTERVAL).isoformat().replace("+00:00", "Z"),
            }
        )

    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return {
        "path": path.name,
        "expected_intervals": expected_count,
        "written_rows": len(rows),
        "omitted_timestamp_count": len(missing_indexes),
        "duplicate_timestamp_count": len(duplicate_indexes),
        "missing_timestamp_periods": missing_periods,
        "signal_value_gap_counts": {field: len(indexes) for field, indexes in value_gaps.items()},
    }


def main() -> None:
    target = Path(__file__).resolve().parent
    baseline = _write_period(
        target / "resort-tower-baseline.csv",
        start=BASELINE_START,
        days=BASELINE_DAYS,
        seed_offset=0,
        comparison=False,
    )
    comparison = _write_period(
        target / "resort-tower-comparison.csv",
        start=COMPARISON_START,
        days=COMPARISON_DAYS,
        seed_offset=10_000,
        comparison=True,
    )
    metadata = {
        "generator": Path(__file__).name,
        "seed": SEED,
        "interval_minutes": 5,
        "baseline": baseline,
        "comparison": comparison,
        "simulated_behavior": {
            "comparison_normal_until": CHANGE_START.isoformat().replace("+00:00", "Z"),
            "hydraulic_change_full_at": CHANGE_FULL.isoformat().replace("+00:00", "Z"),
            "recovery_movement_starts_at": RECOVERY_START.isoformat().replace("+00:00", "Z"),
            "baseline_relationships_restored_at": RECOVERY_COMPLETE.isoformat().replace("+00:00", "Z"),
        },
    }
    (target / "generation-metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
