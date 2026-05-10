from __future__ import annotations

from typing import Any

import httpx

from app.connectors.base import ConnectorBase
from app.connectors.csv_connector import CONTEXT_COLUMNS, infer_unit, slugify
from app.connectors.models import ConnectorHealthStatus, NormalizedConnectorBatch, NormalizedTelemetryRecord, ValidationIssue
from app.connectors.validation import deduplicate_records, normalize_timestamp_value, normalize_unit, summarize_issues, validate_numeric_value, validate_unit
from app.services.data_quality import detect_timestamp_column


def masked_headers(headers: dict[str, str], token: str | None) -> dict[str, str]:
    masked = {}
    for key, value in headers.items():
        if key.lower() in {"authorization", "x-api-key", "api-key"}:
            masked[key] = mask_secret(value)
        else:
            masked[key] = value
    if token:
        masked["token"] = mask_secret(token)
    return masked


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    value = str(value)
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * max(4, len(value) - 4)}{value[-2:]}"


class RESTConnector(ConnectorBase):
    connector_type = "rest"
    display_name = "REST API"
    functional = True

    def __init__(self, config: dict[str, Any] | None = None, transport: httpx.BaseTransport | None = None) -> None:
        super().__init__(config)
        self.transport = transport

    def connect(self) -> dict[str, Any]:
        endpoint = self.config.get("endpoint")
        if not endpoint:
            return {"ok": False, "message": "REST endpoint is required."}
        return {"ok": True, "message": "REST connector configured.", "endpoint": endpoint}

    def validate_connection(self) -> dict[str, Any]:
        payload = self._request_json()
        records = self._extract_records(payload)
        if not records:
            return {"ok": False, "message": "REST API returned an empty dataset."}
        return {"ok": True, "message": f"REST API validated with {len(records)} records."}

    def fetch_historical(self) -> list[dict[str, Any]]:
        payload = self._request_json()
        records = self._extract_records(payload)
        if not records:
            raise ValueError("REST API returned an empty dataset.")
        return records

    def stream_latest(self) -> list[dict[str, Any]]:
        records = self.fetch_historical()
        return records[-1:] if records else []

    def normalize(self, raw_data: list[dict[str, Any]]) -> NormalizedConnectorBatch:
        source_id = str(self.config.get("source_id") or "customer-rest")
        system_id = str(self.config.get("system_id") or "facility-rest")
        errors: list[ValidationIssue] = []
        warnings: list[str] = []
        records: list[NormalizedTelemetryRecord] = []

        if not raw_data:
            raise ValueError("REST API returned no telemetry records.")

        timestamp_column = detect_timestamp_column(list(raw_data[0].keys()))
        if timestamp_column is None:
            raise ValueError("REST telemetry is missing a timestamp field.")

        for row_index, row in enumerate(raw_data, start=1):
            normalized_timestamp = normalize_timestamp_value(row.get(timestamp_column))
            if normalized_timestamp is None:
                errors.append(ValidationIssue(row_number=row_index, field=timestamp_column, message="Timestamp is missing or malformed."))
                continue

            context = {
                key: value
                for key, value in row.items()
                if key.lower() in CONTEXT_COLUMNS and value not in (None, "")
            }
            row_quality = str(row.get("quality") or row.get("status") or "good").strip().lower() or "good"

            for column_name, raw_value in row.items():
                normalized_column = column_name.strip().lower()
                if normalized_column == timestamp_column.lower() or normalized_column in CONTEXT_COLUMNS:
                    continue
                if isinstance(raw_value, (dict, list)):
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
                        metadata={"row_number": row_index, **context},
                    )
                )

        deduplicated_records, duplicates_removed = deduplicate_records(records)
        if duplicates_removed:
            warnings.append(f"{duplicates_removed} duplicate telemetry records were ignored.")
        if errors:
            warnings.extend(summarize_issues(errors))
        if not deduplicated_records:
            raise ValueError("No valid telemetry records were returned by the REST API after validation.")

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
            metadata={"endpoint": self.config.get("endpoint")},
        )

    def health_check(self) -> ConnectorHealthStatus:
        endpoint = self.config.get("endpoint")
        status = "ready" if endpoint else "not_configured"
        return ConnectorHealthStatus(
            connector_type=self.connector_type,
            display_name=self.display_name,
            functional=True,
            connection_status=status,
            masked_configuration={
                "endpoint": endpoint or "No endpoint configured",
                "headers": masked_headers(self.config.get("headers", {}), self.config.get("token")),
            },
        )

    def _request_json(self) -> Any:
        endpoint = self.config.get("endpoint")
        if not endpoint:
            raise ValueError("REST endpoint is required.")

        method = str(self.config.get("method", "GET")).upper()
        headers = dict(self.config.get("headers") or {})
        token = self.config.get("token")
        if token and "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {token}"

        try:
            with httpx.Client(timeout=10.0, transport=self.transport) as client:
                response = client.request(
                    method,
                    endpoint,
                    headers=headers,
                    json=self.config.get("sample_payload"),
                )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ValueError(f"REST API returned status {exc.response.status_code}.") from None
        except httpx.HTTPError:
            raise ValueError("REST API could not be reached. Check the endpoint and network path.") from None

        try:
            return response.json()
        except ValueError:
            raise ValueError("REST API response was not valid JSON.") from None

    def _extract_records(self, payload: Any) -> list[dict[str, Any]]:
        records_path = self.config.get("records_path")
        if records_path and isinstance(payload, dict):
            current: Any = payload
            for segment in str(records_path).split("."):
                if not isinstance(current, dict) or segment not in current:
                    raise ValueError(f"REST API response did not include records_path {records_path}.")
                current = current[segment]
            payload = current

        if isinstance(payload, list):
            if all(isinstance(item, dict) for item in payload):
                return payload
            raise ValueError("REST API response list must contain objects.")

        if isinstance(payload, dict):
            for key in ("records", "data", "items", "telemetry"):
                candidate = payload.get(key)
                if isinstance(candidate, list) and all(isinstance(item, dict) for item in candidate):
                    return candidate

        raise ValueError("REST API response did not include a usable telemetry record list.")
