from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.connectors.base import ConnectorBase
from app.connectors.limits import (
    MAX_CONNECTOR_SOURCE_ROWS,
    enforce_normalization_budget,
    enforce_source_row_limit,
)
from app.connectors.models import (
    ConnectorHealthStatus,
    NormalizedConnectorBatch,
    NormalizedTelemetryRecord,
    ValidationIssue,
)
from app.connectors.validation import (
    deduplicate_records,
    normalize_timestamp_value,
    normalize_unit,
    summarize_issues,
    validate_numeric_value,
    validate_unit,
)
from app.services.data_quality import detect_timestamp_column

CONTEXT_COLUMNS = {"room", "zone", "bay", "line", "quality", "status", "unit", "source_id", "system_id"}


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-") or "sensor"


def infer_unit(sensor_name: str) -> str:
    normalized = sensor_name.strip().lower()
    if "temp" in normalized:
        return "F"
    if "humidity" in normalized or normalized == "rh":
        return "%"
    if "co2" in normalized:
        return "ppm"
    if "pressure" in normalized:
        return "Pa"
    if "irrigation" in normalized or "flow" in normalized:
        return "gpm"
    if "light" in normalized:
        return "ppfd"
    return ""


def _normalize_wide_sensor_record(
    row: dict[str, Any],
    *,
    column_name: str,
    raw_value: Any,
    row_index: int,
    normalized_timestamp: str,
    source_id: str,
    system_id: str,
    row_quality: str,
    metadata: dict[str, Any],
    errors: list[ValidationIssue],
) -> NormalizedTelemetryRecord | None:
    numeric_value = validate_numeric_value(raw_value)
    if numeric_value is None:
        if raw_value not in (None, ""):
            errors.append(
                ValidationIssue(
                    row_number=row_index,
                    field=column_name,
                    message=f"Sensor value for {column_name} must be numeric.",
                )
            )
        return None

    unit = normalize_unit(row.get(f"{column_name}_unit") or row.get("unit") or infer_unit(column_name))
    if not validate_unit(unit):
        errors.append(
            ValidationIssue(
                row_number=row_index,
                field=column_name,
                message=f"Unit {unit or '[blank]'} is not supported for {column_name}.",
            )
        )
        return None

    return NormalizedTelemetryRecord(
        source_id=source_id,
        system_id=system_id,
        sensor_id=slugify(f"{system_id}-{column_name}"),
        sensor_name=column_name,
        value=numeric_value,
        unit=unit,
        timestamp=normalized_timestamp,
        quality_status=row_quality,
        metadata=metadata,
    )


