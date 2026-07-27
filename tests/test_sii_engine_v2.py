from __future__ import annotations

import math

from app.engine.sii_engine import evaluate_sii


def _profiles(columns: list[str]) -> list[dict[str, object]]:
    return [
        {
            "column": column,
            "constant_or_stuck": False,
            "missing_count": 0,
            "non_numeric_count": 0,
        }
        for column in columns
        if column != "timestamp"
    ]


def _stable_rows(count: int = 120) -> tuple[list[str], list[dict[str, str]]]:
    columns = ["timestamp", "flow_rate", "supply_pressure", "pump_power"]
    rows = []
    for index in range(count):
        wave = math.sin(index / 8.0)
        rows.append(
            {
                "timestamp": f"2026-01-01T{index // 60:02d}:{index % 60:02d}:00Z",
                "flow_rate": f"{100.0 + wave * 2.0:.6f}",
                "supply_pressure": f"{40.0 + wave * 0.8:.6f}",
                "pump_power": f"{20.0 + wave * 0.4:.6f}",
            }
        )
    return columns, rows


def test_evaluate_sii_returns_canonical_phase_1_result_with_preserved_math() -> None:
    columns, rows = _stable_rows()
    result = evaluate_sii(
        columns=columns,
        rows=rows,
        numeric_profiles=_profiles(columns),
        timestamp_column="timestamp",
        config={"numeric_columns": columns[1:]},
    )

    assert result["engine"] == {"name": "neraium_sii", "version": "v2"}
    assert result["status"] == "complete"
    assert result["signal_drift"]["status"] == "complete"
    assert len(result["signal_drift"]["column_drift"]) == 3
    assert result["relationship_analysis"]["status"] == "complete"
    assert result["relationship_graph"]["edges"]
    assert result["covariance_analysis"]["status"] == "complete"
    covariance_metrics = result["covariance_analysis"]["metrics"]
    assert covariance_metrics["mahalanobis_distance"] >= 0.0
    assert 0.0 <= covariance_metrics["trajectory_curvature"] <= 1.0
    assert result["temporal_analysis"]["status"] == "complete"
    assert 0.0 <= result["temporal_analysis"]["instability_index"]["score"] <= 1.0
    assert result["persistence_analysis"]["fixed_row_support"]["status"] in {
        "not_persistent",
        "persistent",
    }
    assert result["multiscale_analysis"]["status"] == "complete"
    assert result["multiscale_analysis"]["scales_used"] == ["15_minutes", "1_hour"]
    assert result["physics_reasoning"]["active"] is True
    assert result["physics_reasoning"]["reason"] == "no_configured_engineering_priors"
    assert result["physics_evidence"] == result["physics_reasoning"]
    assert result["evidence_fusion"]["active"] is True
    assert result["evidence_fusion"]["observations"] == []
    assert result["behavioral_model"]["status"] == "limited"
    assert result["behavioral_model"]["active"] is False
    assert result["behavioral_model"]["identity"]["identity_status"] == "limited"
    assert result["findings"] == []

    trace = result["processing_trace"]
    assert trace["sii_engine_called"] is True
    assert trace["sii_engine_version"] == "v2"
    assert trace["modules_attempted"].count("temporal_analysis") == 1
    assert trace["modules_attempted"].count("covariance_analysis") == 1
    assert trace["modules_failed"] == []
    assert trace["rows_received"] == len(rows)
    assert trace["rows_used"] == len(rows)
    assert trace["columns_used"] == columns[1:]
    assert trace["total_runtime_seconds"] >= 0.0


