from __future__ import annotations

from datetime import datetime
from typing import Any

from app.connectors.models import SUPPORTED_UNITS, NormalizedTelemetryRecord, ValidationIssue
from app.services.data_quality import parse_timestamp


def normalize_timestamp_value(raw_value: Any) -> str | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, datetime):
        return raw_value.isoformat()
    if not isinstance(raw_value, str):
        raw_value = str(raw_value)
    parsed = parse_timestamp(raw_value)
    if parsed is None:
        return None
    return parsed.isoformat()


def normalize_unit(raw_value: Any) -> str:
    if raw_value is None:
        return ""
    return str(raw_value).strip()


def validate_numeric_value(raw_value: Any) -> float | None:
    if raw_value is None or raw_value == "":
        return None
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return None


def validate_unit(unit: str) -> bool:
    return unit.lower() in SUPPORTED_UNITS


def deduplicate_records(records: list[NormalizedTelemetryRecord]) -> tuple[list[NormalizedTelemetryRecord], int]:
    seen: set[tuple[str, str, str, str]] = set()
    unique_records: list[NormalizedTelemetryRecord] = []
    duplicates_removed = 0
    for record in records:
        dedupe_key = (record.source_id, record.system_id, record.sensor_id, record.timestamp)
        if dedupe_key in seen:
            duplicates_removed += 1
            continue
        seen.add(dedupe_key)
        unique_records.append(record)
    return unique_records, duplicates_removed


def summarize_issues(issues: list[ValidationIssue]) -> list[str]:
    summaries: list[str] = []
    for issue in issues[:8]:
        row_prefix = f"Row {issue.row_number}: " if issue.row_number is not None else ""
        summaries.append(f"{row_prefix}{issue.message}")
    if len(issues) > 8:
        summaries.append(f"{len(issues) - 8} additional validation issues omitted.")
    return summaries
