from app.engine import run_engine_analysis
from app.services.baseline_analysis import build_baseline_analysis
from app.services.cultivation_mapping import map_cultivation_columns
from app.services.data_quality import build_data_quality, profile_numeric_columns


def engine_for(columns: list[str], rows: list[list[str]], warnings: list[str] | None = None) -> dict:
    warnings = warnings or []
    numeric_profiles = profile_numeric_columns(columns, rows)
    data_quality = build_data_quality(
        row_count=len(rows),
        column_count=len(columns),
        numeric_column_count=len(numeric_profiles),
        timestamp_detected=True,
        warnings=warnings,
    )
    baseline_analysis = build_baseline_analysis(columns, rows, numeric_profiles)
    return run_engine_analysis(
        columns=columns,
        rows=rows,
        data_quality=data_quality,
        baseline_analysis=baseline_analysis,
        cultivation_mapping=map_cultivation_columns(columns),
        numeric_profiles=numeric_profiles,
    )


def test_engine_no_drift_is_normal() -> None:
    rows = [[str(index), "75", "58"] for index in range(6)]

    result = engine_for(["timestamp", "temperature", "humidity"], rows)

    assert result["overall_result"] == "normal"
    assert result["signals"] == []


def test_engine_detects_upward_drift() -> None:
    rows = [
        ["0", "70"],
        ["1", "70"],
        ["2", "74"],
        ["3", "78"],
        ["4", "90"],
        ["5", "90"],
    ]

    result = engine_for(["timestamp", "temperature"], rows)

    assert result["overall_result"] == "elevated"
    assert any(signal["type"] == "baseline_drift" and signal["level"] == "elevated" for signal in result["signals"])


def test_engine_detects_downward_drift() -> None:
    rows = [
        ["0", "80"],
        ["1", "80"],
        ["2", "76"],
        ["3", "72"],
        ["4", "60"],
        ["5", "60"],
    ]

    result = engine_for(["timestamp", "humidity"], rows)

    assert result["overall_result"] == "elevated"
    assert any(signal["type"] == "baseline_drift" and "down" in signal["message"] for signal in result["signals"])


def test_engine_handles_insufficient_rows() -> None:
    rows = [["0", "70"], ["1", "71"], ["2", "72"], ["3", "73"]]

    result = engine_for(["timestamp", "temperature"], rows)

    assert result["overall_result"] == "needs_review"
    assert any("not enough rows" in limitation for limitation in result["limitations"])


def test_engine_handles_missing_numeric_values() -> None:
    rows = [
        ["0", "70"],
        ["1", ""],
        ["2", "70"],
        ["3", "70"],
        ["4", ""],
        ["5", "70"],
    ]

    result = engine_for(["timestamp", "temperature"], rows)

    assert result["overall_result"] == "needs_review"
    assert any("numeric columns contain missing values" in limitation for limitation in result["limitations"])


def test_engine_detects_relationship_coupling_change() -> None:
    rows = [
        ["0", "1", "1"],
        ["1", "2", "2"],
        ["2", "3", "2"],
        ["3", "4", "3"],
        ["4", "5", "5"],
        ["5", "6", "4"],
        ["6", "7", "3"],
        ["7", "8", "2"],
        ["8", "9", "2"],
        ["9", "10", "1"],
    ]

    result = engine_for(["timestamp", "temperature", "humidity"], rows)

    assert any(signal["type"] == "relationship_change" for signal in result["signals"])
    assert any(evidence["type"] == "relationship_change" for evidence in result["evidence"])


def test_engine_skips_relationships_when_not_enough_numeric_columns() -> None:
    rows = [[str(index), "75"] for index in range(6)]

    result = engine_for(["timestamp", "temperature"], rows)

    assert any("fewer than two numeric columns" in limitation for limitation in result["limitations"])
    assert "relationships.skipped:insufficient_numeric_columns" in result["audit_trace"]


def test_engine_audit_trace_present() -> None:
    rows = [[str(index), "75", "58"] for index in range(6)]

    result = engine_for(["timestamp", "temperature", "humidity"], rows)

    assert result["audit_trace"]
    assert result["audit_trace"][0] == "engine.version:neraium-cultivation-v1"
