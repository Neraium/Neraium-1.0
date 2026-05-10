from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


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


class ConnectorTestRequest(BaseModel):
    connector_type: str
    config: dict[str, Any] = Field(default_factory=dict)


class RestConnectorRequest(BaseModel):
    source_id: str = "customer-rest"
    system_id: str = "facility-rest"
    endpoint: str
    method: str = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    token: str | None = None
    records_path: str | None = None
    sample_payload: dict[str, Any] | None = None


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
