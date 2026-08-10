from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

try:
    import resource
except ImportError:  # pragma: no cover - Windows fallback
    resource = None  # type: ignore[assignment]


PERFORMANCE_CONTRACT_VERSION = "dataset-processing-performance.v1"
_MAX_TOTAL_COUNTERS = {
    "rows_processed",
    "signals_processed",
    "relationship_pairs_considered",
    "relationship_pairs_eligible",
    "relationship_pairs_deeply_analyzed",
}


def _peak_rss_bytes() -> int | None:
    if resource is None:
        return None
    peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    # Linux reports KiB; macOS reports bytes.
    return peak if os.uname().sysname == "Darwin" else peak * 1024


def _clean_counts(values: dict[str, Any]) -> dict[str, int]:
    cleaned: dict[str, int] = {}
    for key, value in values.items():
        if value is None:
            continue
        try:
            number = max(0, int(value))
        except (TypeError, ValueError):
            continue
        cleaned[str(key)] = number
    return cleaned


@dataclass
class _ActiveStage:
    name: str
    wall_started: float
    cpu_started: float
    counters: dict[str, int] = field(default_factory=dict)


class PerformanceTracker:
    """Low-overhead, data-free timing and work-count instrumentation.

    Trackers are deliberately job-local. They hold no module-level cache or raw
    telemetry, so one dataset/job/facility cannot affect another job's report.
    """

    def __init__(
        self,
        *,
        rows: int = 0,
        signals: int = 0,
        seed_stages: Iterable[dict[str, Any]] | None = None,
        seed_peak_memory_bytes: int | None = None,
        seed_wall_seconds: float = 0.0,
        seed_cpu_seconds: float = 0.0,
    ) -> None:
        self._wall_started = time.perf_counter()
        self._cpu_started = time.process_time()
        self._active: _ActiveStage | None = None
        self._stages: list[dict[str, Any]] = [dict(item) for item in (seed_stages or [])]
        self._totals = _clean_counts({"rows_processed": rows, "signals_processed": signals})
        self._starting_peak_memory_bytes = _peak_rss_bytes()
        self._seed_peak_memory_bytes = seed_peak_memory_bytes
        self._seed_wall_seconds = max(0.0, float(seed_wall_seconds))
        self._seed_cpu_seconds = max(0.0, float(seed_cpu_seconds))

    def start_stage(self, name: str, **counters: Any) -> None:
        self.finish_stage()
        self._active = _ActiveStage(
            name=str(name),
            wall_started=time.perf_counter(),
            cpu_started=time.process_time(),
            counters=_clean_counts(counters),
        )

    def update(self, **counters: Any) -> None:
        cleaned = _clean_counts(counters)
        if self._active is None:
            for key, value in cleaned.items():
                self._totals[key] = max(self._totals.get(key, 0), value)
            return
        for key, value in cleaned.items():
            self._active.counters[key] = max(self._active.counters.get(key, 0), value)

    def increment(self, **counters: Any) -> None:
        cleaned = _clean_counts(counters)
        target = self._active.counters if self._active is not None else self._totals
        for key, value in cleaned.items():
            target[key] = target.get(key, 0) + value

    def progress(self, completed: int, total: int, unit_type: str | None) -> None:
        if not unit_type:
            return
        key = {
            "relationship_pairs": "relationship_pairs_considered",
            "relationship_edges": "relationship_pairs_deeply_analyzed",
            "temporal_calculations": "windows_evaluated",
            "context_windows": "windows_evaluated",
            "mode_rows": "rows_processed",
            "scales": "scales_evaluated",
            "relationship_models": "models_evaluated",
            "model_components": "models_evaluated",
            "evidence_candidates": "evidence_candidates_processed",
            "sensor_vectors": "rows_processed",
            "signals": "signals_processed",
            "health_checks": "signals_processed",
            "threshold_candidates": "threshold_candidates_processed",
            "rules": "models_evaluated",
        }.get(str(unit_type), str(unit_type))
        self.update(**{key: total if total > 0 else completed})

    def finish_stage(self, **counters: Any) -> None:
        if self._active is None:
            return
        self.update(**counters)
        now_wall = time.perf_counter()
        now_cpu = time.process_time()
        stage = {
            "stage": self._active.name,
            "wall_seconds": round(max(0.0, now_wall - self._active.wall_started), 6),
            "cpu_seconds": round(max(0.0, now_cpu - self._active.cpu_started), 6),
            "counters": dict(self._active.counters),
        }
        self._stages.append(stage)
        for key, value in self._active.counters.items():
            if key in _MAX_TOTAL_COUNTERS:
                self._totals[key] = max(self._totals.get(key, 0), value)
            else:
                self._totals[key] = self._totals.get(key, 0) + value
        self._active = None

    def report(self, **totals: Any) -> dict[str, Any]:
        self.finish_stage()
        for key, value in _clean_counts(totals).items():
            self._totals[key] = max(self._totals.get(key, 0), value)
        peak_candidates = [
            value
            for value in (
                self._seed_peak_memory_bytes,
                self._starting_peak_memory_bytes,
                _peak_rss_bytes(),
            )
            if value is not None
        ]
        report = {
            "contract_version": PERFORMANCE_CONTRACT_VERSION,
            "stages": list(self._stages),
            "totals": dict(self._totals),
            "total_wall_seconds": round(
                self._seed_wall_seconds + max(0.0, time.perf_counter() - self._wall_started),
                6,
            ),
            "total_cpu_seconds": round(
                self._seed_cpu_seconds + max(0.0, time.process_time() - self._cpu_started),
                6,
            ),
            "approximate_peak_memory_bytes": max(peak_candidates) if peak_candidates else None,
            "memory_measurement": "process_peak_rss" if peak_candidates else "unavailable",
        }
        report["compact_summary"] = compact_performance_summary(report)
        return report


