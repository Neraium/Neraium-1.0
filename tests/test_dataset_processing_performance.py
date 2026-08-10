from __future__ import annotations

import copy
import json
import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app.engine.sii.common import NumericRowCache, numeric_values, paired_values
from app.engine.sii_engine import evaluate_sii
from app.engine.temporal_math import _column_entropy
from app.services.analysis_provenance import result_digest
from app.services.behavioral_baseline import (
    _BaselineComputationCache,
    _fit_expected_models,
    _identify_modes,
    _learn_distributions,
    _learn_relationship_graph,
    build_behavioral_baseline,
)
from app.services.baseline_contracts import BASELINE_ARTIFACT_CONTRACT_VERSION
from app.services.data_quality import profile_numeric_columns
from app.services.performance_instrumentation import PERFORMANCE_CONTRACT_VERSION
from app.services.upload_jobs import _comparison_relationship_changes, process_csv_content
from scripts.benchmark_dataset_processing import BenchmarkCase, run_case


_RUNTIME_KEYS = {
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


def _rows(row_count: int = 120, signal_count: int = 6) -> tuple[list[str], list[dict[str, object]]]:
    columns = [
        "timestamp",
        "equipment_stage",
        *[f"process_signal_{index:02d}" for index in range(signal_count)],
    ]
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows: list[dict[str, object]] = []
    for index in range(row_count):
        stage = 1 if (index // max(1, row_count // 4)) % 2 == 0 else 2
        base = 30.0 + stage * 7.0 + math.sin(index / 9.0) * 2.0
        row: dict[str, object] = {
            "timestamp": (started + timedelta(minutes=5 * index)).isoformat().replace("+00:00", "Z"),
            "equipment_stage": stage,
        }
        for signal_index in range(signal_count):
            row[f"process_signal_{signal_index:02d}"] = (
                None
                if signal_index == 2 and index % 41 == 0
                else base * (1.0 + signal_index * 0.06) + math.cos(index / (5.0 + signal_index)) * 0.15
            )
        rows.append(row)
    return columns, rows


def _profiles(columns: list[str], rows: list[dict[str, object]]) -> list[dict[str, object]]:
    matrix = [[str(row.get(column, "")) for column in columns] for row in rows]
    return [
        {**item, "minimum": item.get("min"), "maximum": item.get("max")}
        for item in profile_numeric_columns(columns, matrix)
    ]


def _without_runtime(value):
    if isinstance(value, dict):
        return {
            key: _without_runtime(item)
            for key, item in value.items()
            if key not in _RUNTIME_KEYS
        }
    if isinstance(value, list):
        return [_without_runtime(item) for item in value]
    return value


def test_job_local_baseline_cache_is_semantically_equivalent() -> None:
    columns, rows = _rows(row_count=144, signal_count=7)
    numeric_columns = columns[1:]
    modes, membership = _identify_modes(rows, columns, numeric_columns, {})

    uncached_distributions = _learn_distributions(rows, numeric_columns, modes, membership)
    cache = _BaselineComputationCache(rows)
    cached_distributions = _learn_distributions(
        rows,
        numeric_columns,
        modes,
        membership,
        cache=cache,
    )
    assert cached_distributions == uncached_distributions

    uncached_graph = _learn_relationship_graph(rows, numeric_columns, modes, membership)
    performance_counts: dict[str, int] = {}
    cached_graph = _learn_relationship_graph(
        rows,
        numeric_columns,
        modes,
        membership,
        cache=cache,
        performance_counts=performance_counts,
    )
    assert performance_counts["cache_hits"] > 0
    assert cached_graph == uncached_graph
    assert _fit_expected_models(rows, cached_graph, membership, cache=cache) == _fit_expected_models(
        rows,
        uncached_graph,
        membership,
    )


def test_baseline_job_persists_versioned_artifacts_and_stage_report() -> None:
    columns, rows = _rows(row_count=72, signal_count=4)
    profiles = _profiles(columns, rows)
    result = build_behavioral_baseline(
        job_id="performance-baseline-job",
        filename="performance-baseline.csv",
        columns=columns,
        rows=rows,
        numeric_columns=columns[1:],
        timestamp_column="timestamp",
        row_count_total=len(rows),
        numeric_profiles=profiles,
        ingestion_report={"header_present": True},
    )

    performance = result["processing_trace"]["performance"]
    stages = {item["stage"] for item in performance["stages"]}
    assert {
        "select_usable_signals",
        "operating_context_construction",
        "baseline_statistics",
        "relationship_learning",
        "expected_model_fitting",
        "finalization",
    } <= stages
    model = result["candidate_model"]
    assert model["artifact_contract_version"] == BASELINE_ARTIFACT_CONTRACT_VERSION
    assert model["reusable_artifacts"]["contract_version"] == BASELINE_ARTIFACT_CONTRACT_VERSION


def test_numeric_row_cache_preserves_missing_value_alignment_and_is_job_scoped() -> None:
    first = [{"a": "1", "b": "2"}, {"a": None, "b": "3"}, {"a": "4", "b": None}]
    second = [{"a": "100", "b": "200"}]
    first_cache = NumericRowCache()
    second_cache = NumericRowCache()

    assert numeric_values(first, "a", cache=first_cache) == numeric_values(first, "a")
    assert paired_values(first, "a", "b", cache=first_cache) == paired_values(first, "a", "b")
    assert numeric_values(second, "a", cache=second_cache) == [100.0]
    assert numeric_values(second, "a", cache=second_cache) != numeric_values(first, "a", cache=first_cache)
    assert first_cache.hits > 0


@pytest.mark.parametrize(
    "values",
    [
        np.linspace(0.0, 1.0, 13),
        np.linspace(-1.0, 1.0, 25),
        np.ones(24),
        np.asarray([0.0, 0.5, 1.0]),
        np.random.default_rng(7).normal(size=24),
    ],
)
def test_specialized_entropy_matches_numpy_histogram_exactly(values: np.ndarray) -> None:
    assert _column_entropy(values) == pytest.approx(
        _column_entropy(values, use_specialized_histogram=False),
        abs=1e-15,
        rel=0.0,
    )


def test_sii_optimized_and_reference_paths_have_identical_intelligence() -> None:
    columns, rows = _rows(row_count=180, signal_count=8)
    profiles = _profiles(columns, rows)
    config = {
        "numeric_columns": columns[1:],
        "row_count_total": len(rows),
        "temporal_config": {"max_rows": len(rows)},
    }
    reference = evaluate_sii(
        columns=columns,
        rows=rows,
        numeric_profiles=profiles,
        timestamp_column="timestamp",
        config={**config, "disable_performance_caches": True},
    )
    optimized = evaluate_sii(
        columns=columns,
        rows=rows,
        numeric_profiles=profiles,
        timestamp_column="timestamp",
        config=config,
    )

    assert _without_runtime(optimized) == _without_runtime(reference)
    report = optimized["processing_trace"]["performance"]
    stage_names = {item["stage"] for item in report["stages"]}
    assert {
        "signal_drift",
        "relationship_analysis",
        "operating_mode_analysis",
        "data_condition_checks",
        "sensor_health",
        "empirical_thresholds",
        "mode_conditioned_baseline_comparison",
        "relationship_graph_analysis",
        "fixed_persistence",
        "adaptive_persistence",
        "temporal_lag_analysis",
        "multiscale_analysis",
        "covariance_analysis",
        "physics_reasoning",
        "behavioral_modeling",
        "evidence_fusion",
        "finalization",
    } <= stage_names
    assert report["total_wall_seconds"] >= 0
    assert report["total_cpu_seconds"] >= 0
    assert report["compact_summary"]
    assert report["totals"]["temporal_pairs"] >= 0
    assert report["totals"]["multiscale_pairs"] >= 0
    assert "process_signal" not in json.dumps(report)


def test_full_upload_report_includes_validation_and_canonical_stages() -> None:
    columns, rows = _rows(row_count=48, signal_count=4)
    content = "\n".join(
        [",".join(columns)]
        + [",".join("" if row.get(column) is None else str(row.get(column)) for column in columns) for row in rows]
    )
    result = process_csv_content(content=content.encode(), filename="performance-report.csv")
    report = result["processing_trace"]["performance"]
    stages = {item["stage"] for item in report["stages"]}

    assert {
        "validation",
        "schema_timestamp_processing",
        "semantic_mapping",
        "canonical_dataset_build",
        "canonical_persistence",
        "result_finalization",
        "evidence_persistence",
    } <= stages
    assert report["totals"]["rows_processed"] == 48
    assert report["total_wall_seconds"] == result["processing_time_seconds"]


def test_baseline_artifact_reuse_is_versioned_and_reports_cache_reuse() -> None:
    _columns, rows = _rows(row_count=60, signal_count=2)
    model = {
        "contract_version": "behavioral-digital-model.v1",
        "artifact_contract_version": BASELINE_ARTIFACT_CONTRACT_VERSION,
        "relationship_graph": {
            "edges": [
                {
                    "edge_id": "all_operation:a:b",
                    "mode_id": "all_operation",
                    "source": "process_signal_00",
                    "target": "process_signal_01",
                    "correlation": 0.95,
                    "sample_count": 60,
                }
            ]
        },
    }
    counts: dict[str, int] = {}
    first = _comparison_relationship_changes(model, rows, performance_counts=counts)
    second = _comparison_relationship_changes(copy.deepcopy(model), rows)

    assert first == second
    assert counts["baseline_artifacts_reused"] == 1
    assert counts["relationship_pairs_considered"] == 1
    incompatible = {**model, "artifact_contract_version": "behavioral-baseline-artifacts.v999"}
    with pytest.raises(ValueError, match="incompatible_baseline_artifacts"):
        _comparison_relationship_changes(incompatible, rows)


def test_reproducible_benchmark_runs_without_absolute_timing_assertions() -> None:
    report = run_case(BenchmarkCase("ci", rows=72, signals=4))

    assert report["case"] == {"name": "ci", "rows": 72, "signals": 4}
    assert report["baseline_learning"]["semantic_fingerprint"]
    assert report["comparison_analysis"]["semantic_fingerprint"]
    assert report["baseline_learning"]["pair_counts"]["candidate_pairs"] > 0
    assert report["comparison_analysis"]["before"]["median_wall_seconds"] >= 0
    assert report["comparison_analysis"]["after"]["median_wall_seconds"] >= 0


def test_performance_diagnostics_do_not_change_intelligence_provenance() -> None:
    base = {
        "sii_result": {
            "overall_result": "needs_review",
            "processing_trace": {
                "performance": {
                    "contract_version": PERFORMANCE_CONTRACT_VERSION,
                    "total_wall_seconds": 10.0,
                }
            },
        }
    }
    faster = copy.deepcopy(base)
    faster["sii_result"]["processing_trace"]["performance"] = {
        "contract_version": PERFORMANCE_CONTRACT_VERSION,
        "total_wall_seconds": 1.0,
        "cache_hits": 50,
    }

    assert result_digest(base) == result_digest(faster)
    domain_change = copy.deepcopy(base)
    domain_change["sii_result"]["performance"] = {"efficiency": "degraded"}
    assert result_digest(base) != result_digest(domain_change)
