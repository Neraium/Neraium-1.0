from __future__ import annotations

import json
import tempfile
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any

from app.connectors.models import ConnectorHealthStatus
from app.connectors.registry import CONNECTOR_CLASSES


_CONNECTOR_STORE_DIRECTORY = "connectors"
_HEALTH_STATE_FILENAME = "health.json"
_HEALTH_TEMP_PREFIX = ".health-"
_HEALTH_TEMP_SUFFIX = ".tmp"
_ALLOWED_CONNECTOR_TYPES = frozenset(CONNECTOR_CLASSES)


class ConnectorStorePathError(ValueError):
    """Raised when connector state storage escapes its approved root."""


class InvalidConnectorTypeError(ValueError):
    """Raised when connector state uses an identifier outside the registry."""


def _resolve_within(approved_root: Path, candidate: Path) -> Path:
    canonical_candidate = candidate.resolve(strict=False)
    try:
        canonical_candidate.relative_to(approved_root)
    except ValueError as exc:
        raise ConnectorStorePathError("Connector storage path is outside the approved root.") from exc
    return canonical_candidate


class ConnectorHealthStore:
    """Filesystem-backed connector health state rooted in trusted app configuration."""

    def __init__(self, approved_runtime_root: str | Path) -> None:
        configured_root = Path(approved_runtime_root)
        configured_root.mkdir(parents=True, exist_ok=True)
        self._runtime_root = configured_root.resolve(strict=True)

        connector_root_candidate = self._runtime_root.joinpath(_CONNECTOR_STORE_DIRECTORY)
        if connector_root_candidate.is_symlink():
            raise ConnectorStorePathError("Connector storage directory must not be a symbolic link.")
        connector_root = _resolve_within(self._runtime_root, connector_root_candidate)
        connector_root.mkdir(exist_ok=True)
        if connector_root.is_symlink():
            raise ConnectorStorePathError("Connector storage directory must not be a symbolic link.")
        self._connector_root = _resolve_within(self._runtime_root, connector_root.resolve(strict=True))
        self._lock = RLock()

    @property
    def state_path(self) -> Path:
        candidate = self._connector_root.joinpath(_HEALTH_STATE_FILENAME)
        if candidate.is_symlink():
            raise ConnectorStorePathError("Connector health state must not be a symbolic link.")
        return _resolve_within(self._connector_root, candidate)

    def read(self) -> dict[str, Any]:
        with self._lock:
            path = self.state_path
            if not path.exists():
                return {}
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
            return payload if isinstance(payload, dict) else {}

    def write(self, payload: Mapping[str, Any]) -> None:
        with self._lock:
            destination = self.state_path
            temporary_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self._connector_root,
                    prefix=_HEALTH_TEMP_PREFIX,
                    suffix=_HEALTH_TEMP_SUFFIX,
                    delete=False,
                ) as temporary_file:
                    json.dump(dict(payload), temporary_file, indent=2)
                    temporary_file.flush()
                    temporary_path = Path(temporary_file.name).resolve(strict=True)

                temporary_path = _resolve_within(self._connector_root, temporary_path)
                temporary_path.replace(destination)
                temporary_path = None
            finally:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)

    def upsert(self, status: ConnectorHealthStatus) -> None:
        connector_type = status.connector_type
        if connector_type not in _ALLOWED_CONNECTOR_TYPES:
            raise InvalidConnectorTypeError("Connector type is not supported.")

        with self._lock:
            state = self.read()
            stored_items = state.get("connectors", {})
            items = (
                {
                    key: value
                    for key, value in stored_items.items()
                    if key in _ALLOWED_CONNECTOR_TYPES and isinstance(value, dict)
                }
                if isinstance(stored_items, dict)
                else {}
            )
            items[connector_type] = status.model_dump()
            state["connectors"] = items
            state["updated_at"] = datetime.utcnow().isoformat()
            self.write(state)
