from __future__ import annotations

from app.engine.sii_engine import evaluate_sii


def _profiles(columns: list[str]) -> list[dict[str, object]]:
    return [{"column": column, "numeric_ratio": 1.0} for column in columns if column != "timestamp"]


def test_unified_sii_runs_temporal_math_for_sufficient_history() -> None:
    columns = ["timestamp", "pump_power", "flow", "pressure"]
    rows: list[list[object]] = []
    for index in range(80):
        load = float(index % 20)
        shift = 0.0 if index < 40 else float(index - 39) * 0.25
        rows.append(
            [
                f"2026-01-01T{index // 4:02d}:{(index % 4) * 15:02d}:00",
                20.0 + load + shift,
                100.0 + load * 2.0 - shift,
                45.0 + load * 0.5 + shift * 0.2,
            ]
        )

    sii_result = evaluate_sii(
        columns=columns,
        rows=rows,
        numeric_profiles=_profiles(columns),
        timestamp_column="timestamp",
    )
    result = sii_result["temporal_analysis"]

    assert result["engine"]["name"] == "temporal_math_engine"
    assert result.get("status") != "limited"
    assert result["baseline_rows"] >= 12
    assert result["active_rows"] >= 2
    assert result["columns_used"] == ["pump_power", "flow", "pressure"]
    assert 0.0 <= result["instability_index"]["score"] <= 1.0
    assert result["decision_thresholding"]["state"] in {
        "Normal",
        "Watch",
        "Investigate",
        "Act",
        "Critical",
    }


def test_unified_sii_preserves_limited_temporal_result() -> None:
    columns = ["timestamp", "flow"]
    rows = [[f"2026-01-01T00:{index:02d}:00", float(index)] for index in range(6)]

    sii_result = evaluate_sii(
        columns=columns,
        rows=rows,
        numeric_profiles=_profiles(columns),
        timestamp_column="timestamp",
    )
    result = sii_result["temporal_analysis"]

    assert result["engine"]["name"] == "temporal_math_engine"
    assert result["status"] == "limited"
    assert result["reason"] == "insufficient_numeric_history"
