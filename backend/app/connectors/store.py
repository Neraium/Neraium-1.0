from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.connectors.models import ConnectorHealthStatus
from app.core.path_safety import ensure_storage_root, resolve_storage_path


def connectors_runtime_dir(runtime_dir: Path) -> Path:
    root = ensure_storage_root(runtime_dir)
    path = resolve_storage_path(root, "connectors")
    path.mkdir(parents=True, exist_ok=True)
    return path


def health_state_path(runtime_dir: Path) -> Path:
    return resolve_storage_path(connectors_runtime_dir(runtime_dir), "health.json")


def read_health_state(runtime_dir: Path) -> dict[str, Any]:
    path = health_state_path(runtime_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def write_health_state(runtime_dir: Path, payload: dict[str, Any]) -> None:
    path = health_state_path(runtime_dir)
    temp_path = path.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp_path.replace(path)


def upsert_health_status(runtime_dir: Path, status: ConnectorHealthStatus) -> None:
    state = read_health_state(runtime_dir)
    items = state.get("connectors", {})
    items[status.connector_type] = status.model_dump()
    state["connectors"] = items
    state["updated_at"] = datetime.utcnow().isoformat()
    write_health_state(runtime_dir, state)
