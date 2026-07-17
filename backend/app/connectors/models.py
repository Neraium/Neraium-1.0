from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

from app.contracts import ContractModel, Identifier, SecretText, validate_http_url


SUPPORTED_UNITS = {
    "",
    "%",
    "c",
    "f",
    "kpa",
    "pa",
    "ppm",
    "ms",
    "s",
    "min",
    "hour",
    "gpm",
    "lpm",
    "gal",
    "l",
    "lux",
    "ppfd",
    "ec",
    "ph",
    "vpd",
    "kw",
    "w",
    "amps",
    "cfm",
}


class NormalizedTelemetryRecord(BaseModel):
    source_id: str
    facility_id: str | None = None
    room_id: str | None = None
    system_id: str
    sensor_id: str
    sensor_name: str
    value: float
    unit: str = ""
    timestamp: str
    quality_status: str = "good"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValidationIssue(BaseModel):
    row_number: int | None = None
    field: str
    message: str


class NormalizedConnectorBatch(BaseModel):
    connector_type: str
    source_id: str
    system_id: str
    records: list[NormalizedTelemetryRecord] = Field(default_factory=list)
    sensor_count: int = 0
    record_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    errors: list[ValidationIssue] = Field(default_factory=list)
    duplicate_records_removed: int = 0
    last_sync_time: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConnectorHealthStatus(BaseModel):
    connector_type: str
    display_name: str
    functional: bool
    connection_status: Literal["ready", "degraded", "offline", "not_configured"] = "not_configured"
    last_sync_time: str | None = None
    sensors_detected: int = 0
    records_ingested: int = 0
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    masked_configuration: dict[str, Any] = Field(default_factory=dict)


class ConnectorDescriptor(BaseModel):
    connector_type: str
    display_name: str
    functional: bool
    description: str
    supports_historical: bool = True
    supports_streaming: bool = False


class ConnectorTestRequest(ContractModel):
    connector_type: Literal[
        "csv", "rest", "database", "mqtt", "opcua", "bacnet",
        "pentair", "hayward", "modbus", "nodered", "bas_bms",
    ]
    config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def config_is_bounded(self):
        if len(self.config) > 50 or len(json.dumps(self.config, default=str).encode("utf-8")) > 1_048_576:
            raise ValueError("Connector config exceeds the supported size.")
        return self


class RestConnectorRequest(ContractModel):
    source_id: Identifier = "customer-rest"
    system_id: Identifier = "facility-rest"
    endpoint: str
    method: Literal["GET", "POST"] = "GET"
    headers: dict[Annotated[str, StringConstraints(min_length=1, max_length=128)], Annotated[str, StringConstraints(max_length=4096)]] = Field(default_factory=dict, max_length=50)
    token: SecretText | None = None
    records_path: Annotated[str, StringConstraints(min_length=1, max_length=500, pattern=r"^[A-Za-z0-9_.-]+$")] | None = None
    sample_payload: dict[str, Any] | None = None

    @field_validator("endpoint")
    @classmethod
    def endpoint_is_safe_http(cls, value: str) -> str:
        return validate_http_url(value)

    @model_validator(mode="after")
    def sample_is_bounded(self):
        if self.sample_payload is not None and len(json.dumps(self.sample_payload, default=str).encode("utf-8")) > 1_048_576:
            raise ValueError("Sample payload exceeds the 1 MiB limit.")
        return self


class DatabaseConnectorRequest(ContractModel):
    source_id: Identifier = "customer-database"
    system_id: Identifier = "facility-database"
    database_url: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    query: Annotated[str, StringConstraints(min_length=1, max_length=20_000)]
    parameters: dict[str, Any] | list[Any] | None = None
    latest_query: Annotated[str, StringConstraints(min_length=1, max_length=20_000)] | None = None
    max_rows: int = Field(default=5000, ge=1, le=10_000)
    query_timeout_seconds: int = Field(default=30, ge=1, le=120)
    sslmode: Literal["require", "verify-ca", "verify-full"] = "require"


class ConnectorActionResponse(BaseModel):
    connector_type: str
    message: str
    connection_status: str
    last_sync_time: str | None = None
    sensors_detected: int = 0
    records_ingested: int = 0
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    masked_configuration: dict[str, Any] = Field(default_factory=dict)
    normalized_preview: list[NormalizedTelemetryRecord] = Field(default_factory=list)
