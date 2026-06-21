import math
from datetime import datetime, timezone
from typing import Any

TIMESTAMP_COLUMN_HINTS = (
    "timestamp",
    "time_stamp",
    "time",
    "datetime",
    "date_time",
    "date",
    "logged_at",
    "recorded_at",
    "created_at",
)


def build_warnings(columns: list[str], rows: list[list[str]]) -> list[str]:
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


def detect_timestamp_column(columns: list[str], rows: list[list[str]] | None = None) -> str | None:
    normalized_columns = [(column, column.lower().replace(" ", "_")) for column in columns]
    for column, normalized in normalized_columns:
        if normalized in TIMESTAMP_COLUMN_HINTS or "timestamp" in normalized:
            return column
    if not rows:
        return None
    sample_rows = rows[: min(200, len(rows))]
    best_column: str | None = None
    best_ratio = 0.0
    for index, column in enumerate(columns):
        valid = 0
        observed = 0
        for row in sample_rows:
            raw_value = row[index].strip() if index < len(row) else ""
            if not raw_value:
                continue
            observed += 1
            if parse_timestamp(raw_value) is not None:
                valid += 1
        if observed < 3:
            continue
        ratio = valid / observed
        if ratio > best_ratio:
            best_ratio = ratio
            best_column = column
    if best_column is not None and best_ratio >= 0.6:
        return best_column
    return None


def profile_numeric_columns(columns: list[str], rows: list[list[str]]) -> list[dict[str, Any]]:
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
            value = parse_numeric_value(raw_value)
            if value is None:
                has_non_numeric = True
                continue
            if not math.isfinite(value):
                has_non_numeric = True
                continue
            values.append(value)

        numeric_ratio = (len(values) / max(1, row_count - missing_count)) if row_count else 0.0
        if not values or len(values) < 3 or numeric_ratio < 0.4:
            continue

        minimum = min(values)
        maximum = max(values)
        average = sum(values) / len(values)
        missing_percent = (missing_count / row_count * 100) if row_count else 0

        profiles.append(
            {
                "column": column,
                "min": round_number(minimum),
                "max": round_number(maximum),
                "average": round_number(average),
                "missing_count": missing_count,
                "missing_percent": round_number(missing_percent),
                "valid_numeric_count": len(values),
                "non_numeric_count": max(0, row_count - missing_count - len(values)),
                "constant_or_stuck": minimum == maximum,
                "variability": variability_flag(values, average),
                "range_warning": range_warning(column, minimum, maximum),
            }
        )

    return profiles


