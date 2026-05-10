from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.connectors.models import ConnectorHealthStatus, NormalizedConnectorBatch


class ConnectorBase(ABC):
    connector_type = "base"
    display_name = "Base Connector"
    functional = False

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    @abstractmethod
    def connect(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def validate_connection(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def fetch_historical(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def stream_latest(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def normalize(self, raw_data: list[dict[str, Any]]) -> NormalizedConnectorBatch:
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> ConnectorHealthStatus:
        raise NotImplementedError
