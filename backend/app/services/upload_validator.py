from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Callable

from app.services.data_quality import detect_timestamp_column, parse_numeric_value, parse_timestamp


CHILLED_WATER_EXPECTED_COLUMNS = {
    "timestamp",
    "chw_supply_temp_f",
    "chw_return_temp_f",
    "delta_t_f",
    "flow_gpm",
    "pump_speed_pct",
    "pump_power_kw",
    "differential_pressure_psi",
    "chiller_load_pct",
    "compressor_power_kw",
    "condenser_water_temp_f",
    "evaporator_temp_f",
    "building_cooling_demand_pct",
    "ambient_temp_f",
    "energy_consumption_kwh",
    "alarm_count",
    "maintenance_event",
    "operator_override",
}
CHILLED_WATER_IMPORTANT_COLUMNS = (
    "chw_supply_temp_f",
    "chw_return_temp_f",
    "flow_gpm",
    "pump_power_kw",
    "chiller_load_pct",
    "compressor_power_kw",
)
CHILLED_WATER_FLAG_COLUMNS = {"alarm_count", "maintenance_event", "operator_override"}
CHILLED_WATER_SPARSE_MISSING_THRESHOLD = 0.05
SHORT_GAP_LIMIT_ROWS = 6
LOW_MISSING_WARNING_THRESHOLD = 0.10

DOMAIN_ADAPTERS = (
    (
        "chilled_water",
        "chilled-water telemetry",
        ("chw_", "chilled", "chiller", "evaporator", "condenser", "delta_t", "cooling_demand"),
    ),
    (
        "hvac",
        "HVAC telemetry",
        ("supply_temp", "return_temp", "static_pressure", "airflow", "ahu", "rtu", "compressor", "economizer"),
    ),
    (
        "pumps",
        "pump telemetry",
        ("pump", "flow", "gpm", "discharge_pressure", "suction_pressure", "bearing", "vibration", "vfd"),
    ),
    (
        "pool_spa_chemistry",
        "pool/spa chemistry telemetry",
        ("pool", "spa", "orp", "chlorine", "ph", "turbidity", "sanitizer", "alkalinity"),
    ),
    (
        "energy_meters",
        "energy meter telemetry",
        ("kwh", "kw", "voltage", "current", "power_factor", "meter", "demand"),
    ),
    (
        "generic_equipment",
        "equipment telemetry",
        ("asset", "equipment", "machine", "motor", "temperature", "pressure", "speed", "runtime"),
    ),
)


def detect_delimiter(sample: str) -> str:
    non_blank = [line for line in sample.splitlines() if line.strip()][:20]
    joined = "\n".join(non_blank)
    if not joined:
        raise ValueError("CSV file is empty.")
    try:
        return csv.Sniffer().sniff(joined, delimiters=",\t;|").delimiter
    except csv.Error:
        return "whitespace"


def row_tokens(line: str, delimiter: str) -> list[str]:
    if delimiter == "whitespace":
        return line.strip().split()
    return next(csv.reader([line], delimiter=delimiter))