class CSVConnector(ConnectorBase):
    connector_type = "csv"
    display_name = "CSV / Local File"
    functional = True

    def connect(self) -> dict[str, Any]:
        filename = self.config.get("filename", "telemetry.csv")
        return {
            "message": f"CSV source {filename} is available for ingestion.",
            "filename": filename,
        }

    def validate_connection(self) -> dict[str, Any]:
        raw_content = self.config.get("content", "")
        if not str(raw_content).strip():
            return {"ok": False, "message": "CSV dataset is empty."}
        rows = self.fetch_historical()
        if not rows:
            return {"ok": False, "message": "CSV dataset does not contain any telemetry rows."}
        return {"ok": True, "message": f"CSV dataset validated with {len(rows)} rows."}

    def fetch_historical(self) -> list[dict[str, Any]]:
        raw_content = self.config.get("content", "")
        reader = csv.DictReader(io.StringIO(raw_content))
        rows: list[dict[str, Any]] = []
        for row in reader:
            rows.append(dict(row))
            if len(rows) > MAX_CONNECTOR_SOURCE_ROWS:
                enforce_source_row_limit(rows)
        return rows

    def stream_latest(self) -> list[dict[str, Any]]:
        rows = self.fetch_historical()
        return rows[-1:] if rows else []

    def normalize(self, raw_data: list[dict[str, Any]]) -> NormalizedConnectorBatch:
        filename, source_id, system_id = self._normalization_identity()
        timestamp_column = self._normalization_columns(raw_data)
        records, errors = self._normalize_rows(
            raw_data,
            timestamp_column=timestamp_column,
            filename=filename,
            source_id=source_id,
            system_id=system_id,
        )
        return self._build_normalized_batch(
            records,
            errors,
            filename=filename,
            source_id=source_id,
            system_id=system_id,
            timestamp_column=timestamp_column,
        )

    def _normalization_identity(self) -> tuple[str, str, str]:
        filename = str(self.config.get("filename", "telemetry.csv"))
        source_id = str(self.config.get("source_id") or Path(filename).stem or "csv-upload")
        system_id = str(self.config.get("system_id") or "facility-csv")
        return filename, source_id, system_id

    @staticmethod
    def _normalization_columns(raw_data: list[dict[str, Any]]) -> str:
        if not raw_data:
            raise ValueError("CSV dataset is empty. Upload a file with timestamped telemetry rows.")

        enforce_source_row_limit(raw_data)
        timestamp_column = detect_timestamp_column(list(raw_data[0].keys()))
        if timestamp_column is None:
            raise ValueError("CSV dataset is missing a timestamp column. Add a column like timestamp or recorded_at.")
        sensor_columns = [
            column_name
            for column_name in raw_data[0]
            if CSVConnector._is_sensor_column(column_name, timestamp_column)
        ]
        enforce_normalization_budget(row_count=len(raw_data), sensor_count=len(sensor_columns))
        return timestamp_column

    @staticmethod
    def _is_sensor_column(column_name: str | None, timestamp_column: str) -> bool:
        if not column_name:
            return False
        normalized_column = column_name.strip().lower()
        return normalized_column != timestamp_column.lower() and normalized_column not in CONTEXT_COLUMNS

    @staticmethod
    def _normalize_rows(
        raw_data: list[dict[str, Any]],
        *,
        timestamp_column: str,
        filename: str,
        source_id: str,
        system_id: str,
    ) -> tuple[list[NormalizedTelemetryRecord], list[ValidationIssue]]:
        records: list[NormalizedTelemetryRecord] = []
        errors: list[ValidationIssue] = []
        for row_index, row in enumerate(raw_data, start=2):
            normalized_timestamp = normalize_timestamp_value(row.get(timestamp_column))
            if normalized_timestamp is None:
                errors.append(
                    ValidationIssue(
                        row_number=row_index,
                        field=timestamp_column,
                        message="Timestamp is missing or could not be parsed.",
                    )
                )
                continue
            records.extend(
                CSVConnector._normalize_row(
                    row,
                    row_index=row_index,
                    timestamp_column=timestamp_column,
                    normalized_timestamp=normalized_timestamp,
                    filename=filename,
                    source_id=source_id,
                    system_id=system_id,
                    errors=errors,
                )
            )
        return records, errors

    @staticmethod
    def _normalize_row(
        row: dict[str, Any],
        *,
        row_index: int,
        timestamp_column: str,
        normalized_timestamp: str,
        filename: str,
        source_id: str,
        system_id: str,
        errors: list[ValidationIssue],
    ) -> list[NormalizedTelemetryRecord]:
        context = {
            key: value
            for key, value in row.items()
            if key and key.lower() in CONTEXT_COLUMNS and value not in (None, "")
        }
        row_quality = str(row.get("quality") or row.get("status") or "good").strip().lower() or "good"
        records: list[NormalizedTelemetryRecord] = []
        for column_name, raw_value in row.items():
            if not CSVConnector._is_sensor_column(column_name, timestamp_column):
                continue
            record = _normalize_wide_sensor_record(
                row,
                column_name=column_name,
                raw_value=raw_value,
                row_index=row_index,
                normalized_timestamp=normalized_timestamp,
                source_id=source_id,
                system_id=system_id,
                row_quality=row_quality,
                metadata={"row_number": row_index, "filename": filename, **context},
                errors=errors,
            )
            if record is not None:
                records.append(record)
        return records

    def _build_normalized_batch(
        self,
        records: list[NormalizedTelemetryRecord],
        errors: list[ValidationIssue],
        *,
        filename: str,
        source_id: str,
        system_id: str,
        timestamp_column: str,
    ) -> NormalizedConnectorBatch:
        deduplicated_records, duplicates_removed = deduplicate_records(records)
        warnings = self._normalization_warnings(errors, duplicates_removed)
        if not deduplicated_records:
            raise ValueError("No valid telemetry records were found after validation. Check timestamps, units, and sensor values.")

        sensor_ids = {record.sensor_id for record in deduplicated_records}
        return NormalizedConnectorBatch(
            connector_type=self.connector_type,
            source_id=source_id,
            system_id=system_id,
            records=deduplicated_records,
            sensor_count=len(sensor_ids),
            record_count=len(deduplicated_records),
            warnings=warnings,
            errors=errors,
            duplicate_records_removed=duplicates_removed,
            last_sync_time=max(record.timestamp for record in deduplicated_records),
            metadata={
                "filename": filename,
                "timestamp_column": timestamp_column,
                "ingested_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    @staticmethod
    def _normalization_warnings(errors: list[ValidationIssue], duplicates_removed: int) -> list[str]:
        warnings: list[str] = []
        if duplicates_removed:
            warnings.append(f"{duplicates_removed} duplicate telemetry records were ignored.")
        if errors:
            warnings.extend(summarize_issues(errors))
        return warnings

    def health_check(self) -> ConnectorHealthStatus:
        filename = self.config.get("filename")
        status: Literal["ready", "not_configured"] = "ready" if filename else "not_configured"
        return ConnectorHealthStatus(
            connector_type=self.connector_type,
            display_name=self.display_name,
            functional=True,
            connection_status=status,
            masked_configuration={"filename": filename or "No file ingested yet"},
        )
