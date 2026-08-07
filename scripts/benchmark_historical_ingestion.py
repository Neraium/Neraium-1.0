#!/usr/bin/env python3
"""Generate and profile a realistic deterministic historian export."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

from app.services.dataset_scope import build_dataset_scope, set_current_dataset_scope  # noqa: E402
from app.services.historical_ingestion import build_historical_ingestion  # noqa: E402
from app.services.upload_state_repository import configure_runtime_dir  # noqa: E402


def generate_export(path: Path, *, rows: int, signals: int) -> None:
    headers = ["Timestamp"]
    for index in range(signals):
        family = index % 6
        if family == 0:
            headers.append(f"AHU-{index:03d} Supply Temp F")
        elif family == 1:
            headers.append(f"CHW-{index:03d} Flow gpm")
        elif family == 2:
            headers.append(f"Pump-{index:03d} Pressure psi")
        elif family == 3:
            headers.append(f"Fan-{index:03d} Speed Hz")
        elif family == 4:
            headers.append(f"Valve-{index:03d} Position %")
        else:
            headers.append(f"Meter-{index:03d} Power kW")

    started = datetime(2025, 1, 1, tzinfo=timezone.utc)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for row_index in range(rows):
            timestamp = started + timedelta(minutes=5 * row_index)
            values: list[str | float] = [timestamp.isoformat().replace("+00:00", "Z")]
            for signal_index in range(signals):
                baseline = 20.0 + signal_index * 0.7
                cycle = math.sin((row_index + signal_index) / 37.0) * (2.0 + signal_index % 5)
                value = baseline + cycle + ((row_index % 17) * 0.013)
                values.append("" if (row_index + signal_index * 13) % 997 == 0 else round(value, 6))
            writer.writerow(values)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=25_000)
    parser.add_argument("--signals", type=int, default=48)
    parser.add_argument("--analysis-rows", type=int, default=10_000)
    arguments = parser.parse_args()
    if arguments.rows < 6 or arguments.signals < 2:
        parser.error("--rows must be at least 6 and --signals must be at least 2")

    with tempfile.TemporaryDirectory(prefix="neraium-ingestion-benchmark-") as directory:
        root = Path(directory)
        runtime = root / "runtime"
        runtime.mkdir()
        configure_runtime_dir(runtime)
        set_current_dataset_scope(build_dataset_scope(user_id="benchmark@local", workspace_id="benchmark"))
        source = root / "realistic-historian.csv"
        generation_started = time.perf_counter()
        generate_export(source, rows=arguments.rows, signals=arguments.signals)
        generation_seconds = time.perf_counter() - generation_started

        wall_started = time.perf_counter()
        record, _ = build_historical_ingestion(
            source,
            dataset_id="historical-ingestion-benchmark",
            filename=source.name,
            max_analysis_rows=arguments.analysis_rows,
        )
        wall_seconds = time.perf_counter() - wall_started
        performance = dict(record["performance"])
        report = {
            "contract_version": record["contract_version"],
            "fixture": {
                "rows": arguments.rows,
                "signals": arguments.signals,
                "source_bytes": source.stat().st_size,
                "generation_seconds": round(generation_seconds, 6),
            },
            "upload_processing_seconds": round(wall_seconds, 6),
            "parsing_seconds": performance["parsing_seconds"],
            "schema_and_timestamp_profiling_seconds": performance["schema_and_timestamp_profiling_seconds"],
            "mapping_seconds": performance["mapping_seconds"],
            "quality_profiling_seconds": performance["quality_profiling_seconds"],
            "normalization_seconds": performance["canonical_normalization_seconds"],
            "canonical_persistence_seconds": performance["canonical_persistence_seconds"],
            "total_ingestion_to_readiness_seconds": performance["total_ingestion_to_readiness_seconds"],
            "peak_process_rss_bytes": performance["peak_process_rss_bytes"],
            "canonical_rows": record["canonical_dataset"]["row_count"],
            "analysis_sample_rows": record["canonical_dataset"]["analysis_sample_rows"],
            "readiness": record["readiness"]["outcome"],
        }
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
