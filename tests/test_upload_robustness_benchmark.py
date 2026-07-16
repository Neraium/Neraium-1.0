from __future__ import annotations

from datetime import datetime, timedelta, timezone
import ctypes
import importlib
import json
import os
import sys
from typing import Any

import pytest

try:
    resource_module: Any = importlib.import_module("resource")
except ImportError:  # Windows does not provide the Unix resource module.
    resource_module = None

from app.services.upload_jobs import process_csv_content


def _rows(count: int, *, drift: bool = False, missing: bool = False, relationship_collapse: bool = False, dropout: bool = False) -> bytes:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    lines = ["timestamp,temp,humidity,airflow,pressure"]
    for index in range(count):
        ts = (start + timedelta(minutes=index)).isoformat().replace("+00:00", "Z")
        progress = index / max(1, count - 1)
        drift_offset = progress * 8 if drift and index > int(count * 0.7) else 0
        temp = 72 + (index % 13) * 0.05 + drift_offset
        humidity = 50 + (index % 17) * 0.04 + (drift_offset * 1.2)
        if relationship_collapse:
            humidity = 0.72 * temp + 3.0
            if index > int(count * 0.7):
                humidity = 90.0 - 0.55 * temp
        airflow = 410 + (index % 19) * 0.3 - drift_offset * 4
        pressure = 1.4 + (index % 7) * 0.01 + drift_offset * 0.04
        if missing and index % 23 == 0:
            lines.append(f"{ts},,{humidity:.3f},{airflow:.3f},{pressure:.4f}")
        elif dropout and index > int(count * 0.75):
            lines.append(f"{ts},{temp:.3f},,,")
        else:
            lines.append(f"{ts},{temp:.3f},{humidity:.3f},{airflow:.3f},{pressure:.4f}")
    return "\n".join(lines).encode()


def _peak_memory_kb() -> int:
    if resource_module is not None:
        # Linux CI reports ru_maxrss in KiB. Keep that native path unchanged.
        return int(resource_module.getrusage(resource_module.RUSAGE_SELF).ru_maxrss)
    if sys.platform == "win32":
        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        process = ctypes.windll.kernel32.GetCurrentProcess()
        if ctypes.windll.psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
            return int(counters.PeakWorkingSetSize // 1024)
    return 0


def _run_case(name: str, content: bytes, *, expected_detected: bool, max_seconds: float) -> dict:
    before = _peak_memory_kb()
    result = process_csv_content(filename=f"{name}.csv", content=content)
    after = _peak_memory_kb()
    latest = result.get("sii_runner_result", {}).get("latest_state", {})
    relationship_changes = result.get("baseline_analysis", {}).get("top_relationship_changes") or []
    detected = (
        result["drift_status"] in {"review", "unstable"}
        or bool(relationship_changes)
        or float(latest.get("instability_score") or 0.0) >= 0.52
    )
    false_positive = detected and not expected_detected
    missed_detection = expected_detected and not detected
    return {
        "case": name,
        "false_positive": false_positive,
        "detected": detected,
        "missed_detection": missed_detection,
        "runtime_seconds": result["processing_time_seconds"],
        "memory_delta_kb": max(0, after - before),
        "rows_received": result["ingestion_report"]["rows_received"],
        "rows_used": result["ingestion_report"]["rows_used"],
        "rows_dropped": result["ingestion_report"]["rows_dropped"],
        "drop_reasons": result["ingestion_report"]["drop_reasons"],
        "reliability_rating": result["data_quality"]["reliability_rating"],
        "confidence": result["sii_intelligence"]["rooms"][0]["confidence"],
        "max_seconds": max_seconds,
    }


def test_robustness_benchmark_matrix(tmp_path) -> None:
    cases = [
        ("stable_clean", _rows(1200), False, 8.0),
        ("stable_noisy_missing", _rows(1200, missing=True), False, 8.0),
        ("injected_drift", _rows(1200, drift=True), True, 8.0),
        ("relationship_collapse", _rows(1200, relationship_collapse=True), True, 8.0),
        ("sensor_dropout", _rows(1200, dropout=True), False, 8.0),
        ("large_10k", _rows(10_000), False, 20.0),
    ]
    report = [_run_case(name, content, expected_detected=expected, max_seconds=max_seconds) for name, content, expected, max_seconds in cases]
    (tmp_path / "robustness_benchmark_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    assert not any(item["false_positive"] for item in report if item["case"].startswith("stable"))
    assert not any(item["missed_detection"] for item in report if item["case"] in {"injected_drift", "relationship_collapse"})
    assert all(item["runtime_seconds"] <= item["max_seconds"] for item in report)
    assert all(item["rows_received"] >= item["rows_used"] for item in report)


def test_100k_upload_performance_guard() -> None:
    report = _run_case("large_100k", _rows(100_000), expected_detected=False, max_seconds=60.0)
    assert report["runtime_seconds"] <= report["max_seconds"]
    assert report["rows_received"] == 100_000
    assert report["rows_used"] == 100_000
    assert report["rows_dropped"] == 0


@pytest.mark.skipif(os.getenv("NERAIUM_RUN_1M_BENCHMARK") != "1", reason="Set NERAIUM_RUN_1M_BENCHMARK=1 to run the 1M-row upload guard.")
def test_1m_upload_performance_guard() -> None:
    report = _run_case("large_1m", _rows(1_000_000), expected_detected=False, max_seconds=300.0)
    assert report["runtime_seconds"] <= report["max_seconds"]
    assert report["rows_received"] == 1_000_000
    assert report["rows_used"] == 1_000_000
