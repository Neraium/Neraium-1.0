from __future__ import annotations

from app.connectors.base import ConnectorBase
from app.connectors.models import ConnectorHealthStatus, NormalizedConnectorBatch


class PlaceholderConnector(ConnectorBase):
    connector_type = "placeholder"
    display_name = "Placeholder"
    functional = False

    def connect(self) -> dict[str, str]:
        return {"message": f"{self.display_name} is not available in this release."}

    def validate_connection(self) -> dict[str, str]:
        return {"ok": False, "message": f"{self.display_name} is not available in this release. Use a CSV dataset, REST API, or database connector."}

    def fetch_historical(self) -> list[dict[str, str]]:
        return []

    def stream_latest(self) -> list[dict[str, str]]:
        return []

    def normalize(self, raw_data: list[dict[str, str]]) -> NormalizedConnectorBatch:
        raise ValueError(f"{self.display_name} is not available in this release. Use a CSV dataset, REST API, or database connector.")

    def health_check(self) -> ConnectorHealthStatus:
        return ConnectorHealthStatus(
            connector_type=self.connector_type,
            display_name=self.display_name,
            functional=False,
            connection_status="not_configured",
            warnings=[f"{self.display_name} is not available in this release."],
        )


class MQTTConnector(PlaceholderConnector):
    connector_type = "mqtt"
    display_name = "MQTT"


class OPCUAConnector(PlaceholderConnector):
    connector_type = "opcua"
    display_name = "OPC UA"


class BACnetConnector(PlaceholderConnector):
    connector_type = "bacnet"
    display_name = "BACnet / BMS"


class PentairConnector(PlaceholderConnector):
    connector_type = "pentair"
    display_name = "Pentair"


class HaywardConnector(PlaceholderConnector):
    connector_type = "hayward"
    display_name = "Hayward"


class ModbusConnector(PlaceholderConnector):
    connector_type = "modbus"
    display_name = "Modbus"


class NodeRedConnector(PlaceholderConnector):
    connector_type = "nodered"
    display_name = "Node-RED"


class BASBMSConnector(PlaceholderConnector):
    connector_type = "bas_bms"
    display_name = "BAS / BMS"