def profile_timestamps(
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
        timestamp = parse_timestamp(raw_value)
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
        profile["estimated_sample_interval"] = estimated_sample_interval(parsed)
        if len(parsed) < 2:
            profile["warnings"].append("At least two timestamps are required to estimate sample interval.")
        elif profile["estimated_sample_interval"] is None:
            profile["warnings"].append("Timestamp intervals are inconsistent.")

    return profile


def build_data_quality(
    row_count: int,
    column_count: int,
    numeric_column_count: int,
    timestamp_detected: bool,
    warnings: list[str],
    quality_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    quality_metrics = quality_metrics or {}
    rows_received = int(quality_metrics.get("rows_received") or row_count or 0)
    rows_dropped = int(quality_metrics.get("rows_dropped") or 0)
    drop_ratio = rows_dropped / max(1, rows_received)
    quality_counts = quality_metrics.get("quality_counts") or {}
    missing_rows = int(quality_counts.get("rows_with_missing_values") or 0)
    invalid_numeric_rows = int(quality_counts.get("rows_with_invalid_numeric") or 0)
    stuck_sensor_count = int(quality_metrics.get("stuck_sensor_count") or 0)
    irregular_sampling = bool(quality_metrics.get("irregular_sampling"))
    baseline_reliable = bool(quality_metrics.get("baseline_reliable", True))
    requested_gate_state = str(quality_metrics.get("analysis_gate_state") or "").upper()
    schema_detection = quality_metrics.get("schema_detection") if isinstance(quality_metrics.get("schema_detection"), dict) else {}
    quality_messages = [str(item) for item in quality_metrics.get("data_quality_messages", []) if str(item).strip()]
    imputation_report = quality_metrics.get("imputation_report") if isinstance(quality_metrics.get("imputation_report"), dict) else {}

    score = 100
    if not timestamp_detected:
        score -= 12
    if row_count < 12:
        score -= 30
    elif row_count < 50:
        score -= 12
    if drop_ratio > 0:
        score -= min(28, int(drop_ratio * 100))
    if missing_rows:
        score -= min(18, int((missing_rows / max(1, row_count)) * 80))
    if invalid_numeric_rows:
        score -= min(14, int((invalid_numeric_rows / max(1, row_count)) * 70))
    if irregular_sampling:
        score -= 8
    if stuck_sensor_count:
        score -= min(18, stuck_sensor_count * 6)
    if not baseline_reliable:
        score -= 16
    reliability_score = max(0, min(100, score))

    if reliability_score >= 82:
        reliability_rating = "strong"
    elif reliability_score >= 62:
        reliability_rating = "usable"
    elif reliability_score >= 40:
        reliability_rating = "weak"
    else:
        reliability_rating = "not_reliable"

    informational_warnings = {
        "At least 5 data rows are needed for baseline comparison.",
    }
    blocking_warnings = [warning for warning in warnings if warning not in informational_warnings]

    if requested_gate_state in {"READY", "DEGRADED_READY", "PENDING", "ERROR"}:
        analysis_gate_state = requested_gate_state
    elif row_count == 0 or column_count == 0 or numeric_column_count == 0:
        analysis_gate_state = "ERROR"
    elif not timestamp_detected or blocking_warnings:
        analysis_gate_state = "DEGRADED_READY"
    else:
        analysis_gate_state = "READY"

    if analysis_gate_state == "ERROR":
        readiness = "not_ready"
    elif analysis_gate_state == "PENDING":
        readiness = "pending"
    elif analysis_gate_state == "DEGRADED_READY":
        readiness = "ready"
    else:
        readiness = "ready"

    return {
        "row_count": row_count,
        "column_count": column_count,
        "numeric_column_count": numeric_column_count,
        "timestamp_detected": timestamp_detected,
        "warnings": warnings,
        "messages": quality_messages,
        "readiness": readiness,
        "analysis_gate_state": analysis_gate_state,
        "schema_detection": schema_detection,
        "imputation_report": imputation_report,
        "reliability_rating": reliability_rating,
        "reliability_score": reliability_score,
        "quality_metrics": {
            "rows_received": rows_received,
            "rows_used": row_count,
            "rows_dropped": rows_dropped,
            "drop_ratio": round_number(drop_ratio),
            "rows_with_missing_values": missing_rows,
            "rows_with_invalid_numeric": invalid_numeric_rows,
            "stuck_sensor_count": stuck_sensor_count,
            "irregular_sampling": irregular_sampling,
            "baseline_reliable": baseline_reliable,
        },
    }


def parse_timestamp(raw_value: str) -> datetime | None:
    normalized = raw_value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"

    for candidate in (normalized, normalized.replace("/", "-"), normalized.replace(" ", "T")):
        try:
            return normalize_timestamp(datetime.fromisoformat(candidate))
        except ValueError:
            continue

    for timestamp_format in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw_value, timestamp_format)
        except ValueError:
            continue

    return None


def parse_numeric_value(raw_value: str) -> float | None:
    normalized = raw_value.strip()
    if not normalized:
        return None
    normalized = normalized.replace(",", "").replace("%", "")
    lowered = normalized.lower()
    if lowered in {"nan", "null", "none", "n/a", "na", "-"}:
        return None
    pieces = normalized.split()
    candidate = pieces[0] if pieces else normalized
    try:
        value = float(candidate)
    except ValueError:
        filtered = "".join(char for char in candidate if char.isdigit() or char in {".", "-", "+"})
        if filtered in {"", "-", "+", ".", "-.", "+."}:
            return None
        try:
            value = float(filtered)
        except ValueError:
            return None
    if not math.isfinite(value):
        return None
    return value


def normalize_timestamp(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp
    return timestamp.astimezone(timezone.utc).replace(tzinfo=None)


def estimated_sample_interval(timestamps: list[datetime]) -> str | None:
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


def round_number(value: float | None, digits: int = 3) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def variability_flag(values: list[float], average: float) -> str:
    if not values:
        return "unknown"
    variance = sum((value - average) ** 2 for value in values) / len(values)
    spread = math.sqrt(variance)
    scale = max(abs(average), 1.0)
    ratio = spread / scale
    if ratio > 0.5:
        return "high"
    if ratio > 0.2:
        return "moderate"
    return "low"


def range_warning(column: str, minimum: float, maximum: float) -> str | None:
    lowered = column.lower()
    if "humidity" in lowered and (minimum < 0 or maximum > 100):
        return "Humidity values fall outside the expected 0-100 range."
    if "temp" in lowered and (minimum < -50 or maximum > 160):
        return "Temperature values fall outside a typical equipment telemetry range."
    if "co2" in lowered and maximum > 10000:
        return "CO2 values are unusually high."
    if "ph" in lowered and (minimum < 0 or maximum > 14):
        return "pH values fall outside the expected 0-14 range."
    return None