def test_relationship_weakening_is_traceable_to_preserved_pearson_outputs() -> None:
    columns = ["timestamp", "flow_rate", "supply_pressure", "pump_power"]
    rows = []
    for index in range(120):
        flow = 80.0 + index * 0.25
        if index < 84:
            pressure = 10.0 + flow * 0.5
        else:
            pressure = 35.0 + ((index * 17) % 11)
        power = 15.0 + flow * 0.2
        timestamp = f"2026-01-02T{index // 60:02d}:{index % 60:02d}:00Z"
        rows.append(
            {
                "timestamp": timestamp,
                "flow_rate": f"{flow:.6f}",
                "supply_pressure": f"{pressure:.6f}",
                "pump_power": f"{power:.6f}",
                "__source_row_number": index + 2,
                "__source_timestamp": timestamp,
            }
        )

    result = evaluate_sii(
        columns=columns,
        rows=rows,
        numeric_profiles=_profiles(columns),
        timestamp_column="timestamp",
        config={"numeric_columns": columns[1:]},
    )

    changes = result["relationship_analysis"]["top_relationship_changes"]
    changed_pair = next(
        item
        for item in changes
        if set(item["relationship"].split(" <-> "))
        == {"flow_rate", "supply_pressure"}
    )
    assert changed_pair["baseline_correlation"] > 0.99
    assert abs(changed_pair["recent_correlation"]) < 0.5
    assert changed_pair["correlation_delta"] > 0.5
    assert changed_pair["change_type"] in {"weakened", "missing"}
    assert changed_pair["baseline_sample_size"] == 84
    assert changed_pair["recent_sample_size"] == 36
    assert changed_pair["source_rows"]


def test_single_temporary_spike_does_not_pass_covariance_persistence_gates() -> None:
    columns, rows = _stable_rows(80)
    rows[-1]["flow_rate"] = "240.0"
    rows[-1]["supply_pressure"] = "90.0"
    result = evaluate_sii(
        columns=columns,
        rows=rows,
        numeric_profiles=_profiles(columns),
        timestamp_column="timestamp",
        config={"numeric_columns": columns[1:]},
    )

    gates = result["persistence_analysis"]["covariance_gates"]
    assert not (gates["persistence_condition"] and gates["accumulation_condition"])
    assert result["compatibility"]["sii_runner_result"]["latest_state"]["urgency"] != "CRITICAL"
    assert result["findings"] == []


def test_sparse_history_returns_structured_limited_sections() -> None:
    columns = ["timestamp", "flow_rate"]
    rows = [
        {"timestamp": f"2026-01-01T00:0{index}:00Z", "flow_rate": str(10 + index)}
        for index in range(4)
    ]
    result = evaluate_sii(
        columns=columns,
        rows=rows,
        numeric_profiles=_profiles(columns),
        timestamp_column="timestamp",
        config={"numeric_columns": ["flow_rate"]},
    )

    assert result["status"] == "limited"
    assert result["signal_drift"]["status"] == "limited"
    assert result["relationship_analysis"]["status"] == "limited"
    assert result["relationship_graph"]["status"] == "limited"
    assert result["temporal_analysis"]["status"] == "limited"
    assert result["persistence_analysis"]["status"] in {"complete", "limited"}
    assert isinstance(result["uncertainty"]["limitations"], list)


def test_optional_temporal_failure_does_not_fail_other_analytics(monkeypatch) -> None:
    columns, rows = _stable_rows()

    def fail_temporal(**_kwargs):
        raise RuntimeError("synthetic optional failure")

    monkeypatch.setattr("app.engine.sii_engine.evaluate_temporal_math", fail_temporal)
    result = evaluate_sii(
        columns=columns,
        rows=rows,
        numeric_profiles=_profiles(columns),
        timestamp_column="timestamp",
        config={"numeric_columns": columns[1:]},
    )

    assert result["status"] == "limited"
    assert result["temporal_analysis"]["status"] == "failed"
    assert result["covariance_analysis"]["status"] == "complete"
    assert result["signal_drift"]["status"] == "complete"
    assert result["processing_trace"]["modules_failed"] == ["temporal_analysis"]
    assert result["uncertainty"]["module_failures"] == [
        {
            "module": "temporal_analysis",
            "reason": "RuntimeError: synthetic optional failure",
        }
    ]