def looks_like_header(tokens: list[str]) -> bool:
    if not tokens:
        return False
    numeric_count = sum(parse_numeric_value(token) is not None for token in tokens)
    timestamp_count = sum(parse_timestamp(token) is not None for token in tokens)
    return numeric_count + timestamp_count < max(1, len(tokens) // 2)


def normalized_columns(tokens: list[str], *, header_present: bool) -> list[str]:
    if not header_present:
        return [f"column_{index + 1}" for index in range(len(tokens))]
    columns: list[str] = []
    seen: dict[str, int] = {}
    for index, token in enumerate(tokens):
        base = token.strip() or f"column_{index + 1}"
        seen[base] = seen.get(base, 0) + 1
        columns.append(base if seen[base] == 1 else f"{base}_{seen[base]}")
    return columns


def normalize_schema_column(column: str) -> str:
    normalized = column.strip().lower().replace(" ", "_").replace("-", "_")
    return "".join(char for char in normalized if char.isalnum() or char == "_")


def is_status_or_flag_column(column: str) -> bool:
    normalized = normalize_schema_column(column)
    return any(
        token in normalized
        for token in (
            "alarm",
            "alert",
            "fault",
            "status",
            "state",
            "mode",
            "override",
            "operator",
            "maintenance",
            "event",
            "flag",
            "enabled",
            "command",
        )
    )


def detect_domain_adapter(columns: list[str]) -> dict[str, Any]:
    normalized_columns = [normalize_schema_column(column) for column in columns]
    best: tuple[str, str, list[str]] | None = None
    best_matches: list[str] = []
    for adapter_id, label, tokens in DOMAIN_ADAPTERS:
        matches = [
            column
            for column, normalized in zip(columns, normalized_columns)
            if any(token in normalized for token in tokens)
        ]
        if len(matches) > len(best_matches):
            best = (adapter_id, label, list(tokens))
            best_matches = matches
    if best is None or len(best_matches) < 2:
        return {
            "detected": True,
            "system_type": "generic_equipment",
            "label": "generic equipment telemetry",
            "matched_columns": [],
            "confidence": "low",
        }
    return {
        "detected": True,
        "system_type": best[0],
        "label": best[1],
        "matched_columns": best_matches[:12],
        "confidence": "high" if len(best_matches) >= 4 else "medium",
    }


def profile_csv_columns(
    columns: list[str],
    rows: list[list[str]],
    *,
    timestamp_index: int | None,
    identity_index: int | None,
) -> dict[str, Any]:
    excluded_indexes = {index for index in (timestamp_index, identity_index) if index is not None}
    row_count = len(rows)
    empty_columns: list[str] = []
    numeric_indexes: list[int] = []
    categorical_indexes: list[int] = []
    status_indexes: list[int] = []
    unknown_columns: list[str] = []

    for index, column in enumerate(columns):
        values = [row[index].strip() if index < len(row) else "" for row in rows]
        non_empty = [value for value in values if value != ""]
        if not non_empty:
            empty_columns.append(column)
            continue
        if index in excluded_indexes:
            continue

        numeric_count = sum(parse_numeric_value(value) is not None for value in non_empty)
        numeric_ratio = numeric_count / max(1, len(non_empty))
        distinct_count = len({value.lower() for value in non_empty})
        status_like = is_status_or_flag_column(column)

        if status_like:
            status_indexes.append(index)
            categorical_indexes.append(index)
        elif numeric_count >= max(3, int(row_count * 0.15)) and numeric_ratio >= 0.4:
            numeric_indexes.append(index)
        elif distinct_count <= max(20, int(max(1, row_count) * 0.2)):
            categorical_indexes.append(index)
        else:
            unknown_columns.append(column)

    return {
        "empty_columns": empty_columns,
        "numeric_indexes": numeric_indexes,
        "numeric_columns": [columns[index] for index in numeric_indexes],
        "categorical_columns": [columns[index] for index in categorical_indexes],
        "status_columns": [columns[index] for index in status_indexes],
        "unknown_extra_columns": unknown_columns,
    }


def detect_chilled_water_schema(columns: list[str]) -> dict[str, Any]:
    normalized_to_column = {normalize_schema_column(column): column for column in columns}
    matched = sorted(set(normalized_to_column) & CHILLED_WATER_EXPECTED_COLUMNS)
    detected = len(matched) >= 6 and (
        "timestamp" in matched
        or "chw_supply_temp_f" in matched
        or "chw_return_temp_f" in matched
        or "chiller_load_pct" in matched
    )
    important_present = [name for name in CHILLED_WATER_IMPORTANT_COLUMNS if name in normalized_to_column]
    missing_core: list[str] = []
    if "chw_supply_temp_f" not in normalized_to_column and "chw_return_temp_f" not in normalized_to_column:
        missing_core.append("supply and return temperature")
    if "timestamp" not in normalized_to_column:
        missing_core.append("timestamp")
    return {
        "detected": detected,
        "system_type": "chilled_water" if detected else None,
        "matched_columns": matched,
        "important_columns": important_present,
        "missing_core": missing_core if detected else [],
        "column_lookup": normalized_to_column,
    }


def display_chilled_water_column(name: str) -> str:
    labels = {
        "chw_supply_temp_f": "supply temp",
        "chw_return_temp_f": "return temp",
        "flow_gpm": "flow",
        "pump_power_kw": "pump power",
        "chiller_load_pct": "chiller load",
        "compressor_power_kw": "compressor power",
    }
    return labels.get(name, name.replace("_", " "))


def format_interval(seconds: int | None) -> str | None:
    if not seconds or seconds <= 0:
        return None
    if seconds % 3600 == 0:
        hours = seconds // 3600
        return f"{hours}-hour"
    if seconds % 60 == 0:
        minutes = seconds // 60
        return f"{minutes}-minute"
    return f"{seconds}-second"


def detect_interval_seconds(rows: list[tuple[Any, dict[str, Any]]]) -> int | None:
    timestamps = [item[0] for item in rows]
    intervals = [
        int((current - previous).total_seconds())
        for previous, current in zip(timestamps, timestamps[1:])
        if previous is not None and current is not None and int((current - previous).total_seconds()) > 0
    ]
    if not intervals:
        return None
    counts: dict[int, int] = {}
    for interval in intervals:
        counts[interval] = counts.get(interval, 0) + 1
    interval, count = max(counts.items(), key=lambda item: item[1])
    return interval if count / max(1, len(intervals)) >= 0.9 else None


def interpolate_short_numeric_gaps(
    rows: list[tuple[Any, dict[str, Any]]],
    columns_to_interpolate: list[str],
    missing_by_column: dict[str, int],
    total_rows: int,
) -> dict[str, Any]:
    imputed_columns: list[str] = []
    imputed_cells = 0
    for column in columns_to_interpolate:
        missing_ratio = missing_by_column.get(column, 0) / max(1, total_rows)
        if missing_ratio <= 0 or missing_ratio >= LOW_MISSING_WARNING_THRESHOLD:
            continue
        index = 0
        while index < len(rows):
            value = parse_numeric_value(str(rows[index][1].get(column, "")))
            if value is not None:
                index += 1
                continue
            gap_start = index
            while index < len(rows) and parse_numeric_value(str(rows[index][1].get(column, ""))) is None:
                index += 1
            gap_end = index - 1
            gap_size = gap_end - gap_start + 1
            if gap_size > SHORT_GAP_LIMIT_ROWS or gap_start == 0 or index >= len(rows):
                continue
            previous_value = parse_numeric_value(str(rows[gap_start - 1][1].get(column, "")))
            next_value = parse_numeric_value(str(rows[index][1].get(column, "")))
            if previous_value is None or next_value is None:
                continue
            for offset, row_index in enumerate(range(gap_start, gap_end + 1), start=1):
                fraction = offset / (gap_size + 1)
                rows[row_index][1][column] = str(round(previous_value + (next_value - previous_value) * fraction, 6))
                imputed_cells += 1
            imputed_columns.append(column)
    return {
        "imputed_cells": imputed_cells,
        "imputed_columns": sorted(set(imputed_columns)),
    }


def stream_csv_snapshot(
    path: Path,
    *,
    max_analysis_rows: int,
    csv_progress_update_every: int,
    csv_chunk_size_rows: int,
    job_id: str | None = None,
    on_progress: Callable[[str, str, int, str], None] | None = None,
) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        sample_lines: list[str] = []
        while len(sample_lines) < 20 and sum(len(item) for item in sample_lines) < 65536:
            line = handle.readline()
            if line == "":
                break
            if line.strip():
                sample_lines.append(line.rstrip("\r\n"))

        if not sample_lines:
            raise ValueError("CSV file is empty.")

        delimiter = detect_delimiter("\n".join(sample_lines))
        first_tokens = row_tokens(sample_lines[0], delimiter)
        header_present = looks_like_header(first_tokens)
        columns = normalized_columns(first_tokens, header_present=header_present)
        if not columns:
            raise ValueError("CSV must include at least one column.")

        timestamp_column = detect_timestamp_column(columns) if header_present else None
        timestamp_index = columns.index(timestamp_column) if timestamp_column in columns else None
        chilled_water_schema = detect_chilled_water_schema(columns)

        handle.seek(0)
        saw_header = not header_present
        detection_rows: list[list[str]] = []
        while True:
            line = handle.readline()
            if line == "":
                break
            if not line.strip():
                continue
            if header_present and not saw_header:
                saw_header = True
                continue
            tokens = row_tokens(line.rstrip("\r\n"), delimiter)
            if len(tokens) != len(columns):
                continue
            row_values = [token.strip() for token in tokens]
            if len(detection_rows) < 1000:
                detection_rows.append(row_values)

        if not detection_rows:
            raise ValueError("CSV must include a header and at least one usable data row.")

        if timestamp_index is None:
            detected = detect_timestamp_column(columns, detection_rows)
            if detected in columns:
                timestamp_column = detected
                timestamp_index = columns.index(detected)

        identity_index = next(
            (
                index
                for index, column in enumerate(columns)
                if column.lower().strip() in {"room", "zone", "location", "area", "group", "system", "asset", "asset name", "zone name"}
            ),
            None,
        )
        generic_profile = profile_csv_columns(
            columns,
            detection_rows,
            timestamp_index=timestamp_index,
            identity_index=identity_index,
        )
        numeric_indexes = list(generic_profile["numeric_indexes"])
        status_columns = set(generic_profile["status_columns"])
        domain_adapter = detect_domain_adapter(columns)
        chilled_water_schema = {
            **chilled_water_schema,
            **domain_adapter,
            "chilled_water_adapter": chilled_water_schema,
            "generic_profile": {key: value for key, value in generic_profile.items() if key != "numeric_indexes"},
        }

        handle.seek(0)
        rows_received = 0
        blank_rows = 0
        malformed_rows = 0
        duplicate_timestamps = 0
        invalid_timestamps = 0
        no_numeric_values = 0
        rows_with_missing_values = 0
        rows_with_invalid_numeric = 0
        duplicate_exact_rows = 0
        missing_by_column: dict[str, int] = {}
        invalid_by_column: dict[str, int] = {}
        invalid_numeric_cells = 0
        seen_timestamps: set[str] = set()
        seen_exact_rows: set[tuple[str, ...]] = set()
        raw_rows_in_order: list[tuple[Any, dict[str, Any]]] = []
        header_skipped = not header_present

        for line in handle:
            if not line.strip():
                if header_skipped:
                    rows_received += 1
                    blank_rows += 1
                continue

            if not header_skipped:
                header_skipped = True
                continue

            rows_received += 1
            tokens = row_tokens(line.rstrip("\r\n"), delimiter)
            if len(tokens) != len(columns):
                malformed_rows += 1
                continue

            raw_row = [token.strip() for token in tokens]
            exact_row_key = tuple(raw_row)
            if exact_row_key in seen_exact_rows:
                duplicate_exact_rows += 1
                continue
            seen_exact_rows.add(exact_row_key)
            parsed_ts = None
            if timestamp_index is not None:
                parsed_ts = parse_timestamp(raw_row[timestamp_index])
                if parsed_ts is None:
                    invalid_timestamps += 1
                    continue
                identity_value = raw_row[identity_index].strip() if identity_index is not None else ""
                timestamp_key = f"{identity_value}::{parsed_ts.isoformat()}"
                if timestamp_key in seen_timestamps:
                    duplicate_timestamps += 1
                    continue
                seen_timestamps.add(timestamp_key)

            row = {column: raw_row[index] for index, column in enumerate(columns)}
            row["__source_row_number"] = rows_received
            if parsed_ts is not None:
                row["__source_timestamp"] = parsed_ts.isoformat()
            missing_in_row = any(raw_row[index] == "" for index in numeric_indexes)
            invalid_in_row = False
            usable_numeric = 0
            for index in numeric_indexes:
                raw_value = raw_row[index]
                numeric_value = parse_numeric_value(raw_value)
                column_name = columns[index]
                if raw_value == "":
                    missing_by_column[column_name] = missing_by_column.get(column_name, 0) + 1
                    continue
                if numeric_value is None:
                    row[column_name] = ""
                    invalid_by_column[column_name] = invalid_by_column.get(column_name, 0) + 1
                    invalid_numeric_cells += 1
                    invalid_in_row = True
                    continue
                row[columns[index]] = str(numeric_value)
                usable_numeric += 1
            if numeric_indexes and usable_numeric == 0:
                no_numeric_values += 1
                continue
            if missing_in_row:
                rows_with_missing_values += 1
            if invalid_in_row:
                rows_with_invalid_numeric += 1
            raw_rows_in_order.append((parsed_ts, row))

        if not raw_rows_in_order:
            raise ValueError("CSV contains no usable telemetry rows after cleaning.")

        rows_used = len(raw_rows_in_order)
        cleaned = sorted(raw_rows_in_order, key=lambda item: item[0]) if timestamp_index is not None else raw_rows_in_order
        interval_seconds = detect_interval_seconds(cleaned) if timestamp_index is not None else None
        imputation_report = {"imputed_cells": 0, "imputed_columns": []}
        columns_to_interpolate = [column for column in generic_profile["numeric_columns"] if column not in status_columns]
        if rows_used >= 3:
            imputation_report = interpolate_short_numeric_gaps(
                cleaned,
                columns_to_interpolate,
                missing_by_column,
                rows_used,
            )
        sample_rows = [row for _, row in cleaned[:max_analysis_rows]]
        first_timestamp = cleaned[0][1].get(timestamp_column) if timestamp_column else None
        last_timestamp = cleaned[-1][1].get(timestamp_column) if timestamp_column else None
        memory_estimate_bytes = sum(sum(len(str(value or "")) for value in row.values()) for row in sample_rows)
        rows_dropped = rows_received - rows_used
        drop_reasons = {
            key: value
            for key, value in {
                "blank_row": blank_rows,
                "column_count_mismatch": malformed_rows,
                "invalid_timestamp": invalid_timestamps,
                "duplicate_timestamp": duplicate_timestamps,
                "exact_duplicate_row": duplicate_exact_rows,
                "no_usable_numeric_values": no_numeric_values,
            }.items()
            if value
        }
        warnings = []
        if rows_dropped:
            warnings.append(f"{rows_dropped} rows were dropped during safe cleaning.")
        if rows_with_missing_values:
            warnings.append(f"{rows_with_missing_values} rows contain missing numeric values.")
        if rows_with_invalid_numeric:
            warnings.append(f"{rows_with_invalid_numeric} rows contained non-numeric values that were ignored.")
        if delimiter == "whitespace":
            warnings.append("Whitespace-delimited telemetry was detected.")
        if not header_present:
            warnings.append("No header row was detected; generic column names were assigned.")
        timestamps_were_unsorted = timestamp_index is not None and [item[0] for item in raw_rows_in_order] != [item[0] for item in cleaned]
        if timestamps_were_unsorted:
            warnings.append("Timestamps were unsorted and were ordered before analysis.")
        sparse_missing_columns = [
            column
            for column in generic_profile["numeric_columns"]
            if 0 < missing_by_column.get(column, 0) / max(1, rows_used) < LOW_MISSING_WARNING_THRESHOLD
        ]
        high_missing_columns = [
            column
            for column in generic_profile["numeric_columns"]
            if missing_by_column.get(column, 0) / max(1, rows_used) >= LOW_MISSING_WARNING_THRESHOLD
        ]
        bad_columns = [
            {
                "column": column,
                "missing_count": missing_by_column.get(column, 0),
                "invalid_count": invalid_by_column.get(column, 0),
            }
            for column in generic_profile["numeric_columns"]
            if (missing_by_column.get(column, 0) + invalid_by_column.get(column, 0)) / max(1, rows_used) >= 0.4
        ]

        schema_messages: list[str] = [
            "CSV loaded successfully.",
            "Detected telemetry-style dataset.",
            f"Rows loaded: {rows_used:,}.",
            f"{rows_used:,} rows loaded.",
        ]
        adapter_label = str(chilled_water_schema.get("label") or "generic equipment telemetry")
        if adapter_label == "chilled-water telemetry":
            schema_messages.append("Detected chilled-water telemetry.")
        else:
            schema_messages.append(f"Detected {adapter_label}.")
        if timestamp_column:
            schema_messages.append(f"Timestamp column detected: {timestamp_column}.")
        else:
            schema_messages.append("No timestamp column detected; using row-index analysis.")
        interval_label = format_interval(interval_seconds)
        if interval_label:
            schema_messages.append(f"Likely interval detected: {interval_label.replace('-', ' ')}s.")
            schema_messages.append(f"{interval_label} interval detected.")
        schema_messages.append(f"Numeric telemetry columns detected: {len(generic_profile['numeric_columns'])}.")
        if generic_profile["status_columns"]:
            schema_messages.append("Status/flag columns detected and excluded from numeric interpolation.")
        non_signal_columns = [
            column
            for column in columns
            if column != timestamp_column
            and column not in generic_profile["numeric_columns"]
            and column not in generic_profile["status_columns"]
        ]
        if generic_profile["unknown_extra_columns"] or non_signal_columns:
            schema_messages.append("Unknown extra columns ignored unless they break parsing.")
        if imputation_report.get("imputed_cells"):
            schema_messages.append("Sparse missing values detected; short numeric gaps interpolated.")

        analysis_gate_state = "READY"
        if rows_used == 0 or len(columns) == 0:
            analysis_gate_state = "ERROR"
        elif len(generic_profile["numeric_columns"]) < 2 or rows_used < 5:
            analysis_gate_state = "PENDING"
        elif timestamp_index is None:
            analysis_gate_state = "DEGRADED_READY" if rows_used >= 12 else "PENDING"
        elif bad_columns or high_missing_columns or sparse_missing_columns or rows_dropped or rows_with_invalid_numeric or rows_with_missing_values or timestamps_were_unsorted:
            analysis_gate_state = "DEGRADED_READY"

        if sparse_missing_columns:
            sparse_labels = ", ".join(
                display_chilled_water_column(normalize_schema_column(column))
                for column in sparse_missing_columns[:8]
            )
            detail = f"Sparse missing values detected in {sparse_labels}; short gaps interpolated."
            schema_messages.append(detail)
            warnings.append(detail)
        if high_missing_columns:
            warnings.append(f"High missing values detected in {', '.join(high_missing_columns[:8])}; affected columns were degraded individually.")
        if bad_columns:
            warnings.append("One or more telemetry columns have poor coverage and were flagged individually.")
        if analysis_gate_state == "DEGRADED_READY":
            schema_messages.append("Analysis can proceed with confidence warnings.")
        elif analysis_gate_state == "READY":
            schema_messages.append("Analysis can proceed.")
        elif analysis_gate_state == "PENDING":
            if len(generic_profile["numeric_columns"]) < 2:
                schema_messages.append("Analysis is pending because at least two usable numeric telemetry columns are required.")
            elif rows_used < 5:
                schema_messages.append("Analysis is pending because at least five usable telemetry rows are required.")
            else:
                schema_messages.append("Analysis is pending because usable signal is insufficient.")

        if job_id and rows_received >= csv_progress_update_every and on_progress is not None:
            on_progress(job_id, "parsing_telemetry", 20, f"Parsed and cleaned {rows_received:,} rows.")

        return {
            "columns": columns,
            "timestamp_column": timestamp_column,
            "sample_rows": sample_rows,
            "row_count": rows_used,
            "rows_received": rows_received,
            "rows_used": rows_used,
            "rows_dropped": rows_dropped,
            "drop_reasons": drop_reasons,
            "quality_counts": {
                "rows_with_missing_values": rows_with_missing_values,
                "rows_with_invalid_numeric": rows_with_invalid_numeric,
                "invalid_numeric_cells": invalid_numeric_cells,
                "missing_by_column": dict(missing_by_column),
                "invalid_by_column": dict(invalid_by_column),
                "interpolated_numeric_cells": int(imputation_report.get("imputed_cells", 0)),
            },
            "cleaning_warnings": warnings,
            "schema_detection": {
                **chilled_water_schema,
                "column_lookup": dict(chilled_water_schema.get("column_lookup") or {}),
                "bad_columns": bad_columns,
            },
            "analysis_gate_state": analysis_gate_state,
            "data_quality_messages": schema_messages,
            "sample_interval_seconds": interval_seconds,
            "imputation_report": imputation_report,
            "delimiter": delimiter,
            "header_present": header_present,
            "first_timestamp": first_timestamp,
            "last_timestamp": last_timestamp,
            "chunk_count": max(1, (rows_received + csv_chunk_size_rows - 1) // csv_chunk_size_rows),
            "memory_estimate_bytes": int(memory_estimate_bytes),
        }
