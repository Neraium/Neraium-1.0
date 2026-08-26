from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from app.engine.sii_engine import evaluate_sii as real_evaluate_sii
from app.services import upload_pipeline
from app.services.upload_jobs import process_csv_content


def _upload_csv(count: int = 90) -> bytes:
    start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    lines = ["timestamp,flow_rate,supply_pressure,pump_power"]
    for index in range(count):
        timestamp = (start + timedelta(minutes=index)).isoformat().replace("+00:00", "Z")
        wave = math.sin(index / 7.0)
        lines.append(
            f"{timestamp},{100 + wave:.6f},{40 + wave * 0.5:.6f},{20 + wave * 0.2:.6f}"
        )
    return ("\n".join(lines) + "\n").encode()


def _without_failure_prediction_aliases(value):
    if isinstance(value, dict):
        return {
            key: _without_failure_prediction_aliases(item)
            for key, item in value.items()
            if key not in {"projected_time_to_failure", "projected_time_to_failure_hours"}
        }
    if isinstance(value, list):
        return [_without_failure_prediction_aliases(item) for item in value]
    return value


def _has_failure_prediction_alias(value) -> bool:
    if isinstance(value, dict):
        return any(
            key in {"projected_time_to_failure", "projected_time_to_failure_hours"}
            or _has_failure_prediction_alias(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_has_failure_prediction_alias(item) for item in value)
    return False


def test_upload_pipeline_invokes_authoritative_sii_entrypoint_exactly_once(monkeypatch) -> None:
    calls = []

    def counted_evaluate_sii(**kwargs):
        calls.append({"rows": len(kwargs["rows"]), "columns": list(kwargs["columns"])})
        return real_evaluate_sii(**kwargs)

    monkeypatch.setattr(upload_pipeline, "evaluate_sii", counted_evaluate_sii)
    result = process_csv_content(
        filename="unified-sii-phase-1.csv",
        content=_upload_csv(),
    )

    assert calls == [
        {
            "rows": 90,
            "columns": ["timestamp", "flow_rate", "supply_pressure", "pump_power"],
        }
    ]
    canonical = result["sii_result"]
    assert canonical["engine"] == {"name": "neraium_sii", "version": "v2"}
    assert canonical["processing_trace"]["sii_engine_called"] is True
    assert canonical["processing_trace"]["modules_attempted"].count("temporal_analysis") == 1
    assert canonical["processing_trace"]["modules_attempted"].count("covariance_analysis") == 1
    assert result["baseline_analysis"] == canonical["compatibility"]["baseline_analysis"]
    assert result["relationship_model"] == canonical["compatibility"]["relationship_model"]
    canonical_runner = canonical["compatibility"]["sii_runner_result"]
    assert _has_failure_prediction_alias(canonical_runner)
    assert not _has_failure_prediction_alias(result["sii_runner_result"])
    assert result["sii_runner_result"] == _without_failure_prediction_aliases(canonical_runner)
    assert result["processing_trace"]["sii_engine_version"] == "v2"
    assert result["processing_trace"]["rows_received"] == 90
