import pytest

from app.services.baseline_analysis import build_baseline_analysis
from app.services.csv_parser import parse_csv_content, preview_rows
from app.services.data_quality import (
    build_data_quality,
    detect_timestamp_column,
    profile_numeric_columns,
    profile_timestamps,
)
from app.services.operator_report import build_operator_report


def test_csv_parser_returns_columns_rows_and_preview() -> None:
    columns, rows = parse_csv_content(
        b"timestamp,temperature\n2026-05-01T08:00:00Z,75\n"
    )

    assert columns == ["timestamp", "temperature"]
    assert rows == [["2026-05-01T08:00:00Z", "75"]]
    assert preview_rows(columns, rows) == [
        {"timestamp": "2026-05-01T08:00:00Z", "temperature": "75"}
    ]


def test_csv_parser_rejects_empty_content() -> None:
    with pytest.raises(ValueError, match="CSV file is empty."):
        parse_csv_content(b"")


def test_data_quality_profiles_numeric_and_timestamp_data() -> None:
    columns = ["recorded_at", "temperature", "humidity"]
    rows = [
        ["2026-05-01T08:00:00Z", "74", "55"],
        ["2026-05-01T08:05:00Z", "76", ""],
    ]

    timestamp_column = detect_timestamp_column(columns)
    numeric_profiles = profile_numeric_columns(columns, rows)
    timestamp_profile = profile_timestamps(columns, rows, timestamp_column)
    quality = build_data_quality(
        row_count=len(rows),
        column_count=len(columns),
        numeric_column_count=len(numeric_profiles),
        timestamp_detected=timestamp_column is not None,
        warnings=[],
    )

    assert timestamp_column == "recorded_at"
    assert timestamp_profile["estimated_sample_interval"] == "5 minutes"
    assert {profile["column"] for profile in numeric_profiles} == {"temperature", "humidity"}
    assert quality["readiness"] == "ready"


def test_baseline_analysis_compares_first_and_last_windows() -> None:
    columns = ["timestamp", "temperature"]
    rows = [
        ["2026-05-01T08:00:00Z", "70"],
        ["2026-05-01T08:05:00Z", "70"],
        ["2026-05-01T08:10:00Z", "74"],
        ["2026-05-01T08:15:00Z", "80"],
        ["2026-05-01T08:20:00Z", "90"],
        ["2026-05-01T08:25:00Z", "90"],
    ]
    numeric_profiles = [{"column": "temperature"}]

    analysis = build_baseline_analysis(columns, rows, numeric_profiles)

    assert analysis["baseline_window_rows"] == 2
    assert analysis["recent_window_rows"] == 2
    assert analysis["column_drift"][0]["direction"] == "up"
    assert analysis["column_drift"][0]["drift_flag"] == "review"


def test_operator_report_uses_existing_sections() -> None:
    data_quality = {
        "row_count": 6,
        "column_count": 2,
        "numeric_column_count": 1,
        "timestamp_detected": True,
        "warnings": [],
        "readiness": "ready",
    }
    timestamp_profile = {
        "detected_timestamp_column": "timestamp",
        "first_timestamp": "2026-05-01T08:00:00",
        "last_timestamp": "2026-05-01T08:25:00",
        "estimated_sample_interval": "5 minutes",
        "warnings": [],
    }
    numeric_profiles = [
        {
            "column": "temperature",
            "missing_count": 0,
            "missing_percent": 0,
            "variability": "low",
            "range_warning": None,
        }
    ]
    baseline_analysis = {
        "baseline_window_rows": 2,
        "recent_window_rows": 2,
        "columns_analyzed": 1,
        "column_drift": [
            {
                "column": "temperature",
                "direction": "flat",
                "drift_flag": "normal",
                "warnings": [],
            }
        ],
        "overall_assessment": "normal",
        "warnings": [],
    }

    report = build_operator_report(
        data_quality=data_quality,
        timestamp_profile=timestamp_profile,
        numeric_profiles=numeric_profiles,
        baseline_analysis=baseline_analysis,
    )

    assert report["data_readiness"] == "ready"
    assert report["source_sections_used"] == [
        "data_quality",
        "timestamp_profile",
        "numeric_profiles",
        "baseline_analysis",
    ]
    assert "usable for initial review" in report["summary"]
