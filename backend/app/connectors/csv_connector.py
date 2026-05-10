from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from app.connectors.base import ConnectorBase
from app.connectors.models import ConnectorHealthStatus, NormalizedConnectorBatch, NormalizedTelemetryRecord, ValidationIssue
from app.connectors.validation import deduplicate_records, normalize_timestamp_value, normalize_unit, summarize_issues, validate_numeric_value, validate_unit
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
        return [dict(row) for row in reader]

    def stream_latest(self) -> list[dict[str, Any]]:
        rows = self.fetch_historical()
        return rows[-1:] if rows else []

    def normalize(self, raw_data: list[dict[str, Any]]) -> NormalizedConnectorBatch:
        filename = str(self.config.get("filename", "telemetry.csv"))
        source_id = str(self.config.get("source_id") or Path(filename).stem or "csv-upload")
        system_id = str(self.config.get("system_id") or "facility-csv")
        records: list[NormalizedTelemetryRecord] = []
        errors: list[ValidationIssue] = []
        warnings: list[str] = []

        if not raw_data:
            raise ValueError("CSV dataset is empty. Upload a file with timestamped telemetry rows.")

        timestamp_column = detect_timestamp_column(list(raw_data[0].keys()))
        if timestamp_column is None:
            raise ValueError("CSV dataset is missing a timestamp column. Add a column like timestamp or recorded_at.")

        for row_index, row in enumerate(raw_data, start=2):
            normalized_timestamp = normalize_timestamp_value(row.get(timestamp_column))
            if normalized_timestamp is None:
                errors.append(ValidationIssue(row_number=row_index, field=timestamp_column, message="Timestamp is missing or could not be parsed."))
                continue

            context = {
                key: value
                for key, value in row.items()
                if key and key.lower() in CONTEXT_COLUMNS and value not in (None, "")
            }
            row_quality = str(row.get("quality") or row.get("status") or "good").strip().lower() or "good"

            for column_name, raw_value in row.items():
                if not column_name:
                    continue
                normalized_column = column_name.strip().lower()
                if normalized_column == timestamp_column.lower() or normalized_column in CONTEXT_COLUMNS:
                    continue

                numeric_value = validate_numeric_value(raw_value)
                if numeric_value is None:
                    if raw_value not in (None, ""):
                        errors.append(ValidationIssue(row_number=row_index, field=column_name, message=f"Sensor value for {column_name} must be numeric."))
                    continue

                unit = normalize_unit(row.get(f"{column_name}_unit") or row.get("unit") or infer_unit(column_name))
                if not validate_unit(unit):
                    errors.append(ValidationIssue(row_number=row_index, field=column_name, message=f"Unit {unit or '[blank]'} is not supported for {column_name}."))
                    continue

                sensor_id = slugify(f"{system_id}-{column_name}")
                records.append(
                    NormalizedTelemetryRecord(
                        source_id=source_id,
                        system_id=system_id,
                        sensor_id=sensor_id,
                        sensor_name=column_name,
                        value=numeric_value,
                        unit=unit,
                        timestamp=normalized_timestamp,
                        quality_status=row_quality,
                        metadata={
                            "row_number": row_index,
                            "filename": filename,
                            **context,
                        },
                    )
                )

        deduplicated_records, duplicates_removed = deduplicate_records(records)
        if duplicates_removed:
            warnings.append(f"{duplicates_removed} duplicate telemetry records were ignored.")
        if errors:
            warnings.extend(summarize_issues(errors))
        if not deduplicated_records:
            raise ValueError("No valid telemetry records were found after validation. Check timestamps, units, and sensor values.")

        sensor_ids = {record.sensor_id for record in deduplicated_records}
        last_sync_time = max(record.timestamp for record in deduplicated_records)
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
            last_sync_time=last_sync_time,
            metadata={
                "filename": filename,
                "timestamp_column": timestamp_column,
                "ingested_at": datetime.utcnow().isoformat(),
            },
        )

    def health_check(self) -> ConnectorHealthStatus:
        filename = self.config.get("filename")
        status = "ready" if filename else "not_configured"
        return ConnectorHealthStatus(
            connector_type=self.connector_type,
            display_name=self.display_name,
            functional=True,
            connection_status=status,
            masked_configuration={"filename": filename or "No file ingested yet"},
        )
