from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
import random


ROOT = Path(__file__).resolve().parent


def write_csv(name: str, columns: list[str], rows: list[list[object]]) -> None:
    path = ROOT / name
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)


def clean_historian() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(96):
        timestamp = (start + timedelta(minutes=15 * index)).isoformat().replace("+00:00", "Z")
        rows.append([
            timestamp,
            round(42 + (index % 12) * 0.2, 2),
            round(53 + (index % 10) * 0.25, 2),
            round(820 + (index % 16) * 8, 2),
            round(11 + (index % 8) * 0.3, 2),
            1 if index % 24 >= 4 else 0,
        ])
    write_csv(
        "clean_historian.csv",
        ["Timestamp", "CHW Supply Temp F", "CHW Return Temp F", "Flow GPM", "Differential Pressure PSI", "Pump Status"],
        rows,
    )


def messy_industrial() -> None:
    rng = random.Random(7401)
    start = datetime(2026, 2, 1, tzinfo=timezone.utc)
    rows: list[list[object]] = []
    for index in range(120):
        # Add a deterministic one-minute slip every five records so the export
        # has a real interval distribution rather than one isolated gap.
        timestamp = start + timedelta(minutes=5 * index + index // 5)
        if index >= 70:
            timestamp += timedelta(hours=3)
        supply_f: object = f"{43 + (index % 9) * 0.3:.2f} F"
        pressure: object = f"{75 + (index % 7):.2f} psi"
        valve: object = f"{min(100, (index % 22) * 5)}%"
        damper_fraction = round((index % 21) / 20, 3)
        sparse: object = "" if index % 3 else round(10 + index * 0.1, 2)
        mixed: object = "manual" if index in {17, 49} else round(30 + rng.uniform(-3, 3), 3)
        rows.append([
            timestamp.isoformat().replace("+00:00", "Z"),
            supply_f,
            round((43 - 32) * 5 / 9 + (index % 5) * 0.2, 3),
            pressure,
            round(517 + (index % 7) * 6.894757293168, 3),
            valve,
            damper_fraction,
            47.0,
            round(1500 + rng.uniform(-180, 180), 3),
            100 if index % 12 >= 4 else index % 4 * 25,
            round(900 + (index % 11) * 2, 3),
            round(900 + (index % 11) * 2, 3),
            sparse,
            1 if index >= 60 else 0,
            round(25 + index * 0.05, 3),
            mixed,
        ])
    rows.insert(22, list(rows[21]))
    rows[35][0], rows[36][0] = rows[36][0], rows[35][0]
    rows[50][0] = "not-a-date"
    rows[51][0] = ""
    rows[77][1] = ""
    write_csv(
        "messy_industrial.csv",
        [
            "Timestamp", "Supply Temp F", "Supply Temp C", "Header Pressure psi", "Pressure kPa",
            "Valve Position %", "Damper Command fraction", "Stuck Sensor", "Noisy Sensor", "Clipped Load %", "Flow A", "Flow B",
            "Sparse Signal", "Chiller Stage", "Mystery Flow", "Mixed Signal",
        ],
        rows,
    )


def multiple_timestamps() -> None:
    rows = [
        [f"2026-03-01T00:{index:02d}:00Z", f"2026-03-01T00:{index:02d}:01Z", 40 + index, 8 + index]
        for index in range(12)
    ]
    write_csv("multiple_timestamp_candidates.csv", ["Timestamp", "Recorded At", "Supply Temp F", "Flow GPM"], rows)


def timezone_edges() -> None:
    rows = [
        ["2026-11-01T01:00:00-04:00", 44, 10],
        ["2026-11-01T01:30:00-04:00", 45, 11],
        ["2026-11-01T01:00:00-05:00", 46, 12],
        ["2026-11-01T01:30:00-05:00", 47, 13],
        ["2026-11-01T02:00:00-05:00", 48, 14],
        ["2026-11-01T02:30:00-05:00", 49, 15],
    ]
    write_csv("timezone_dst_edges.csv", ["Timestamp", "Supply Temp F", "Pressure psi"], rows)


def malformed_export() -> None:
    path = ROOT / "malformed_export.csv"
    path.write_text(
        "Timestamp,Supply Temp F,Pressure psi,Comment\n"
        "2026-04-01T00:00:00Z,44 F,10 psi,ok\n"
        "2026-04-01T00:05:00Z,45 F\n"
        "2026-02-31T00:10:00Z,bad,inf,bad date\n"
        "2026-04-01T00:15:00Z,46 F,11 psi,manual override\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    ROOT.mkdir(parents=True, exist_ok=True)
    clean_historian()
    messy_industrial()
    multiple_timestamps()
    timezone_edges()
    malformed_export()
