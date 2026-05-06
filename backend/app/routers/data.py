import csv
import io
import math
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

router = APIRouter(tags=["data"])

PREVIEW_ROW_LIMIT = 5
TIMESTAMP_COLUMN_HINTS = (
    "timestamp",
    "time",
    "datetime",
    "date",
    "recorded_at",
    "created_at",
)
BASELINE_WINDOW_FRACTION = 0.2
MIN_BASELINE_ROWS = 5


@router.post("/data/upload")
async def upload_csv(file: UploadFile = File(...)) -> dict[str, Any]:
    filename = file.filename or ""
    if Path(filename).suffix.lower() != ".csv":
        raise HTTPException(status_code=400, detail="Only .csv files are supported.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="CSV file is empty.")

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV file must be UTF-8 encoded.") from exc

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise HTTPException(status_code=400, detail="CSV file is empty.")

    columns = [column.strip() for column in rows[0]]
    if not any(columns):
        raise HTTPException(status_code=400, detail="CSV file must include a header row.")

    data_rows = [row for row in rows[1:] if any(cell.strip() for cell in row)]
    warnings = _build_warnings(columns, data_rows)
    detected_timestamp_column = _detect_timestamp_column(columns)

    if detected_timestamp_column is None:
        warnings.append("No obvious timestamp column detected.")

    numeric_profiles = _profile_numeric_columns(columns, data_rows)
    timestamp_profile = _profile_timestamps(columns, data_rows, detected_timestamp_column)
    warnings.extend(timestamp_profile["warnings"])
    warnings.extend(
        profile["range_warning"]
        for profile in numeric_profiles
        if profile["range_warning"] is not None
    )
    data_quality = _build_data_quality(
        row_count=len(data_rows),
        column_count=len(columns),
        numeric_column_count=len(numeric_profiles),
        timestamp_detected=detected_timestamp_column is not None,
        warnings=warnings,
    )
    baseline_analysis = _build_baseline_analysis(columns, data_rows, numeric_profiles)

    return {
        "filename": filename,
        "row_count": len(data_rows),
        "column_count": len(columns),
        "columns": columns,
        "preview_rows": _preview_rows(columns, data_rows),
        "detected_timestamp_column": detected_timestamp_column,
        "warnings": warnings,
        "numeric_profiles": numeric_profiles,
        "timestamp_profile": timestamp_profile,
        "data_quality": data_quality,
        "baseline_analysis": baseline_analysis,
    }


def _detect_timestamp_column(columns: list[str]) -> str | None:
    normalized_columns = [(column, column.lower().replace(" ", "_")) for column in columns]
    for column, normalized in normalized_columns:
        if normalized in TIMESTAMP_COLUMN_HINTS or "timestamp" in normalized:
            return column
    return None


def _preview_rows(columns: list[str], rows: list[list[str]]) -> list[dict[str, str]]:
    preview: list[dict[str, str]] = []
    for row in rows[:PREVIEW_ROW_LIMIT]:
        preview.append(
            {
                column: row[index].strip() if index < len(row) else ""
                for index, column in enumerate(columns)
            }
        )
    return preview


def _build_warnings(columns: list[str], rows: list[list[str]]) -> list[str]:
    warnings: list[str] = []
    if len(set(columns)) != len(columns):
        warnings.append("Duplicate column names detected.")
    if any(not column for column in columns):
        warnings.append("One or more columns are unnamed.")
    if not rows:
        warnings.append("CSV contains headers but no data rows.")
    if any(len(row) != len(columns) for row in rows):
        warnings.append("One or more rows have a different column count than the header.")
    return warnings


def _profile_numeric_columns(columns: list[str], rows: list[list[str]]) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    row_count = len(rows)

    for index, column in enumerate(columns):
        values: list[float] = []
        missing_count = 0
        has_non_numeric = False

        for row in rows:
            raw_value = row[index].strip() if index < len(row) else ""
            if raw_value == "":
                missing_count += 1
                continue
            try:
                value = float(raw_value)
            except ValueError:
                has_non_numeric = True
                break
            if not math.isfinite(value):
                has_non_numeric = True
                break
            values.append(value)

        if has_non_numeric or not values:
            continue

        minimum = min(values)
        maximum = max(values)
        average = sum(values) / len(values)
        missing_percent = (missing_count / row_count * 100) if row_count else 0

        profiles.append(
            {
                "column": column,
                "min": _round_number(minimum),
                "max": _round_number(maximum),
                "average": _round_number(average),
                "missing_count": missing_count,
                "missing_percent": _round_number(missing_percent),
                "variability": _variability_flag(values, average),
                "range_warning": _range_warning(column, minimum, maximum),
            }
        )

    return profiles


def _profile_timestamps(
    columns: list[str],
    rows: list[list[str]],
    detected_timestamp_column: str | None,
) -> dict[str, Any]:
    profile = {
        "detected_timestamp_column": detected_timestamp_column,
        "first_timestamp": None,
        "last_timestamp": None,
        "estimated_sample_interval": None,
        "warnings": [],
    }
    if detected_timestamp_column is None:
        return profile

    column_index = columns.index(detected_timestamp_column)
    parsed: list[datetime] = []
    missing_count = 0
    invalid_count = 0

    for row in rows:
        raw_value = row[column_index].strip() if column_index < len(row) else ""
        if raw_value == "":
            missing_count += 1
            continue
        timestamp = _parse_timestamp(raw_value)
        if timestamp is None:
            invalid_count += 1
            continue
        parsed.append(timestamp)

    if missing_count:
        profile["warnings"].append("Timestamp column contains missing values.")
    if invalid_count:
        profile["warnings"].append("Timestamp column contains values that could not be parsed.")
    if rows and not parsed:
        profile["warnings"].append("No usable timestamps found in the detected timestamp column.")
        return profile

    if parsed:
        profile["first_timestamp"] = min(parsed).isoformat()
        profile["last_timestamp"] = max(parsed).isoformat()
        profile["estimated_sample_interval"] = _estimated_sample_interval(parsed)
        if len(parsed) < 2:
            profile["warnings"].append("At least two timestamps are required to estimate sample interval.")
        elif profile["estimated_sample_interval"] is None:
            profile["warnings"].append("Timestamp intervals are inconsistent.")

    return profile


def _parse_timestamp(raw_value: str) -> datetime | None:
    normalized = raw_value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"

    for candidate in (normalized, normalized.replace("/", "-")):
        try:
            return _normalize_timestamp(datetime.fromisoformat(candidate))
        except ValueError:
            continue

    for timestamp_format in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw_value, timestamp_format)
        except ValueError:
            continue

    return None


