from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Callable

from app.services.data_quality import detect_timestamp_column, parse_numeric_value, parse_timestamp


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
        excluded_indexes = {index for index in (timestamp_index, identity_index) if index is not None}
        numeric_indexes = [
            index
            for index in range(len(columns))
            if index not in excluded_indexes
            and sum(parse_numeric_value(row[index]) is not None for row in detection_rows)
            >= max(3, int(min(len(detection_rows), 1000) * 0.15))
        ]

        handle.seek(0)
        rows_received = 0
        blank_rows = 0
        malformed_rows = 0
        duplicate_timestamps = 0
        invalid_timestamps = 0
        no_numeric_values = 0
        rows_with_missing_values = 0
        rows_with_invalid_numeric = 0
        invalid_numeric_cells = 0
        seen_timestamps: set[str] = set()
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
                if raw_value == "":
                    continue
                numeric_value = parse_numeric_value(raw_value)
                if numeric_value is None:
                    row[columns[index]] = ""
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
        if timestamp_index is not None and [item[0] for item in raw_rows_in_order] != [item[0] for item in cleaned]:
            warnings.append("Timestamps were unsorted and were ordered before analysis.")

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
            },
            "cleaning_warnings": warnings,
            "delimiter": delimiter,
            "header_present": header_present,
            "first_timestamp": first_timestamp,
            "last_timestamp": last_timestamp,
            "chunk_count": max(1, (rows_received + csv_chunk_size_rows - 1) // csv_chunk_size_rows),
            "memory_estimate_bytes": int(memory_estimate_bytes),
        }
