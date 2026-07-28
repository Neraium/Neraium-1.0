from __future__ import annotations

import json
from typing import Any, Literal, cast

import httpx

from app.connectors.base import ConnectorBase
from app.connectors.csv_connector import CONTEXT_COLUMNS, infer_unit, slugify
from app.connectors.limits import (
    MAX_CONNECTOR_RESPONSE_BYTES,
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
        return {"ok": True, "message": "REST API connector settings are complete.", "endpoint": endpoint}

    def validate_connection(self) -> dict[str, Any]:
        payload = self._request_json()
        records = self._extract_records(payload)
        if not records:
            return {"ok": False, "message": "REST API returned an empty dataset."}
        return {"ok": True, "message": f"REST API access confirmed with {len(records)} telemetry records."}

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
        timestamp_column = self._normalization_columns(raw_data)
        records, errors = self._normalize_rows(
            raw_data,
            timestamp_column=timestamp_column,
            source_id=source_id,
            system_id=system_id,
        )
        return self._build_normalized_batch(
            records,
            errors,
            source_id=source_id,
            system_id=system_id,
        )

    @staticmethod
    def _normalization_columns(raw_data: list[dict[str, Any]]) -> str:
        if not raw_data:
            raise ValueError("REST API returned no telemetry records.")

        enforce_source_row_limit(raw_data)
        timestamp_column = detect_timestamp_column(list(raw_data[0].keys()))
        if timestamp_column is None:
            raise ValueError("REST telemetry is missing a timestamp field.")
        sensor_columns = [
            column_name
            for column_name, value in raw_data[0].items()
            if RESTConnector._is_wide_sensor_value(column_name, value, timestamp_column)
        ]
        enforce_normalization_budget(row_count=len(raw_data), sensor_count=len(sensor_columns))
        return timestamp_column

    @staticmethod
    def _is_wide_sensor_value(column_name: str, raw_value: Any, timestamp_column: str) -> bool:
        normalized_column = column_name.strip().lower()
        return (
            normalized_column != timestamp_column.lower()
            and normalized_column not in CONTEXT_COLUMNS
            and not isinstance(raw_value, (dict, list))
        )

    @staticmethod
    def _normalize_rows(
        raw_data: list[dict[str, Any]],
        *,
        timestamp_column: str,
        source_id: str,
        system_id: str,
    ) -> tuple[list[NormalizedTelemetryRecord], list[ValidationIssue]]:
        records: list[NormalizedTelemetryRecord] = []
        errors: list[ValidationIssue] = []
        for row_index, row in enumerate(raw_data, start=1):
            normalized_timestamp = normalize_timestamp_value(row.get(timestamp_column))
            if normalized_timestamp is None:
                errors.append(
                    ValidationIssue(
                        row_number=row_index,
                        field=timestamp_column,
                        message="Timestamp is missing or malformed.",
                    )
                )
                continue
            records.extend(
                RESTConnector._normalize_row(
                    row,
                    row_index=row_index,
                    timestamp_column=timestamp_column,
                    normalized_timestamp=normalized_timestamp,
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
        source_id: str,
        system_id: str,
        errors: list[ValidationIssue],
    ) -> list[NormalizedTelemetryRecord]:
        context = {
            key: value
            for key, value in row.items()
            if key.lower() in CONTEXT_COLUMNS and value not in (None, "")
        }
        row_quality = str(row.get("quality") or row.get("status") or "good").strip().lower() or "good"
        normalized_keys = {str(key).strip().lower(): key for key in row}
        if "sensor_id" in normalized_keys and "value" in normalized_keys:
            record = RESTConnector._normalize_long_format_record(
                row,
                normalized_keys=normalized_keys,
                row_index=row_index,
                normalized_timestamp=normalized_timestamp,
                source_id=source_id,
                system_id=system_id,
                row_quality=row_quality,
                context=context,
                errors=errors,
            )
            return [record] if record is not None else []
        return RESTConnector._normalize_wide_format_records(
            row,
            row_index=row_index,
            timestamp_column=timestamp_column,
            normalized_timestamp=normalized_timestamp,
            source_id=source_id,
            system_id=system_id,
            row_quality=row_quality,
            context=context,
            errors=errors,
        )

    @staticmethod
    def _normalize_long_format_record(
        row: dict[str, Any],
        *,
        normalized_keys: dict[str, Any],
        row_index: int,
        normalized_timestamp: str,
        source_id: str,
        system_id: str,
        row_quality: str,
        context: dict[str, Any],
        errors: list[ValidationIssue],
    ) -> NormalizedTelemetryRecord | None:
        raw_sensor_id = str(row.get(normalized_keys["sensor_id"]) or "").strip()
        numeric_value = validate_numeric_value(row.get(normalized_keys["value"]))
        if not raw_sensor_id:
            errors.append(ValidationIssue(row_number=row_index, field="sensor_id", message="Sensor ID is required."))
            return None
        if numeric_value is None:
            errors.append(
                ValidationIssue(
                    row_number=row_index,
                    field="value",
                    message=f"Sensor value for {raw_sensor_id} must be numeric.",
                )
            )
            return None

        raw_unit = row.get(cast(str, normalized_keys.get("unit"))) if "unit" in normalized_keys else infer_unit(raw_sensor_id)
        unit = normalize_unit(raw_unit)
        if not validate_unit(unit):
            errors.append(
                ValidationIssue(
                    row_number=row_index,
                    field="unit",
                    message=f"Unit {unit or '[blank]'} is not supported for {raw_sensor_id}.",
                )
            )
            return None

        sensor_name_key = cast(str, normalized_keys.get("sensor_name"))
        sensor_name = str(row.get(sensor_name_key) or raw_sensor_id).strip()
        return NormalizedTelemetryRecord(
            source_id=source_id,
            system_id=system_id,
            sensor_id=slugify(f"{system_id}-{raw_sensor_id}"),
            sensor_name=sensor_name,
            value=numeric_value,
            unit=unit,
            timestamp=normalized_timestamp,
            quality_status=row_quality,
            metadata={"row_number": row_index, **context},
        )

    @staticmethod
    def _normalize_wide_format_records(
        row: dict[str, Any],
        *,
        row_index: int,
        timestamp_column: str,
        normalized_timestamp: str,
        source_id: str,
        system_id: str,
        row_quality: str,
        context: dict[str, Any],
        errors: list[ValidationIssue],
    ) -> list[NormalizedTelemetryRecord]:
        records: list[NormalizedTelemetryRecord] = []
        for column_name, raw_value in row.items():
            if not RESTConnector._is_wide_sensor_value(column_name, raw_value, timestamp_column):
                continue
            record = RESTConnector._normalize_wide_sensor_value(
                row,
                column_name=column_name,
                raw_value=raw_value,
                row_index=row_index,
                normalized_timestamp=normalized_timestamp,
                source_id=source_id,
                system_id=system_id,
                row_quality=row_quality,
                context=context,
                errors=errors,
            )
            if record is not None:
                records.append(record)
        return records

    @staticmethod
    def _normalize_wide_sensor_value(
        row: dict[str, Any],
        *,
        column_name: str,
        raw_value: Any,
        row_index: int,
        normalized_timestamp: str,
        source_id: str,
        system_id: str,
        row_quality: str,
        context: dict[str, Any],
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
            metadata={"row_number": row_index, **context},
        )

    def _build_normalized_batch(
        self,
        records: list[NormalizedTelemetryRecord],
        errors: list[ValidationIssue],
        *,
        source_id: str,
        system_id: str,
    ) -> NormalizedConnectorBatch:
        deduplicated_records, duplicates_removed = deduplicate_records(records)
        warnings = self._normalization_warnings(errors, duplicates_removed)
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

    @staticmethod
    def _normalization_warnings(errors: list[ValidationIssue], duplicates_removed: int) -> list[str]:
        warnings: list[str] = []
        if duplicates_removed:
            warnings.append(f"{duplicates_removed} duplicate telemetry records were ignored.")
        if errors:
            warnings.extend(summarize_issues(errors))
        return warnings

    def health_check(self) -> ConnectorHealthStatus:
        endpoint = self.config.get("endpoint")
        status: Literal["ready", "not_configured"] = "ready" if endpoint else "not_configured"
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
                with client.stream(
                    method,
                    endpoint,
                    headers=headers,
                    json=self.config.get("sample_payload"),
                ) as response:
                    response.raise_for_status()
                    content_length = response.headers.get("content-length")
                    try:
                        declared_size = int(content_length) if content_length else None
                    except ValueError:
                        raise ValueError("REST API returned an invalid Content-Length header.") from None
                    if declared_size is not None and declared_size > MAX_CONNECTOR_RESPONSE_BYTES:
                        raise ValueError(
                            f"REST API response exceeds the {MAX_CONNECTOR_RESPONSE_BYTES}-byte connector limit."
                        )
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        content.extend(chunk)
                        if len(content) > MAX_CONNECTOR_RESPONSE_BYTES:
                            raise ValueError(
                                f"REST API response exceeds the {MAX_CONNECTOR_RESPONSE_BYTES}-byte connector limit."
                            )
        except httpx.HTTPStatusError as exc:
            raise ValueError(f"REST API returned status {exc.response.status_code}.") from None
        except httpx.HTTPError:
            raise ValueError("REST API could not be reached. Check the endpoint and network path.") from None

        try:
            return json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("REST API response was not valid JSON.") from None

    def _extract_records(self, payload: Any) -> list[dict[str, Any]]:
        payload = self._payload_at_records_path(payload)
        if isinstance(payload, list):
            return self._validated_record_list(payload)
        if isinstance(payload, dict):
            return self._records_from_mapping(payload)
        raise ValueError("REST API response did not include a usable telemetry record list.")

    def _payload_at_records_path(self, payload: Any) -> Any:
        records_path = self.config.get("records_path")
        if not records_path or not isinstance(payload, dict):
            return payload

        current: Any = payload
        for segment in str(records_path).split("."):
            if not isinstance(current, dict) or segment not in current:
                raise ValueError(f"REST API response did not include records_path {records_path}.")
            current = current[segment]
        return current

    @staticmethod
    def _validated_record_list(payload: list[Any]) -> list[dict[str, Any]]:
        if not all(isinstance(item, dict) for item in payload):
            raise ValueError("REST API response list must contain objects.")
        enforce_source_row_limit(payload)
        return payload

    @staticmethod
    def _records_from_mapping(payload: dict[str, Any]) -> list[dict[str, Any]]:
        for key in ("records", "data", "items", "telemetry"):
            candidate = payload.get(key)
            if isinstance(candidate, list) and all(isinstance(item, dict) for item in candidate):
                return candidate
        raise ValueError("REST API response did not include a usable telemetry record list.")
