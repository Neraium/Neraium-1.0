"""Disk-indexed, lossless complete-case analysis view; no analytical statistics."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sqlite3
from collections import Counter
from pathlib import Path

from .csv_loader import _detect_timestamp_column
from .timeparse import parse_source_timestamp


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def time_key(value):
    # ISO keys normalize aware offsets for ordering without changing source timestamps.
    from datetime import timezone
    dt = parse_source_timestamp(value) if isinstance(value, str) else value
    return (dt.astimezone(timezone.utc) if dt.tzinfo else dt).isoformat()


class QualitySource:
    """Temporary SQLite view. Each row retains exact CSV cell strings and source position."""
    def __init__(self, path, database, signal_names, timestamp_column=None):
        self.path = Path(path)
        self.sha256 = file_hash(path)
        self.db = sqlite3.connect(database)
        self.db.execute('CREATE TABLE valid (position INTEGER PRIMARY KEY, source_row INTEGER, time TEXT, cells TEXT)')
        self.db.execute('CREATE INDEX valid_time ON valid(time)')
        self.db.execute('CREATE TABLE excluded (source_row INTEGER PRIMARY KEY, timestamp TEXT, issues TEXT)')
        self.rows = self
        reasons, cells, source_cadence, valid_cadence = Counter(), Counter(), Counter(), Counter()
        previous = previous_valid = None
        valid_count = total = 0
        try:
            with self.path.open(encoding='utf-8-sig', newline='') as stream:
                reader = csv.reader(stream, strict=True)
                self.columns = next(reader)
                if (len(set(self.columns)) != len(self.columns) or any(not c or c != c.strip() or c.startswith('__') or any(ord(x)<32 for x in c) for c in self.columns)):
                    raise ValueError('Invalid CSV headers')
                self.timestamp_column = _detect_timestamp_column(self.columns, timestamp_column)
                self.numeric_columns = [c for c in self.columns if c != self.timestamp_column]
                if self.numeric_columns != list(signal_names) or not 1 <= len(signal_names) <= 32:
                    raise ValueError('Selected fixed signal schema must match CSV telemetry in order')
                for total, values in enumerate(reader, 1):
                    if len(values) != len(self.columns):
                        raise ValueError(f'Malformed data row {total}')
                    row = dict(zip(self.columns, values))
                    stamp = row[self.timestamp_column]
                    dt = parse_source_timestamp(stamp)
                    if previous is not None:
                        if (dt.tzinfo is None) != (previous.tzinfo is None) or dt <= previous:
                            raise ValueError(f'Timestamps must be strictly increasing, unique, and use one mode: row {total}')
                        source_cadence[str((dt-previous).total_seconds())] += 1
                    else:
                        self.start = stamp
                    previous = dt
                    self.end = stamp
                    issues = []
                    for signal in self.numeric_columns:
                        value = row[signal]
                        reason = None
                        if not value.strip():
                            reason = 'blank'
                        else:
                            try:
                                if not math.isfinite(float(value)):
                                    reason = 'non_finite'
                            except (ValueError, OverflowError):
                                reason = 'non_numeric'
                        if reason:
                            issues.append({'signal': signal, 'reason': reason})
                            cells[f'{signal}:{reason}'] += 1
                    if issues:
                        for reason in {x['reason'] for x in issues}:
                            reasons[reason] += 1
                        self.db.execute('INSERT INTO excluded VALUES (?,?,?)', (total, stamp, json.dumps(issues)))
                    else:
                        if previous_valid is not None:
                            valid_cadence[str((dt-previous_valid).total_seconds())] += 1
                        previous_valid = dt
                        self.db.execute('INSERT INTO valid VALUES (?,?,?,?)', (valid_count, total, time_key(dt), json.dumps(row)))
                        valid_count += 1
                    if total % 10000 == 0:
                        self.db.commit()
            self.db.commit()
            if not valid_count:
                raise ValueError('No valid telemetry rows')
            if file_hash(path) != self.sha256:
                raise ValueError('Source changed while indexing')
        except BaseException:
            self.db.close()
            raise
        self.count = valid_count
        self.numeric_profiles = [{'column': c, 'numeric_ratio': 1.0, 'missing_count': 0, 'non_numeric_count': 0} for c in self.numeric_columns]
        self.audit = {'original_rows': total, 'valid_rows': valid_count, 'excluded_rows': total-valid_count,
                      'excluded_rows_by_reason_nonexclusive': dict(reasons), 'invalid_cells_by_signal_and_reason': dict(cells),
                      'source_cadence_seconds': dict(source_cadence), 'valid_cadence_seconds': dict(valid_cadence),
                      'rule': 'Exclude a row iff any selected telemetry cell is blank, non-numeric or non-finite. Preserve all other cells verbatim.',
                      'source_row_numbering': '1-based data rows, header excluded',
                      'timestamps_strictly_increasing_unique': True,
                      'excluded_row_provenance': [{'source_row': r, 'timestamp': t, 'issues': json.loads(i)} for r,t,i in self.db.execute('SELECT * FROM excluded ORDER BY source_row')]}

    def __len__(self):
        return self.count

    def __getitem__(self, index):
        if index < 0:
            index += self.count
        result = self.db.execute('SELECT cells FROM valid WHERE position=?', (index,)).fetchone()
        if result is None:
            raise IndexError(index)
        return json.loads(result[0])

    def window(self, start, end):
        count = self.db.execute('SELECT count(*) FROM valid WHERE time>=? AND time<?', (time_key(start), time_key(end))).fetchone()[0]
        if not 16 <= count <= 12000:
            raise ValueError(f'Window requires 16–12000 valid rows; found {count}')
        records = list(self.db.execute('SELECT source_row,cells FROM valid WHERE time>=? AND time<? ORDER BY position', (time_key(start), time_key(end))))
        rows = [json.loads(c) for _, c in records]
        return rows, {'row_count': count, 'source_row_numbers': [r for r,_ in records],
                      'source_timestamps': [r[self.timestamp_column] for r in rows],
                      'time_boundary_start_inclusive': start.isoformat(), 'time_boundary_end_exclusive': end.isoformat()}

    def close(self):
        self.db.close()