def _normalize_timestamp(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp
    return timestamp.astimezone(timezone.utc).replace(tzinfo=None)


def _estimated_sample_interval(timestamps: list[datetime]) -> str | None:
    ordered = sorted(timestamps)
    intervals = [
        int((current - previous).total_seconds())
        for previous, current in zip(ordered, ordered[1:])
        if int((current - previous).total_seconds()) > 0
    ]
    if not intervals:
        return None

    first_interval = intervals[0]
    if any(interval != first_interval for interval in intervals):
        return None

    if first_interval % 3600 == 0:
        hours = first_interval // 3600
        return f"{hours} hour" if hours == 1 else f"{hours} hours"
    if first_interval % 60 == 0:
        minutes = first_interval // 60
        return f"{minutes} minute" if minutes == 1 else f"{minutes} minutes"
    return f"{first_interval} seconds"


def _variability_flag(values: list[float], average: float) -> str:
    if len(values) < 2 or min(values) == max(values):
        return "low"

    variance = sum((value - average) ** 2 for value in values) / len(values)
    standard_deviation = math.sqrt(variance)
    baseline = abs(average) if abs(average) > 0.000001 else max(abs(value) for value in values)
    coefficient = standard_deviation / baseline if baseline else 0

    if coefficient < 0.02:
        return "low"
    if coefficient > 0.25:
        return "high"
    return "normal"


def _range_warning(column: str, minimum: float, maximum: float) -> str | None:
    normalized = column.lower().replace("_", " ")
    if "humidity" in normalized and (minimum < 0 or maximum > 100):
        return f"{column} contains values outside the expected 0-100 humidity range."
    if "temperature" in normalized or normalized in {"temp", "room temp"}:
        if minimum < -40 or maximum > 140:
            return f"{column} contains values outside a broad cultivation temperature range."
    if "co2" in normalized or "carbon dioxide" in normalized:
        if minimum < 0 or maximum > 10000:
            return f"{column} contains values outside a broad CO2 sensor range."
    if minimum < 0 and any(keyword in normalized for keyword in ("vpd", "light", "ec", "ppm")):
        return f"{column} contains negative values for a measurement that is usually non-negative."
    return None


def _build_data_quality(
    row_count: int,
    column_count: int,
    numeric_column_count: int,
    timestamp_detected: bool,
    warnings: list[str],
) -> dict[str, Any]:
    if row_count == 0 or column_count == 0 or numeric_column_count == 0:
        readiness = "not_ready"
    elif not timestamp_detected or warnings:
        readiness = "needs_review"
    else:
        readiness = "ready"

    return {
        "row_count": row_count,
        "column_count": column_count,
        "numeric_column_count": numeric_column_count,
        "timestamp_detected": timestamp_detected,
        "warnings": warnings,
        "readiness": readiness,
    }


def _build_baseline_analysis(
    columns: list[str],
    rows: list[list[str]],
    numeric_profiles: list[dict[str, Any]],
) -> dict[str, Any]:
    warnings: list[str] = []
    if len(rows) < MIN_BASELINE_ROWS:
        return {
            "baseline_window_rows": 0,
            "recent_window_rows": 0,
            "columns_analyzed": 0,
            "column_drift": [],
            "overall_assessment": "needs_review",
            "warnings": ["At least 5 data rows are needed for baseline comparison."],
        }

    window_size = max(1, math.ceil(len(rows) * BASELINE_WINDOW_FRACTION))
    if window_size * 2 > len(rows):
        return {
            "baseline_window_rows": window_size,
            "recent_window_rows": window_size,
            "columns_analyzed": 0,
            "column_drift": [],
            "overall_assessment": "needs_review",
            "warnings": ["Not enough rows to compare separate baseline and recent windows."],
        }

    baseline_rows = rows[:window_size]
    recent_rows = rows[-window_size:]
    numeric_columns = {profile["column"] for profile in numeric_profiles}
    column_drift: list[dict[str, Any]] = []

    for index, column in enumerate(columns):
        if column not in numeric_columns:
            continue

        baseline_values, baseline_missing = _numeric_window_values(baseline_rows, index)
        recent_values, recent_missing = _numeric_window_values(recent_rows, index)
        column_warnings: list[str] = []

        if baseline_missing or recent_missing:
            column_warnings.append(f"{column} has missing values in baseline or recent windows.")
        if not baseline_values or not recent_values:
            column_warnings.append(f"{column} does not have enough numeric values for baseline comparison.")
            warnings.extend(column_warnings)
            continue

        baseline_average = sum(baseline_values) / len(baseline_values)
        recent_average = sum(recent_values) / len(recent_values)
        absolute_change = recent_average - baseline_average
        percent_change = _safe_percent_change(baseline_average, absolute_change)
        direction = _drift_direction(absolute_change, baseline_average)
        drift_flag = _drift_flag(percent_change, absolute_change, baseline_average)

        if _variability_flag(baseline_values, baseline_average) == "high":
            column_warnings.append(f"{column} baseline window is highly variable.")
        if _variability_flag(recent_values, recent_average) == "high":
            column_warnings.append(f"{column} recent window is highly variable.")
        if column_warnings:
            warnings.extend(column_warnings)

        column_drift.append(
            {
                "column": column,
                "baseline_average": _round_number(baseline_average),
                "recent_average": _round_number(recent_average),
                "absolute_change": _round_number(absolute_change),
                "percent_change": _round_number(percent_change) if percent_change is not None else None,
                "direction": direction,
                "drift_flag": drift_flag,
                "warnings": column_warnings,
            }
        )

    if not column_drift:
        warnings.append("No numeric columns were available for baseline comparison.")

    overall_assessment = (
        "needs_review"
        if warnings or any(item["drift_flag"] == "review" for item in column_drift)
        else "normal"
    )

    return {
        "baseline_window_rows": window_size,
        "recent_window_rows": window_size,
        "columns_analyzed": len(column_drift),
        "column_drift": column_drift,
        "overall_assessment": overall_assessment,
        "warnings": warnings,
    }


def _numeric_window_values(rows: list[list[str]], column_index: int) -> tuple[list[float], int]:
    values: list[float] = []
    missing_count = 0
    for row in rows:
        raw_value = row[column_index].strip() if column_index < len(row) else ""
        if raw_value == "":
            missing_count += 1
            continue
        try:
            value = float(raw_value)
        except ValueError:
            missing_count += 1
            continue
        if math.isfinite(value):
            values.append(value)
        else:
            missing_count += 1
    return values, missing_count


def _safe_percent_change(baseline_average: float, absolute_change: float) -> float | None:
    if abs(baseline_average) < 0.000001:
        return None
    return absolute_change / abs(baseline_average) * 100


def _drift_direction(absolute_change: float, baseline_average: float) -> str:
    threshold = max(abs(baseline_average) * 0.01, 0.01)
    if absolute_change > threshold:
        return "up"
    if absolute_change < -threshold:
        return "down"
    return "flat"


def _drift_flag(
    percent_change: float | None,
    absolute_change: float,
    baseline_average: float,
) -> str:
    if percent_change is None:
        return "watch" if abs(absolute_change) > 0.01 else "normal"

    magnitude = abs(percent_change)
    if magnitude >= 20:
        return "review"
    if magnitude >= 10:
        return "watch"
    if _drift_direction(absolute_change, baseline_average) == "flat":
        return "normal"
    return "normal"


def _round_number(value: float) -> float:
    return round(value, 4)
