from __future__ import annotations

import re
from datetime import datetime

SOURCE_CLOCK = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}')


def parse_source_timestamp(value: str) -> datetime:
    if not isinstance(value, str) or value != value.strip():
        raise ValueError(f'unsupported timestamp {value!r}')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError(f'unsupported timestamp {value!r}') from exc
    if parsed.tzinfo is None and not SOURCE_CLOCK.fullmatch(value):
        raise ValueError(f'unsupported naive timestamp {value!r}; use exact YYYY-MM-DD HH:MM:SS or timezone-aware ISO 8601')
    return parsed


def validate_ordered_unique(rows: list[dict], timestamp_column: str) -> list[datetime]:
    parsed = [parse_source_timestamp(row[timestamp_column]) for row in rows]
    aware = [item.tzinfo is not None for item in parsed]
    if any(aware) and not all(aware):
        raise ValueError('CSV mixes timezone-aware and timezone-unspecified timestamps')
    for index, (previous, current) in enumerate(zip(parsed, parsed[1:]), 2):
        if current <= previous:
            raise ValueError(f'timestamps must be strictly increasing and unique; data row {index}')
    return parsed
