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


def test_progressive_degradation_remains_detectable() -> None:
    result = process_csv_content(filename="progressive-drift-regression.csv", content=_csv_from_rows(_telemetry_rows(260, drift=True)))
    latest = _latest_runner_state(result)

    assert result["drift_status"] in {"review", "unstable"} or latest["instability_score"] >= 0.52
    assert latest["regime"] in {"UNSTABLE", "LOCK_IN"} or latest["instability_score"] >= 0.52