def append_performance_stage(
    report: dict[str, Any] | None,
    *,
    stage: str,
    wall_seconds: float,
    cpu_seconds: float,
    counters: dict[str, Any] | None = None,
    total_wall_seconds: float | None = None,
) -> None:
    if not isinstance(report, dict):
        return
    cleaned = _clean_counts(counters or {})
    stages = report.setdefault("stages", [])
    stages.append(
        {
            "stage": str(stage),
            "wall_seconds": round(max(0.0, float(wall_seconds)), 6),
            "cpu_seconds": round(max(0.0, float(cpu_seconds)), 6),
            "counters": cleaned,
        }
    )
    totals = report.setdefault("totals", {})
    for key, value in cleaned.items():
        if key in _MAX_TOTAL_COUNTERS:
            totals[key] = max(int(totals.get(key) or 0), value)
        else:
            totals[key] = int(totals.get(key) or 0) + value
    report["total_cpu_seconds"] = round(
        max(0.0, float(report.get("total_cpu_seconds") or 0.0))
        + max(0.0, float(cpu_seconds)),
        6,
    )
    if total_wall_seconds is not None:
        report["total_wall_seconds"] = round(max(0.0, float(total_wall_seconds)), 6)
    report["compact_summary"] = compact_performance_summary(report)


def ingestion_performance_stages(
    performance: dict[str, Any] | None,
    *,
    rows: int,
    signals: int,
) -> list[dict[str, Any]]:
    values = performance if isinstance(performance, dict) else {}

    def stage(name: str, wall_keys: tuple[str, ...], cpu_key: str | None, **counts: int) -> dict[str, Any]:
        wall = sum(float(values.get(key) or 0.0) for key in wall_keys)
        cpu = float(values.get(cpu_key) or 0.0) if cpu_key else 0.0
        return {
            "stage": name,
            "wall_seconds": round(max(0.0, wall), 6),
            "cpu_seconds": round(max(0.0, cpu), 6),
            "counters": _clean_counts(counts),
        }

    canonical_total = float(values.get("canonical_normalization_seconds") or 0.0)
    canonical_persistence = float(values.get("canonical_persistence_seconds") or 0.0)
    canonical_cpu_total = float(values.get("canonical_cpu_seconds") or 0.0)
    canonical_persistence_cpu = float(values.get("canonical_persistence_cpu_seconds") or 0.0)
    canonical_build = {
        "stage": "canonical_dataset_build",
        "wall_seconds": round(max(0.0, canonical_total - canonical_persistence), 6),
        "cpu_seconds": round(max(0.0, canonical_cpu_total - canonical_persistence_cpu), 6),
        "counters": _clean_counts({"rows_processed": rows, "signals_processed": signals}),
    }
    return [
        stage("validation", ("raw_preservation_seconds", "parsing_seconds", "quality_profiling_seconds"), "validation_cpu_seconds", rows_processed=rows, signals_processed=signals),
        stage("schema_timestamp_processing", ("schema_and_timestamp_profiling_seconds",), "schema_timestamp_cpu_seconds", rows_processed=rows, signals_processed=signals),
        stage("semantic_mapping", ("mapping_seconds",), "mapping_cpu_seconds", signals_processed=signals),
        canonical_build,
        stage("canonical_persistence", ("canonical_persistence_seconds",), "canonical_persistence_cpu_seconds", rows_processed=rows),
    ]


def compact_performance_summary(report: dict[str, Any], *, stage_limit: int = 8) -> list[str]:
    stages = sorted(
        (item for item in report.get("stages", []) if isinstance(item, dict)),
        key=lambda item: float(item.get("wall_seconds") or 0.0),
        reverse=True,
    )[:stage_limit]
    lines = [
        f"{str(item.get('stage') or 'unknown').replace('_', ' ').title():<32} {float(item.get('wall_seconds') or 0.0):>8.3f}s"
        for item in stages
    ]
    totals = report.get("totals") if isinstance(report.get("totals"), dict) else {}
    for key, label in (
        ("rows_processed", "Rows"),
        ("signals_processed", "Signals"),
        ("relationship_pairs_considered", "Pairs considered"),
        ("relationship_pairs_deeply_analyzed", "Pairs deeply analyzed"),
        ("temporal_pairs", "Temporal pairs"),
        ("multiscale_pairs", "Multiscale pairs"),
        ("lags_evaluated", "Lags evaluated"),
        ("scales_evaluated", "Scales evaluated"),
        ("models_evaluated", "Models evaluated"),
        ("evidence_candidates_processed", "Evidence candidates"),
        ("cache_hits", "Cache hits / reuse"),
    ):
        if key in totals:
            lines.append(f"{label + ':':<32} {int(totals[key]):>8,}")
    lines.append(f"{'Total runtime:':<32} {float(report.get('total_wall_seconds') or 0.0):>8.3f}s")
    return lines
