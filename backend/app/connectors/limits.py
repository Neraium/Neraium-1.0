from __future__ import annotations

from typing import Any


MAX_CONNECTOR_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_CONNECTOR_SOURCE_ROWS = 10_000
MAX_CONNECTOR_NORMALIZED_RECORDS = 20_000


def enforce_source_row_limit(records: list[dict[str, Any]]) -> None:
    if len(records) > MAX_CONNECTOR_SOURCE_ROWS:
        raise ValueError(
            f"Connector dataset contains {len(records)} source rows; the connector limit is "
            f"{MAX_CONNECTOR_SOURCE_ROWS}. Use the historical telemetry upload for larger datasets."
        )


def enforce_normalization_budget(*, row_count: int, sensor_count: int) -> None:
    potential_records = max(0, int(row_count)) * max(0, int(sensor_count))
    if potential_records > MAX_CONNECTOR_NORMALIZED_RECORDS:
        raise ValueError(
            f"Connector dataset could expand to {potential_records} normalized readings; the connector limit is "
            f"{MAX_CONNECTOR_NORMALIZED_RECORDS}. Reduce the requested window or use the historical telemetry upload."
        )
