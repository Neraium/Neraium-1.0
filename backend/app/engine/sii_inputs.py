from __future__ import annotations

from typing import Any

from app.services.data_quality import build_data_quality, profile_timestamps


def normalize_rows(
    columns: list[str],
    rows: list[dict[str, Any]] | list[list[Any]],
) -> tuple[list[dict[str, Any]], list[list[str]]]:
    if rows and isinstance(rows[0], dict):
        dict_rows = [dict(row) for row in rows if isinstance(row, dict)]
        matrix_rows = [[string_value(row.get(column)) for column in columns] for row in dict_rows]
        return dict_rows, matrix_rows

    matrix_rows = [
        [string_value(value) for value in row]
        for row in rows
        if isinstance(row, (list, tuple))
    ]
    dict_rows = [
        {
            column: row[index] if index < len(row) else ""
            for index, column in enumerate(columns)
        }
        for row in matrix_rows
    ]
    return dict_rows, matrix_rows


def string_value(value: Any) -> str:
    return "" if value is None else str(value)


def numeric_columns(
    *,
    columns: list[str],
    numeric_profiles: list[dict[str, Any]],
    configured_columns: Any = None,
) -> list[str]:
    requested = configured_columns if isinstance(configured_columns, list) else []
    candidates = requested or [
        str(profile.get("column"))
        for profile in numeric_profiles
        if isinstance(profile, dict) and profile.get("column")
    ]
    return list(dict.fromkeys(column for column in candidates if column in columns))


def build_data_conditions(
    *,
    columns: list[str],
    matrix_rows: list[list[str]],
    numeric_columns_used: list[str],
    numeric_profiles: list[dict[str, Any]],
    timestamp_column: str | None,
    baseline_analysis: dict[str, Any],
    provided_data_quality: dict[str, Any] | None,
    config: dict[str, Any],
    progress_callback: Any | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if progress_callback:
        progress_callback(0, 2)
    configured_timestamp_profile = config.get("timestamp_profile")
    timestamp_profile = (
        dict(configured_timestamp_profile)
        if isinstance(configured_timestamp_profile, dict)
        else profile_timestamps(columns, matrix_rows, timestamp_column)
    )
    if progress_callback:
        progress_callback(1, 2)
    if isinstance(provided_data_quality, dict):
        if progress_callback:
            progress_callback(2, 2)
        return dict(provided_data_quality), timestamp_profile

    ingestion_report = config.get("ingestion_report")
    ingestion_report = ingestion_report if isinstance(ingestion_report, dict) else {}
    normalization_report = config.get("normalization_report")
    normalization_report = normalization_report if isinstance(normalization_report, dict) else {}
    additional_warnings = config.get("additional_warnings")
    additional_warnings = additional_warnings if isinstance(additional_warnings, list) else []
    stuck_sensor_count = sum(
        1
        for profile in numeric_profiles
        if isinstance(profile, dict) and profile.get("constant_or_stuck")
    )
    baseline_reliable = (
        int(baseline_analysis.get("baseline_window_rows") or 0) >= 5
        and int(baseline_analysis.get("recent_window_rows") or 0) >= 1
        and int(baseline_analysis.get("columns_analyzed") or 0) >= 1
        and not normalization_report.get("window_suppressed")
    )
    row_count_total = int(config.get("row_count_total") or len(matrix_rows))
    reliability_warning = "Insufficient baseline: SII findings are not reliable enough to show."
    warnings = list(
        dict.fromkeys(
            [
                *[str(item) for item in additional_warnings if str(item).strip()],
                *[str(item) for item in timestamp_profile.get("warnings", []) if str(item).strip()],
                *[str(item) for item in baseline_analysis.get("warnings", []) if str(item).strip()],
                *[str(item) for item in normalization_report.get("warnings", []) if str(item).strip()],
                *(
                    [f"{stuck_sensor_count} numeric sensor(s) appear constant or stuck."]
                    if stuck_sensor_count
                    else []
                ),
                *([reliability_warning] if not baseline_reliable and row_count_total >= 5 else []),
            ]
        )
    )
    quality = build_data_quality(
        row_count_total,
        len(columns),
        len(numeric_columns_used),
        bool(timestamp_column),
        warnings,
        {
            "rows_received": ingestion_report.get("rows_received", row_count_total),
            "rows_dropped": ingestion_report.get("rows_dropped", 0),
            "quality_counts": ingestion_report.get("quality_counts", {}),
            "stuck_sensor_count": stuck_sensor_count,
            "irregular_sampling": any(
                "inconsistent" in str(warning).lower()
                for warning in timestamp_profile.get("warnings", [])
            ),
            "baseline_reliable": baseline_reliable,
            "schema_detection": ingestion_report.get("schema_detection", {}),
            "analysis_gate_state": ingestion_report.get("analysis_gate_state"),
            "data_quality_messages": ingestion_report.get("data_quality_messages", []),
            "imputation_report": ingestion_report.get("imputation_report", {}),
            "normalization_report": normalization_report,
        },
    )
    if progress_callback:
        progress_callback(2, 2)
    return quality, timestamp_profile
