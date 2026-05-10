from __future__ import annotations

from app.connectors.base import ConnectorBase
from app.connectors.models import ConnectorHealthStatus, NormalizedConnectorBatch


class PlaceholderConnector(ConnectorBase):
    connector_type = "placeholder"
    display_name = "Placeholder"
    functional = False

    def connect(self) -> dict[str, str]:
        return {"message": f"{self.display_name} connector scaffold is present but not active yet."}

    def validate_connection(self) -> dict[str, str]:
        return {"ok": False, "message": f"{self.display_name} support is scaffolded and awaiting implementation."}

    def fetch_historical(self) -> list[dict[str, str]]:
        return []

    def stream_latest(self) -> list[dict[str, str]]:
        return []

    def normalize(self, raw_data: list[dict[str, str]]) -> NormalizedConnectorBatch:
        raise ValueError(f"{self.display_name} connector is not implemented yet.")

    def health_check(self) -> ConnectorHealthStatus:
        return ConnectorHealthStatus(
            connector_type=self.connector_type,
            display_name=self.display_name,
            functional=False,
            connection_status="not_configured",
            warnings=[f"{self.display_name} connector scaffold is ready for future implementation."],
        )


class DatabaseConnector(PlaceholderConnector):
    connector_type = "database"
    display_name = "Database"


class MQTTConnector(PlaceholderConnector):
    connector_type = "mqtt"
    display_name = "MQTT"


class OPCUAConnector(PlaceholderConnector):
    connector_type = "opcua"
    display_name = "OPC UA"


class BACnetConnector(PlaceholderConnector):
    connector_type = "bacnet"
    display_name = "BACnet / BMS"
