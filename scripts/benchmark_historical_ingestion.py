#!/usr/bin/env python3
"""Generate and profile a realistic deterministic historian export."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

from app.services.dataset_scope import build_dataset_scope, set_current_dataset_scope  # noqa: E402
from app.services.historical_ingestion import build_historical_ingestion  # noqa: E402
from app.services.job_progress import ProgressReporter, update_progress  # noqa: E402
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


def current_rss_bytes() -> int | None:
    try:
        status = Path("/proc/self/status").read_text(encoding="utf-8")
        line = next(item for item in status.splitlines() if item.startswith("VmRSS:"))
        return int(line.split()[1]) * 1024
    except (OSError, StopIteration, ValueError, IndexError):
        return None


def run_ingestion(source: Path, *, dataset_id: str, analysis_rows: int, instrumented: bool) -> dict:
    progress = None
    serialized_bytes = 0
    maximum_snapshot_bytes = 0

    def persist(**values):
        nonlocal progress, serialized_bytes, maximum_snapshot_bytes
        progress = update_progress(
            progress,
            job_id=values.pop("job_id"),
            workflow=values.pop("workflow"),
            **values,
        )
        snapshot_bytes = len(json.dumps(progress, separators=(",", ":"), default=str).encode("utf-8"))
        serialized_bytes += snapshot_bytes
        maximum_snapshot_bytes = max(maximum_snapshot_bytes, snapshot_bytes)
        return progress

    reporter = ProgressReporter(
        job_id=dataset_id,
        workflow="create_baseline",
        persist=persist,
    ) if instrumented else None
    rss_before = current_rss_bytes()
    started = time.perf_counter()
    record, _ = build_historical_ingestion(
        source,
        dataset_id=dataset_id,
        filename=source.name,
        max_analysis_rows=analysis_rows,
        progress_callback=reporter.report if reporter else None,
    )
    elapsed = time.perf_counter() - started
    rss_after = current_rss_bytes()
    return {
        "elapsed_seconds": elapsed,
        "progress_write_count": reporter.write_count if reporter else 0,
        "average_update_frequency_hz": (reporter.write_count / elapsed) if reporter and elapsed > 0 else 0.0,
        "average_seconds_between_updates": (elapsed / reporter.write_count) if reporter and reporter.write_count else None,
        "serialized_progress_bytes": serialized_bytes,
        "maximum_progress_snapshot_bytes": maximum_snapshot_bytes,
        "rss_delta_bytes": (rss_after - rss_before) if rss_before is not None and rss_after is not None else None,
        "record": record,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=25_000)
    parser.add_argument("--signals", type=int, default=48)
    parser.add_argument("--analysis-rows", type=int, default=10_000)
    parser.add_argument("--iterations", type=int, default=2)
    arguments = parser.parse_args()
    if arguments.rows < 6 or arguments.signals < 2 or arguments.iterations < 1:
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

        baseline_runs = []
        instrumented_runs = []
        for iteration in range(arguments.iterations):
            cases = (False, True) if iteration % 2 == 0 else (True, False)
            for instrumented in cases:
                result = run_ingestion(
                    source,
                    dataset_id=f"historical-ingestion-benchmark-{'instrumented' if instrumented else 'baseline'}-{iteration}",
                    analysis_rows=arguments.analysis_rows,
                    instrumented=instrumented,
                )
                (instrumented_runs if instrumented else baseline_runs).append(result)

        baseline_seconds = statistics.median(item["elapsed_seconds"] for item in baseline_runs)
        instrumented_seconds = statistics.median(item["elapsed_seconds"] for item in instrumented_runs)
        overhead_seconds = instrumented_seconds - baseline_seconds
        record = instrumented_runs[-1]["record"]
        performance = dict(record["performance"])
        write_counts = [item["progress_write_count"] for item in instrumented_runs]
        baseline_rss_deltas = [item["rss_delta_bytes"] for item in baseline_runs if item["rss_delta_bytes"] is not None]
        instrumented_rss_deltas = [item["rss_delta_bytes"] for item in instrumented_runs if item["rss_delta_bytes"] is not None]
        report = {
            "contract_version": record["contract_version"],
            "fixture": {
                "rows": arguments.rows,
                "signals": arguments.signals,
                "source_bytes": source.stat().st_size,
                "generation_seconds": round(generation_seconds, 6),
                "iterations_per_case": arguments.iterations,
            },
            "progress_instrumentation": {
                "baseline_median_seconds": round(baseline_seconds, 6),
                "instrumented_median_seconds": round(instrumented_seconds, 6),
                "overhead_seconds": round(overhead_seconds, 6),
                "overhead_percent": round((overhead_seconds / baseline_seconds) * 100, 3) if baseline_seconds else None,
                "write_count_per_run": write_counts,
                "median_write_count": statistics.median(write_counts),
                "average_update_frequency_hz": round(statistics.mean(item["average_update_frequency_hz"] for item in instrumented_runs), 6),
                "average_seconds_between_updates": round(statistics.mean(item["average_seconds_between_updates"] for item in instrumented_runs), 6),
                "serialized_progress_bytes_per_run": [item["serialized_progress_bytes"] for item in instrumented_runs],
                "maximum_progress_snapshot_bytes": max(item["maximum_progress_snapshot_bytes"] for item in instrumented_runs),
                "baseline_median_rss_delta_bytes": statistics.median(baseline_rss_deltas) if baseline_rss_deltas else None,
                "instrumented_median_rss_delta_bytes": statistics.median(instrumented_rss_deltas) if instrumented_rss_deltas else None,
                "estimated_rss_overhead_bytes": (
                    statistics.median(instrumented_rss_deltas) - statistics.median(baseline_rss_deltas)
                    if baseline_rss_deltas and instrumented_rss_deltas else None
                ),
                "write_interval_seconds": 2.0,
            },
            "baseline_run_seconds": [round(item["elapsed_seconds"], 6) for item in baseline_runs],
            "instrumented_run_seconds": [round(item["elapsed_seconds"], 6) for item in instrumented_runs],
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
