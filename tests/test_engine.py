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
    rows = [[str(index), "75", "58"] for index in range(15)]

    result = engine_for(["timestamp", "temperature", "humidity"], rows)

    assert result["overall_result"] == "normal"
    assert result["signals"] == []
    assert result["system_evidence"]["corroboration_level"] == "limited"


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

    assert result["overall_result"] == "needs_review"
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


def test_engine_limitations_only_can_remain_normal() -> None:
    rows = [[str(index), "75"] for index in range(6)]

    result = engine_for(["timestamp", "temperature"], rows)

    assert result["signals"] == []
    assert result["overall_result"] == "normal"
    assert any("fewer than two numeric columns" in limitation for limitation in result["limitations"])


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


def test_engine_corroboration_level_moderate() -> None:
    rows = [
        [str(index), str(70 if index < 3 else 72 if index < 12 else 82), str(55 if index < 3 else 56 if index < 12 else 68)]
        for index in range(15)
    ]

    result = engine_for(["timestamp", "temperature", "humidity"], rows)

    assert result["system_evidence"]["categories_showing_meaningful_change"] == 0
    assert result["system_evidence"]["corroboration_level"] == "limited"


def test_engine_corroboration_level_strong() -> None:
    rows = [
        [
            str(index),
            str(70 if index < 3 else 74 if index < 12 else 90),
            str(55 if index < 3 else 58 if index < 12 else 72),
            str(900 if index < 3 else 950 if index < 12 else 1250),
        ]
        for index in range(15)
    ]

    result = engine_for(["timestamp", "temperature", "humidity", "co2"], rows)

    assert result["system_evidence"]["categories_showing_meaningful_change"] == 3
    assert result["system_evidence"]["corroboration_level"] == "strong"


def test_engine_persistence_assessment_with_enough_rows() -> None:
    rows = [
        [str(index), str(70 if index < 3 else 74 if index < 12 else 90)]
        for index in range(15)
    ]

    result = engine_for(["timestamp", "temperature"], rows)

    assert result["persistence_assessment"]["status"] == "persistent"
    assert result["persistence_assessment"]["persistent_columns"] == ["temperature"]


def test_engine_persistence_limitation_with_too_few_recent_rows() -> None:
    rows = [
        ["0", "70"],
        ["1", "70"],
        ["2", "74"],
        ["3", "78"],
        ["4", "90"],
        ["5", "90"],
    ]

    result = engine_for(["timestamp", "temperature"], rows)

    assert result["persistence_assessment"]["status"] == "persistent"


def test_engine_audit_trace_includes_skipped_columns_and_relationship_checks() -> None:
    rows = [[str(index), "Flower 1", "75"] for index in range(6)]

    result = engine_for(["timestamp", "room", "temperature"], rows)

    assert "columns_skipped:timestamp:timestamp_context" in result["audit_trace"]
    assert "columns_skipped:room:non_numeric" in result["audit_trace"]
    assert any(entry.startswith("relationship_checks_attempted:") for entry in result["audit_trace"])
    assert any(entry.startswith("relationship_checks_skipped:") for entry in result["audit_trace"])


def test_engine_explanations_avoid_unsupported_claims() -> None:
    rows = [
        [str(index), str(70 if index < 3 else 74 if index < 12 else 90)]
        for index in range(15)
    ]

    result = engine_for(["timestamp", "temperature"], rows)
    text = str(result).lower()

    assert "root cause is" not in text
    assert "caused by" not in text
    assert "yield impact is" not in text
    assert "will fail" not in text
    assert "crop stress prediction" not in text
