"""Generate deterministic chilled-water baseline and degraded comparison telemetry."""

from __future__ import annotations

import csv
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path


OUTPUT_DIR = Path(__file__).resolve().parent
FIELDS = [
    "timestamp",
    "pump_power_kw",
    "chw_flow_gpm",
    "chw_supply_temp_f",
    "chw_return_temp_f",
    "valve_position_pct",
    "differential_pressure_psi",
    "cooling_demand_tons",
]


def rows(start: datetime, degraded: bool) -> list[dict[str, str]]:
    result = []
    for index in range(7 * 24 * 4):
        timestamp = start + timedelta(minutes=15 * index)
        hour = timestamp.hour + timestamp.minute / 60
        occupied = max(0.0, math.sin(math.pi * (hour - 6) / 16))
        daily = 190 + 300 * occupied
        variation = 18 * math.sin(index * 0.37) + 8 * math.cos(index * 0.11)
        demand = daily + variation
        flow = 410 + demand * 1.52 + 7 * math.sin(index * 0.23)
        valve = min(94, 25 + demand * 0.135 + 1.8 * math.sin(index * 0.19))
        pressure = 8.2 + 0.0145 * flow + 0.22 * math.cos(index * 0.17)
        supply = 42.1 + 0.18 * math.sin(index * 0.09)
        return_temp = supply + demand * 24 / (flow * 0.5) + 0.08 * math.cos(index * 0.29)
        # Persistent pump/VFD degradation: flow and hydraulic conditions remain
        # comparable while electrical power rises and begins cycling independently
        # of load, weakening the learned pump-power-to-flow relationship.
        normal_power = 12 + 0.000047 * flow**2 + 0.35 * pressure
        pump_power = normal_power * 1.45 + 35 * math.sin(index * 0.73) if degraded else normal_power
        result.append({
            "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
            "pump_power_kw": f"{pump_power:.3f}",
            "chw_flow_gpm": f"{flow:.3f}",
            "chw_supply_temp_f": f"{supply:.3f}",
            "chw_return_temp_f": f"{return_temp:.3f}",
            "valve_position_pct": f"{valve:.3f}",
            "differential_pressure_psi": f"{pressure:.3f}",
            "cooling_demand_tons": f"{demand:.3f}",
        })
    return result


def write(name: str, data: list[dict[str, str]]) -> None:
    with (OUTPUT_DIR / name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(data)


if __name__ == "__main__":
    write("chilled-water-baseline.csv", rows(datetime(2026, 6, 1, tzinfo=timezone.utc), False))
    write("chilled-water-pump-degradation.csv", rows(datetime(2026, 6, 15, tzinfo=timezone.utc), True))
