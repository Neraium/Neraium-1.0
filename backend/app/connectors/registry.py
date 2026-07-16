from __future__ import annotations

from typing import Any

from app.connectors.csv_connector import CSVConnector
from app.connectors.database_connector import DatabaseConnector
from app.connectors.models import ConnectorDescriptor
from app.connectors.placeholders import (
    BACnetConnector,
    BASBMSConnector,
    HaywardConnector,
    MQTTConnector,
    ModbusConnector,
    NodeRedConnector,
    OPCUAConnector,
    PentairConnector,
)
from app.connectors.rest_connector import RESTConnector

CONNECTOR_CLASSES = {
    "csv": CSVConnector,
    "rest": RESTConnector,
    "database": DatabaseConnector,
    "mqtt": MQTTConnector,
    "opcua": OPCUAConnector,
    "bacnet": BACnetConnector,
    "pentair": PentairConnector,
    "hayward": HaywardConnector,
    "modbus": ModbusConnector,
    "nodered": NodeRedConnector,
    "bas_bms": BASBMSConnector,
}


def get_connector(connector_type: str, config: dict[str, Any] | None = None) -> object:
    connector_class = CONNECTOR_CLASSES.get(connector_type)
    if connector_class is None:
        raise ValueError(f"Connector type {connector_type} is not supported.")
    return connector_class(config)


def build_connector_descriptors() -> list[ConnectorDescriptor]:
    return [
        ConnectorDescriptor(
            connector_type="csv",
            display_name="CSV / Local File",
            functional=True,
            description="Upload customer CSV exports and normalize sensor readings for Neraium ingestion.",
        ),
        ConnectorDescriptor(
            connector_type="rest",
            display_name="REST API",
            functional=True,
            description="Poll external telemetry APIs and normalize JSON payloads into Neraium records.",
        ),
        ConnectorDescriptor(
            connector_type="database",
            display_name="Database",
            functional=True,
            description="Run bounded read-only SQLite or PostgreSQL telemetry queries and normalize the results.",
        ),
        ConnectorDescriptor(
            connector_type="mqtt",
            display_name="MQTT",
            functional=False,
            description="Scaffold for broker-based streaming telemetry.",
            supports_streaming=True,
        ),
        ConnectorDescriptor(
            connector_type="opcua",
            display_name="OPC UA",
            functional=False,
            description="Scaffold for industrial protocol telemetry ingestion.",
            supports_streaming=True,
        ),
        ConnectorDescriptor(
            connector_type="bacnet",
            display_name="BACnet / BMS",
            functional=False,
            description="Scaffold for building management telemetry ingestion.",
            supports_streaming=True,
        ),
        ConnectorDescriptor(
            connector_type="pentair",
            display_name="Pentair",
            functional=False,
            description="Read-only adapter scaffold for Pentair telemetry ingestion.",
            supports_streaming=True,
        ),
        ConnectorDescriptor(
            connector_type="hayward",
            display_name="Hayward",
            functional=False,
            description="Read-only adapter scaffold for Hayward telemetry ingestion.",
            supports_streaming=True,
        ),
        ConnectorDescriptor(
            connector_type="modbus",
            display_name="Modbus",
            functional=False,
            description="Read-only adapter scaffold for Modbus telemetry ingestion.",
            supports_streaming=True,
        ),
        ConnectorDescriptor(
            connector_type="nodered",
            display_name="Node-RED",
            functional=False,
            description="Read-only adapter scaffold for Node-RED telemetry ingestion.",
            supports_streaming=True,
        ),
        ConnectorDescriptor(
            connector_type="bas_bms",
            display_name="BAS / BMS",
            functional=False,
            description="Read-only adapter scaffold for BAS/BMS telemetry ingestion.",
            supports_streaming=True,
        ),
    ]
