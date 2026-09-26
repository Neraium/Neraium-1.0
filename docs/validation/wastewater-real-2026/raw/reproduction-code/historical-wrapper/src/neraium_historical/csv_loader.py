from __future__ import annotations

import csv
import hashlib
import io
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .timeparse import validate_ordered_unique

# Wrapper resource guards, not analytical limits. Engine windows are capped at 12,000.
MAX_CSV_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class LoadedCsv:
    path: Path
    columns: list[str]
    rows: list[dict[str, Any]]
    timestamp_column: str
    numeric_columns: list[str]
    numeric_profiles: list[dict[str, Any]]
    sha256: str


def _detect_timestamp_column(columns: list[str], requested: str | None) -> str:
    if requested is not None:
        if requested not in columns:
            raise ValueError(f'timestamp column {requested!r} not found')
        return requested
    candidates = [c for c in columns if c.lower() in {'timestamp', 'time', 'datetime', 'date_time'}]
    if len(candidates) == 1:
        return candidates[0]
    raise ValueError('timestamp column is ambiguous; pass --timestamp')


def load_csv(path: str | Path, *, timestamp_column: str | None = None) -> LoadedCsv:
    csv_path = Path(path)
    with csv_path.open('rb') as source:
        raw = source.read(MAX_CSV_BYTES + 1)
    if len(raw) > MAX_CSV_BYTES:
        raise ValueError(f'CSV exceeds {MAX_CSV_BYTES} byte resource limit')
    reader = csv.reader(io.StringIO(raw.decode('utf-8-sig'), newline=''), strict=True)
    columns = next(reader, None)
    if not columns:
        raise ValueError('CSV has no header')
    if any(not c or c != c.strip() or c.startswith('__') or any(ord(x) < 32 for x in c) for c in columns):
        raise ValueError('column names must be nonblank, unpadded and contain no control characters or reserved __ prefix')
    if len(set(columns)) != len(columns):
        raise ValueError('CSV contains duplicate column names')
    timestamp = _detect_timestamp_column(columns, timestamp_column)
    signals = [c for c in columns if c != timestamp]
    if not 1 <= len(signals) <= 32:
        raise ValueError('paired Neraium-1.0 requires 1–32 numeric signals')
    rows = []
    for values in reader:
        if len(values) != len(columns):
            raise ValueError(f'CSV line {reader.line_num}: expected {len(columns)} fields, found {len(values)}')
        row = dict(zip(columns, values))
        if not row[timestamp] or row[timestamp] != row[timestamp].strip():
            raise ValueError(f'CSV line {reader.line_num}: timestamp is missing or padded')
        for signal in signals:
            try:
                value = float(row[signal])
                if not math.isfinite(value):
                    raise ValueError()
            except (ValueError, OverflowError):
                raise ValueError(f'CSV line {reader.line_num}: signal {signal!r} requires a finite numeric value') from None
            row[signal] = value
        rows.append(row)
    if not rows:
        raise ValueError('CSV has no data rows')
    validate_ordered_unique(rows, timestamp)
    # Schema/validation facts only; no global statistics or inferred sensor-health flags.
    profiles = [{'column': c, 'numeric_ratio': 1.0, 'missing_count': 0, 'non_numeric_count': 0} for c in signals]
    return LoadedCsv(csv_path, columns, rows, timestamp, signals, profiles, hashlib.sha256(raw).hexdigest())
