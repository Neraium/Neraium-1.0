#!/usr/bin/env python3
"""Benchmark deterministic baseline learning and comparison analysis workloads."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
import time
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

from app.engine.sii_engine import evaluate_sii  # noqa: E402
from app.services.behavioral_baseline import (  # noqa: E402
    _BaselineComputationCache,
    _fit_expected_models,
    _identify_modes,
    _learn_distributions,
    _learn_relationship_graph,
)
from app.services.data_quality import profile_numeric_columns  # noqa: E402


@dataclass(frozen=True)
class BenchmarkCase:
    name: str
    rows: int
    signals: int


CASES = {
    "small": BenchmarkCase("small", rows=240, signals=6),
    "medium": BenchmarkCase("medium", rows=1_200, signals=14),
    "high-signal": BenchmarkCase("high-signal", rows=3_000, signals=24),
}
_RUNTIME_KEYS = {
    "cache_hits",
    "completed_at",
    "created_at",
    "performance",
    "run_id",
    "runtime_seconds",
    "step_timings",
    "timestamp",
    "total_runtime_seconds",
    "upload_id",
}


def generate_rows(case: BenchmarkCase) -> tuple[list[str], list[dict[str, object]]]:
    columns = [
        "timestamp",
        "equipment_stage",
        *[f"process_signal_{index:02d}" for index in range(case.signals)],
    ]
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows: list[dict[str, object]] = []
    for row_index in range(case.rows):
        stage = 1 if (row_index // max(1, case.rows // 8)) % 2 == 0 else 2
        load = 30.0 + stage * 7.0 + math.sin(row_index / 17.0) * 2.0
        row: dict[str, object] = {
            "timestamp": (started + timedelta(minutes=5 * row_index)).isoformat().replace("+00:00", "Z"),
            "equipment_stage": stage,
        }
        for signal_index in range(case.signals):
            cycle = math.cos(row_index / (5.0 + signal_index % 7)) * 0.15
            value = load * (1.0 + signal_index * 0.035) + cycle
            row[f"process_signal_{signal_index:02d}"] = (
                None if signal_index % 5 == 2 and row_index % 997 == 0 else round(value, 8)
            )
        rows.append(row)
    return columns, rows


def numeric_profiles(
    columns: list[str],
    rows: list[dict[str, object]],
) -> list[dict[str, Any]]:
    matrix = [[str(row.get(column, "")) for column in columns] for row in rows]
    return [
        {**item, "minimum": item.get("min"), "maximum": item.get("max")}
        for item in profile_numeric_columns(columns, matrix)
    ]


def _scrub_runtime(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _scrub_runtime(item)
            for key, item in value.items()
            if key not in _RUNTIME_KEYS
        }
    if isinstance(value, list):
        return [_scrub_runtime(item) for item in value]
    return value


def semantic_fingerprint(value: Any) -> str:
    encoded = json.dumps(
        _scrub_runtime(value),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def peak_rss_bytes() -> int | None:
    try:
        import resource

        peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return peak if os.uname().sysname == "Darwin" else peak * 1024
    except (ImportError, OSError, ValueError):
        return None


def _measure(function) -> dict[str, Any]:
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    output = function()
    return {
        "wall_seconds": time.perf_counter() - wall_started,
        "cpu_seconds": time.process_time() - cpu_started,
        "peak_process_rss_bytes": peak_rss_bytes(),
        "output": output,
    }


def run_baseline_learning(
    columns: list[str],
    rows: list[dict[str, object]],
    *,
    optimized: bool,
) -> dict[str, Any]:
    numeric_columns = columns[1:]
    stages: dict[str, float] = {}
    cache = _BaselineComputationCache(rows) if optimized else None

    stage_started = time.perf_counter()
    modes, membership = _identify_modes(rows, columns, numeric_columns, {})
    stages["operating_context_construction"] = time.perf_counter() - stage_started

    stage_started = time.perf_counter()
    distributions = _learn_distributions(
        rows,
        numeric_columns,
        modes,
        membership,
        cache=cache,
    )
    stages["baseline_statistics"] = time.perf_counter() - stage_started

    stage_started = time.perf_counter()
    relationship_counts: dict[str, int] = {}
    graph = _learn_relationship_graph(
        rows,
        numeric_columns,
        modes,
        membership,
        cache=cache,
        performance_counts=relationship_counts,
    )
    stages["relationship_learning"] = time.perf_counter() - stage_started

    stage_started = time.perf_counter()
    models = _fit_expected_models(rows, graph, membership, cache=cache)
    stages["expected_model_fitting"] = time.perf_counter() - stage_started
    return {
        "intelligence": {
            "operating_modes": modes,
            "signal_characteristics": distributions,
            "relationship_graph": graph,
            "expected_behavior_models": models,
        },
        "stage_wall_seconds": stages,
        "pair_counts": {
            "candidate_pairs": relationship_counts.get("relationship_pairs_considered", 0),
            "eligible_pairs": relationship_counts.get("relationship_pairs_eligible", 0),
            "deep_analysis_pairs": relationship_counts.get("relationship_pairs_deeply_analyzed", 0),
        },
    }


def run_comparison(
    columns: list[str],
    rows: list[dict[str, object]],
    profiles: list[dict[str, Any]],
    *,
    optimized: bool,
) -> dict[str, Any]:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="invalid value encountered in divide")
        return evaluate_sii(
            columns=columns,
            rows=rows,
            numeric_profiles=profiles,
            timestamp_column="timestamp",
            config={
                "numeric_columns": columns[1:],
                "row_count_total": len(rows),
                "temporal_config": {"max_rows": len(rows)},
                "disable_performance_caches": not optimized,
            },
        )


def _median_measurements(measurements: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "median_wall_seconds": round(statistics.median(item["wall_seconds"] for item in measurements), 6),
        "median_cpu_seconds": round(statistics.median(item["cpu_seconds"] for item in measurements), 6),
        "peak_process_rss_bytes": max(
            (item["peak_process_rss_bytes"] for item in measurements if item["peak_process_rss_bytes"] is not None),
            default=None,
        ),
    }


def _improvement_percent(before: float, after: float) -> float | None:
    return round((before - after) / before * 100.0, 3) if before > 0 else None


def _throughput(count: int, duration: float) -> float | None:
    return round(count / duration, 3) if duration > 0 else None


def run_case(case: BenchmarkCase, *, iterations: int = 1) -> dict[str, Any]:
    columns, rows = generate_rows(case)
    profiles = numeric_profiles(columns, rows)
    baseline_reference: list[dict[str, Any]] = []
    baseline_optimized: list[dict[str, Any]] = []
    comparison_reference: list[dict[str, Any]] = []
    comparison_optimized: list[dict[str, Any]] = []

    for iteration in range(iterations):
        order = (False, True) if iteration % 2 == 0 else (True, False)
        for optimized in order:
            baseline = _measure(
                lambda optimized=optimized: run_baseline_learning(
                    columns,
                    rows,
                    optimized=optimized,
                )
            )
            (baseline_optimized if optimized else baseline_reference).append(baseline)
            comparison = _measure(
                lambda optimized=optimized: run_comparison(
                    columns,
                    rows,
                    profiles,
                    optimized=optimized,
                )
            )
            (comparison_optimized if optimized else comparison_reference).append(comparison)

    baseline_reference_fingerprint = semantic_fingerprint(baseline_reference[-1]["output"]["intelligence"])
    baseline_optimized_fingerprint = semantic_fingerprint(baseline_optimized[-1]["output"]["intelligence"])
    comparison_reference_fingerprint = semantic_fingerprint(comparison_reference[-1]["output"])
    comparison_optimized_fingerprint = semantic_fingerprint(comparison_optimized[-1]["output"])
    if baseline_reference_fingerprint != baseline_optimized_fingerprint:
        raise RuntimeError(f"{case.name}: baseline semantic fingerprint mismatch")
    if comparison_reference_fingerprint != comparison_optimized_fingerprint:
        raise RuntimeError(f"{case.name}: comparison semantic fingerprint mismatch")

    baseline_before = _median_measurements(baseline_reference)
    baseline_after = _median_measurements(baseline_optimized)
    comparison_before = _median_measurements(comparison_reference)
    comparison_after = _median_measurements(comparison_optimized)
    optimized_baseline = baseline_optimized[-1]["output"]
    reference_baseline = baseline_reference[-1]["output"]
    optimized_comparison = comparison_optimized[-1]["output"]
    reference_comparison = comparison_reference[-1]["output"]
    performance = optimized_comparison["processing_trace"]["performance"]
    reference_performance = reference_comparison["processing_trace"]["performance"]
    comparison_stages_after = {
        item["stage"]: item["wall_seconds"]
        for item in performance["stages"]
    }
    comparison_stages_before = {
        item["stage"]: item["wall_seconds"]
        for item in reference_performance["stages"]
    }
    baseline_pair_count = int(optimized_baseline["pair_counts"]["candidate_pairs"])
    comparison_pair_count = int(
        performance["totals"].get("relationship_pairs_considered") or 0
    )
    return {
        "case": {"name": case.name, "rows": case.rows, "signals": case.signals},
        "iterations_per_path": iterations,
        "baseline_learning": {
            "before": baseline_before,
            "after": baseline_after,
            "wall_improvement_percent": _improvement_percent(
                baseline_before["median_wall_seconds"],
                baseline_after["median_wall_seconds"],
            ),
            "stage_wall_seconds_before": {
                key: round(value, 6)
                for key, value in reference_baseline["stage_wall_seconds"].items()
            },
            "stage_wall_seconds_after": {
                key: round(value, 6)
                for key, value in optimized_baseline["stage_wall_seconds"].items()
            },
            "pair_counts": optimized_baseline["pair_counts"],
            "relationship_throughput_pairs_per_second": {
                "before": _throughput(
                    baseline_pair_count,
                    reference_baseline["stage_wall_seconds"]["relationship_learning"],
                ),
                "after": _throughput(
                    baseline_pair_count,
                    optimized_baseline["stage_wall_seconds"]["relationship_learning"],
                ),
            },
            "semantic_fingerprint": baseline_optimized_fingerprint,
        },
        "comparison_analysis": {
            "before": comparison_before,
            "after": comparison_after,
            "wall_improvement_percent": _improvement_percent(
                comparison_before["median_wall_seconds"],
                comparison_after["median_wall_seconds"],
            ),
            "stage_wall_seconds_before": comparison_stages_before,
            "stage_wall_seconds_after": comparison_stages_after,
            "relationship_throughput_pairs_per_second": {
                "before": _throughput(
                    comparison_pair_count,
                    comparison_stages_before.get("relationship_analysis", 0.0),
                ),
                "after": _throughput(
                    comparison_pair_count,
                    comparison_stages_after.get("relationship_analysis", 0.0),
                ),
            },
            "pair_counts": {
                key: value
                for key, value in performance["totals"].items()
                if key.startswith("relationship_pairs")
            },
            "semantic_fingerprint": comparison_optimized_fingerprint,
        },
        "memory_note": "Peak RSS is the whole benchmark process high-water mark, not isolated allocation usage.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case",
        action="append",
        choices=sorted(CASES),
        help="Benchmark case to run; repeat to select multiple cases (default: all).",
    )
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    if arguments.iterations < 1:
        parser.error("--iterations must be at least 1")

    selected = arguments.case or list(CASES)
    report = {
        "contract_version": "dataset-processing-benchmark.v1",
        "methodology": {
            "paths": ["reference", "optimized"],
            "order": "alternated per iteration",
            "timing": "median wall and process CPU duration",
            "semantic_check": "SHA-256 of runtime-metadata-free output",
        },
        "cases": [run_case(CASES[name], iterations=arguments.iterations) for name in selected],
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if arguments.output:
        arguments.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
